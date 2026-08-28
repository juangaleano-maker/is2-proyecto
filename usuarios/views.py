import json
import logging
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .forms import ReenviarCorreoForm, RegistroUsuarioForm
from .models import EstadoUsuario, PerfilUsuario
from .services.email_service import enviar_correo_activacion
from .services.keycloak_service import KeycloakAdminService

logger = logging.getLogger(__name__)


class RegistroView(View):
    """
    Vista pública para el autoregistro de usuarios.
    Crea el usuario en estado inactivo en Django, registra en Keycloak vía Admin API,
    genera el perfil en estado PENDIENTE_VERIFICACION y despacha el correo de activación.
    """
    template_name = 'usuarios/registro.html'

    def get(self, request):
        form = RegistroUsuarioForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            try:
                # 1. Crear usuario base de Django (inactivo hasta que verifique su correo)
                user = form.save(commit=False)
                user.is_active = False
                user.set_password(form.cleaned_data['password'])
                user.save()

                # 2. Registrar en Keycloak Admin API
                kc_service = KeycloakAdminService()
                kc_res = kc_service.crear_usuario(
                    username=user.username,
                    email=user.email,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    password=form.cleaned_data['password'],
                    required_actions=['VERIFY_EMAIL']
                )

                keycloak_id = kc_res.get('keycloak_id')

                # 3. Crear PerfilUsuario en estado PENDIENTE_VERIFICACION
                perfil = PerfilUsuario.objects.create(
                    user=user,
                    keycloak_id=keycloak_id,
                    estado=EstadoUsuario.PENDIENTE_VERIFICACION,
                    email_verificado=False
                )

                # 4. Enviar correo de activación
                enviar_correo_activacion(user, perfil, request=request)

                request.session['registro_email'] = user.email
                messages.success(
                    request,
                    f"¡Registro completado! Hemos enviado un correo de verificación a {user.email}."
                )
                return redirect('usuarios:registro_exitoso')

            except Exception as e:
                logger.exception("Error durante el proceso de autoregistro: %s", e)
                messages.error(
                    request,
                    f"Ocurrió un error al procesar el registro: {str(e)}"
                )
                return render(request, self.template_name, {'form': form})

        return render(request, self.template_name, {'form': form})


class RegistroExitosoView(View):
    """
    Pantalla informativa mostrada inmediatamente tras el registro,
    notificando que la cuenta está pendiente de verificación por correo.
    """
    template_name = 'usuarios/registro_exitoso.html'

    def get(self, request):
        email = request.session.get('registro_email', 'tu correo electrónico')
        return render(request, self.template_name, {'email': email})


class VerificarCorreoView(View):
    """
    Procesa el enlace de verificación por correo.
    Valida el token, activa la cuenta en Django y sincroniza el estado con Keycloak.
    """
    template_name_success = 'usuarios/verificacion_exitosa.html'
    template_name_failed = 'usuarios/verificacion_fallida.html'

    def get(self, request, token):
        try:
            perfil = PerfilUsuario.objects.select_related('user').get(token_verificacion=token)
        except PerfilUsuario.DoesNotExist:
            return render(
                request,
                self.template_name_failed,
                {
                    'motivo': 'El enlace de verificación es inválido o el token ya ha sido utilizado.',
                    'token': token
                },
                status=400
            )

        if not perfil.is_token_valido(token):
            return render(
                request,
                self.template_name_failed,
                {
                    'motivo': 'El enlace de verificación ha expirado (validez superada).',
                    'email': perfil.user.email,
                    'token': token
                },
                status=400
            )

        # Activar cuenta en Django
        perfil.activar_cuenta()

        # Sincronizar estado en Keycloak
        if perfil.keycloak_id:
            try:
                kc_service = KeycloakAdminService()
                kc_service.marcar_email_verificado(perfil.keycloak_id)
            except Exception as e:
                logger.warning("No se pudo marcar email verificado en Keycloak para %s: %s", perfil.keycloak_id, e)

        messages.success(request, "¡Tu cuenta ha sido verificada y activada con éxito!")
        return render(
            request,
            self.template_name_success,
            {
                'user': perfil.user,
                'perfil': perfil
            }
        )


class ReenviarCorreoVerificacionView(View):
    """
    Permite solicitar un nuevo enlace de activación si el anterior no llegó o expiró.
    """
    template_name = 'usuarios/reenviar_correo.html'

    def get(self, request):
        form = ReenviarCorreoForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = ReenviarCorreoForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = User.objects.get(email__iexact=email)
            perfil, _ = PerfilUsuario.objects.get_or_create(user=user)

            if perfil.estado == EstadoUsuario.ACTIVO:
                messages.info(request, "Tu cuenta ya está verificada y activa.")
                return redirect('usuarios:registro')

            # Reenviar correo
            enviar_correo_activacion(user, perfil, request=request)
            request.session['registro_email'] = user.email
            messages.success(request, f"Se ha enviado un nuevo enlace de verificación a {user.email}.")
            return redirect('usuarios:registro_exitoso')

        return render(request, self.template_name, {'form': form})


class EstadoCuentaView(View):
    """
    Vista para consultar el estado actual de una cuenta (activo / pendiente).
    """
    template_name = 'usuarios/estado_cuenta.html'

    def get(self, request):
        username_or_email = request.GET.get('q', '').strip()
        perfil = None
        error = None

        if username_or_email:
            try:
                if '@' in username_or_email:
                    user = User.objects.select_related('perfil').get(email__iexact=username_or_email)
                else:
                    user = User.objects.select_related('perfil').get(username__iexact=username_or_email)
                perfil = getattr(user, 'perfil', None)

                # Sincronizar automáticamente con Keycloak si aún está pendiente en Django
                if perfil and perfil.estado != EstadoUsuario.ACTIVO and perfil.keycloak_id:
                    try:
                        kc_service = KeycloakAdminService()
                        kc_user = kc_service.obtener_usuario(perfil.keycloak_id)
                        if kc_user and kc_user.get('emailVerified'):
                            perfil.activar_cuenta()
                            perfil.refresh_from_db()
                    except Exception as e:
                        logger.warning("No se pudo sincronizar estado desde Keycloak: %s", e)

            except User.DoesNotExist:
                error = f"No se encontró ningún usuario con '{username_or_email}'."

        return render(request, self.template_name, {
            'query': username_or_email,
            'perfil': perfil,
            'error': error
        })



# ==========================================
# ENDPOINTS API REST (JSON)
# ==========================================

@method_decorator(csrf_exempt, name='dispatch')
class APIRegistroView(View):
    """
    Endpoint API REST para autoregistro de usuarios.
    POST /auth/api/registro/
    """
    def post(self, request):
        try:
            data = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido en el cuerpo de la petición'}, status=400)

        form = RegistroUsuarioForm(data)
        if not form.is_valid():
            return JsonResponse({'success': False, 'errors': form.errors}, status=400)

        user = form.save(commit=False)
        user.is_active = False
        user.set_password(form.cleaned_data['password'])
        user.save()

        # Keycloak Admin API
        kc_service = KeycloakAdminService()
        kc_res = kc_service.crear_usuario(
            username=user.username,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            password=form.cleaned_data['password'],
            required_actions=['VERIFY_EMAIL']
        )

        perfil = PerfilUsuario.objects.create(
            user=user,
            keycloak_id=kc_res.get('keycloak_id'),
            estado=EstadoUsuario.PENDIENTE_VERIFICACION,
            email_verificado=False
        )

        verification_url = enviar_correo_activacion(user, perfil, request=request)

        return JsonResponse({
            'success': True,
            'message': 'Usuario registrado exitosamente. Verificación por correo requerida.',
            'data': {
                'user_id': user.id,
                'username': user.username,
                'email': user.email,
                'estado': perfil.estado,
                'keycloak_id': perfil.keycloak_id,
                'verification_url': verification_url
            }
        }, status=201)


@method_decorator(csrf_exempt, name='dispatch')
class APIVerificarCorreoView(View):
    """
    Endpoint API REST para verificar token de correo.
    POST /auth/api/verificar-correo/
    Body: {"token": "..."}
    """
    def post(self, request):
        try:
            data = json.loads(request.body.decode('utf-8'))
            token = data.get('token')
        except Exception:
            token = request.POST.get('token')

        if not token:
            return JsonResponse({'success': False, 'error': 'Token no proporcionado.'}, status=400)

        try:
            perfil = PerfilUsuario.objects.select_related('user').get(token_verificacion=token)
        except PerfilUsuario.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Token inválido o ya utilizado.'}, status=404)

        if not perfil.is_token_valido(token):
            return JsonResponse({'success': False, 'error': 'El token ha expirado.'}, status=400)

        perfil.activar_cuenta()

        if perfil.keycloak_id:
            kc_service = KeycloakAdminService()
            kc_service.marcar_email_verificado(perfil.keycloak_id)

        return JsonResponse({
            'success': True,
            'message': 'Cuenta verificada y activada exitosamente.',
            'data': {
                'username': perfil.user.username,
                'email': perfil.user.email,
                'estado': perfil.estado,
                'email_verificado': perfil.email_verificado,
                'is_active': perfil.user.is_active
            }
        }, status=200)


@method_decorator(csrf_exempt, name='dispatch')
class APIReenviarVerificacionView(View):
    """
    Endpoint API REST para reenviar enlace de verificación.
    POST /auth/api/reenviar-verificacion/
    Body: {"email": "..."}
    """
    def post(self, request):
        try:
            data = json.loads(request.body.decode('utf-8'))
            email = data.get('email', '').strip().lower()
        except Exception:
            email = request.POST.get('email', '').strip().lower()

        if not email:
            return JsonResponse({'success': False, 'error': 'Email no proporcionado.'}, status=400)

        try:
            user = User.objects.select_related('perfil').get(email__iexact=email)
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'No existe usuario con ese correo.'}, status=404)

        perfil = getattr(user, 'perfil', None)
        if not perfil:
            perfil = PerfilUsuario.objects.create(user=user)

        if perfil.estado == EstadoUsuario.ACTIVO:
            return JsonResponse({
                'success': False,
                'message': 'Esta cuenta ya está activa y verificada.'
            }, status=400)

        verification_url = enviar_correo_activacion(user, perfil, request=request)

        return JsonResponse({
            'success': True,
            'message': f'Correo de verificación reenviado a {email}.',
            'data': {
                'email': email,
                'verification_url': verification_url
            }
        }, status=200)


@method_decorator(csrf_exempt, name='dispatch')
class APIEstadoUsuarioView(View):
    """
    Endpoint API REST para consultar estado de un usuario.
    GET /auth/api/estado/?q=username_or_email
    """
    def get(self, request):
        query = request.GET.get('q', '').strip()
        if not query:
            return JsonResponse({'error': 'Parámetro q requerido (username o email)'}, status=400)

        try:
            if '@' in query:
                user = User.objects.select_related('perfil').get(email__iexact=query)
            else:
                user = User.objects.select_related('perfil').get(username__iexact=query)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Usuario no encontrado'}, status=404)

        perfil = getattr(user, 'perfil', None)

        # Sincronizar automáticamente con Keycloak si aún está pendiente en Django
        if perfil and perfil.estado != EstadoUsuario.ACTIVO and perfil.keycloak_id:
            try:
                kc_service = KeycloakAdminService()
                kc_user = kc_service.obtener_usuario(perfil.keycloak_id)
                if kc_user and kc_user.get('emailVerified'):
                    perfil.activar_cuenta()
                    perfil.refresh_from_db()
            except Exception:
                pass

        return JsonResponse({

            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'estado': perfil.estado if perfil else 'SIN_PERFIL',
            'email_verificado': perfil.email_verificado if perfil else False,
            'keycloak_id': perfil.keycloak_id if perfil else None,
            'is_active': user.is_active
        })
