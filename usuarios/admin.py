from django.contrib import admin
from .models import PerfilUsuario


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ('user', 'estado', 'email_verificado', 'keycloak_id', 'creado_en')
    list_filter = ('estado', 'email_verificado', 'creado_en')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name', 'keycloak_id')
    readonly_fields = ('creado_en', 'actualizado_en', 'token_verificacion', 'token_expiracion')
    actions = ['activar_usuarios', 'desactivar_usuarios']

    @admin.action(description='Activar y verificar usuarios seleccionados')
    def activar_usuarios(self, request, queryset):
        for perfil in queryset:
            perfil.activar_cuenta()
        self.message_user(request, f"{queryset.count()} usuario(s) activado(s) exitosamente.")

    @admin.action(description='Marcar como inactivos')
    def desactivar_usuarios(self, request, queryset):
        queryset.update(estado='INACTIVO')
        for perfil in queryset:
            perfil.user.is_active = False
            perfil.user.save(update_fields=['is_active'])
        self.message_user(request, f"{queryset.count()} usuario(s) desactivado(s).")
