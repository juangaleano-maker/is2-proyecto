from django.db import models

class Moneda(models.Model):
    """
    Representa una divisa o moneda que puede operarse en la plataforma.
    El campo 'activa' controla su disponibilidad sin eliminar su historial.
    """
    nombre = models.CharField(max_length=50, unique=True, verbose_name="Nombre de la moneda")
    siglas = models.CharField(max_length=10, unique=True, verbose_name="Siglas (ej. USD, PYG)")
    activa = models.BooleanField(default=True, verbose_name="¿Moneda activa?")

    class Meta:
        verbose_name = "Moneda"
        verbose_name_plural = "Monedas"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} ({self.siglas})"

    def tiene_cotizaciones(self):
        """
        Verifica si la moneda tiene cotizaciones asociadas.
        Diseñado para ser escalable:
        1. Si se define un atributo '_tiene_cotizaciones' (para mocks o pruebas), lo respeta.
        2. Si existe la relación inversa 'cotizaciones' o 'cotizacion_set', consulta si existen registros.
        3. Si existen modelos relacionados cuyo nombre contenga 'cotiz', consulta su existencia.
        4. Si no existen cotizaciones o el modelo aún no ha sido migrado, retorna False de forma segura.
        """
        if hasattr(self, '_tiene_cotizaciones'):
            return bool(self._tiene_cotizaciones)

        if hasattr(self, 'cotizaciones'):
            try:
                return self.cotizaciones.exists()
            except Exception:
                pass

        if hasattr(self, 'cotizacion_set'):
            try:
                return self.cotizacion_set.exists()
            except Exception:
                pass

        for related_object in self._meta.related_objects:
            if 'cotiz' in related_object.related_model.__name__.lower():
                accessor_name = related_object.get_accessor_name()
                manager = getattr(self, accessor_name, None)
                if manager and hasattr(manager, 'exists'):
                    try:
                        if manager.exists():
                            return True
                    except Exception:
                        pass

        return False
