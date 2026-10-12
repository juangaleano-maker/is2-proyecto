"""
Interfaz abstracta para pasarelas de pago (Strategy Pattern).

Toda pasarela de pago debe implementar esta interfaz, lo que permite
agregar Stripe, SIPAP u otras sin modificar la lógica de negocio existente.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class PasarelaPago(ABC):
    """
    Clase base abstracta para pasarelas de pago.

    Define el contrato que deben cumplir todas las implementaciones
    de pasarelas (Stripe, SIPAP, etc.).

    Uso::

        class MiPasarela(PasarelaPago):
            def crear_pago(self, operacion, **kwargs):
                ...
            def confirmar_pago(self, referencia, **kwargs):
                ...
    """

    @abstractmethod
    def crear_pago(self, operacion: Any, **kwargs) -> Dict[str, Any]:
        """
        Inicia el proceso de pago para una operación.

        Args:
            operacion: Instancia de ``cotizaciones.Operacion``.
            **kwargs: Parámetros adicionales específicos de la pasarela.

        Returns:
            Diccionario con al menos ``{'exito': bool, 'referencia': str}``.

        Raises:
            ValueError: Si la operación no está en estado válido para pagar.
        """

    @abstractmethod
    def confirmar_pago(self, referencia: str, **kwargs) -> Dict[str, Any]:
        """
        Confirma (o verifica) un pago previamente iniciado.

        Args:
            referencia: ID o código externo que identifica el pago.
            **kwargs: Parámetros adicionales.

        Returns:
            Diccionario con ``{'exito': bool, 'estado': str}``.
        """

    def nombre_pasarela(self) -> str:
        """Retorna el nombre identificador de la pasarela."""
        return self.__class__.__name__
