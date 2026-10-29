"""
Formularios del módulo de pagos.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import ComprobanteSIPAP

TIPOS_MIME_PERMITIDOS = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "application/pdf",
}
LIMITE_MB = 5


class ComprobanteSIPAPForm(forms.ModelForm):
    """
    Formulario para que el cliente adjunte su comprobante de pago SIPAP.

    Valida:
    - Tipo de archivo: solo JPG, PNG, PDF.
    - Tamaño máximo: 5 MB.
    """

    class Meta:
        model = ComprobanteSIPAP
        fields = ["archivo"]
        widgets = {
            "archivo": forms.ClearableFileInput(
                attrs={
                    "accept": ".jpg,.jpeg,.png,.pdf",
                    "class": "form-control",
                    "id": "id_archivo_comprobante",
                }
            )
        }
        labels = {"archivo": "Comprobante de pago (JPG, PNG o PDF — máx. 5 MB)"}

    def clean_archivo(self):
        """Valida tipo MIME y tamaño del archivo."""
        archivo = self.cleaned_data.get("archivo")
        if not archivo:
            raise ValidationError("Debes adjuntar un comprobante de pago.")

        # Validar tipo de contenido
        content_type = getattr(archivo, "content_type", "")
        if content_type not in TIPOS_MIME_PERMITIDOS:
            raise ValidationError(
                f"Tipo de archivo no permitido: '{content_type}'. "
                f"Solo se aceptan JPG, PNG y PDF."
            )

        # Validar tamaño
        if archivo.size > LIMITE_MB * 1024 * 1024:
            raise ValidationError(
                f"El archivo supera el límite de {LIMITE_MB} MB "
                f"(tamaño: {archivo.size / (1024*1024):.2f} MB)."
            )

        return archivo


class RechazarComprobanteSIPAPForm(forms.Form):
    """
    Formulario para que el cajero registre el motivo de rechazo del comprobante.
    """

    motivo = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control",
                "id": "id_motivo_rechazo",
                "placeholder": "Describa el motivo del rechazo...",
            }
        ),
        label="Motivo de rechazo",
        min_length=10,
        max_length=500,
        error_messages={
            "min_length": "El motivo debe tener al menos 10 caracteres.",
            "required": "Debe ingresar el motivo del rechazo.",
        },
    )


class AnularFacturaForm(forms.Form):
    """
    Formulario para que un operador/admin ingrese el motivo de anulación
    de una Factura Electrónica (IS2-63 / RF34).
    """

    motivo = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control",
                "id": "id_motivo_anulacion",
                "placeholder": "Indique detalladamente el motivo de la anulación (mín. 10 caracteres)...",
            }
        ),
        label="Motivo de anulación",
        min_length=10,
        max_length=500,
        error_messages={
            "min_length": "El motivo de anulación debe tener al menos 10 caracteres.",
            "required": "Debe ingresar el motivo de anulación.",
        },
    )

