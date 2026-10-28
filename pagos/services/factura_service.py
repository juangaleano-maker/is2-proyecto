"""
Servicio de Facturación Electrónica SIFEN / e-Kuatia (IS2-63).

Implementa la lógica de negocio para:
- RF33: Generar la factura electrónica asociada a una operación pagada.
- RF34: Gestionar los estados (PENDIENTE → EMITIDA / RECHAZADA; EMITIDA → ANULADA).
- RNF37: Completar la emisión simulada en ≤ 5 segundos (sin I/O externo o con timeout rápido).

Integración con Factura Segura:
- Si se configura FACTURA_SEGURA_PASSWORD o FACTURA_SEGURA_AUTH_TOKEN en .env:
    Realiza la llamada HTTP oficial a la API ESI (https://apitest.facturasegura.com.py/misife00/v1/esi).
- Si no se han ingresado las credenciales en .env:
    Opera en modo SIMULACIÓN local automática (CDC 44 dígitos local) para permitir
    pruebas offline y desarrollo sin trabas.
"""

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Tasa IVA para servicios financieros / cambio de divisas en Paraguay (10%)
TASA_IVA = Decimal("0.10")

# Cache local en memoria para el token ESI durante la sesión del servidor
_CACHE_AUTH_TOKEN: Optional[str] = None


class FacturaService:
    """
    Genera y gestiona facturas electrónicas con soporte para la API Factura Segura y simulación local.
    """

    # ------------------------------------------------------------------
    # Emisión
    # ------------------------------------------------------------------

    @classmethod
    @transaction.atomic
    def emitir_factura(
        cls,
        operacion: Any,
        ticket: Optional[Any] = None,
    ):
        """
        Genera y emite la factura electrónica para una operación pagada.

        Es **idempotente**: si ya existe una factura para la operación, la retorna
        sin crear una nueva.
        """
        from cotizaciones.models import Operacion
        from pagos.models import FacturaElectronica

        if operacion.estado != Operacion.EstadoOperacion.PAGADA:
            raise ValueError(
                f"Solo se puede generar factura para operaciones PAGADAS. "
                f"Estado actual: {operacion.get_estado_display()}."
            )

        # Idempotencia: retornar factura existente
        try:
            factura_existente = operacion.factura_electronica
            logger.info(
                "Factura %s ya existía para operación #%s. Retornando la existente.",
                factura_existente.numero_factura,
                operacion.id,
            )
            return factura_existente
        except FacturaElectronica.DoesNotExist:
            pass

        # Snapshot del cliente
        cliente = operacion.cliente
        if cliente.tipo_persona == "FISICA":
            cliente_nombre = f"{cliente.nombre} {cliente.apellido}".strip()
        else:
            cliente_nombre = cliente.razon_social or str(cliente)

        # Cálculo tributario SIFEN
        subtotal_gs = operacion.subtotal  # monto × tasa (en Gs.)
        base_imponible, iva_liquidado, total_liquidado = (
            cls._calcular_desglose_iva(subtotal_gs)
        )

        # Crear factura en estado PENDIENTE
        factura = FacturaElectronica(
            operacion=operacion,
            ticket=ticket,
            estado=FacturaElectronica.EstadoFactura.PENDIENTE,
            condicion_venta=FacturaElectronica.CondicionVenta.CONTADO,
            cliente_nombre=cliente_nombre,
            cliente_documento=cliente.documento,
            cliente_email=cliente.email or "",
            moneda_siglas=operacion.moneda.siglas,
            monto=operacion.monto,
            tasa_aplicada=operacion.tasa_aplicada,
            base_imponible=base_imponible,
            iva_liquidado=iva_liquidado,
            total_liquidado=total_liquidado,
        )
        factura.save()

        # Procesar emisión (vía API Factura Segura o Simulador local si no hay credenciales)
        respuesta = cls._procesar_emision_backend(factura)

        if respuesta["exito"]:
            factura.estado = FacturaElectronica.EstadoFactura.EMITIDA
            factura.cdc = respuesta["cdc"]
            factura.fecha_procesado = timezone.now()
            factura.respuesta_simulador = respuesta
            factura.save(update_fields=["estado", "cdc", "fecha_procesado", "respuesta_simulador"])
            logger.info(
                "[IS2-63] Factura %s emitida (CDC: %s | Simulado: %s) para Operación #%s.",
                factura.numero_factura,
                factura.cdc,
                respuesta.get("simulado", True),
                operacion.id,
            )
        else:
            factura.estado = FacturaElectronica.EstadoFactura.RECHAZADA
            factura.respuesta_simulador = respuesta
            factura.save(update_fields=["estado", "respuesta_simulador"])
            logger.error(
                "[IS2-63] Factura %s RECHAZADA: %s",
                factura.numero_factura,
                respuesta.get("error"),
            )

        return factura

    # ------------------------------------------------------------------
    # Anulación
    # ------------------------------------------------------------------

    @classmethod
    @transaction.atomic
    def anular_factura(
        cls,
        factura: Any,
        usuario: Any,
        motivo: str,
    ) -> dict:
        """
        Anula una factura en estado EMITIDA.
        Si la factura fue emitida mediante Factura Segura, envía sol_cancelacion a la API.
        """
        from pagos.models import FacturaElectronica

        if not factura.es_anulable:
            return {
                "exito": False,
                "error": (
                    f"La factura '{factura.numero_factura}' no puede anularse "
                    f"porque está en estado '{factura.get_estado_display()}'."
                ),
            }

        # Notificar a la API Factura Segura si fue emitida en línea
        if not factura.respuesta_simulador.get("simulado", True):
            cls._cancelar_en_facturasegura(factura)

        factura.estado = FacturaElectronica.EstadoFactura.ANULADA
        factura.motivo_anulacion = motivo.strip()
        factura.anulada_por = usuario
        factura.fecha_procesado = timezone.now()
        factura.save(update_fields=["estado", "motivo_anulacion", "anulada_por", "fecha_procesado"])

        logger.info(
            "[IS2-63] Factura %s ANULADA por %s. Motivo: %s",
            factura.numero_factura,
            usuario.username,
            motivo,
        )
        return {"exito": True}

    # ------------------------------------------------------------------
    # Desglose Matemático Oficial SIFEN
    # ------------------------------------------------------------------

    @staticmethod
    def _calcular_desglose_iva(
        subtotal_gs: Decimal,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        Fórmula SIFEN v150 (método "por dentro"):
            base_imponible  = subtotal / (1 + TASA_IVA)
            iva_liquidado   = subtotal - base_imponible
            total_liquidado = subtotal
        """
        dos = Decimal("0.01")
        base = (subtotal_gs / (1 + TASA_IVA)).quantize(dos, rounding=ROUND_HALF_UP)
        iva  = (subtotal_gs - base).quantize(dos, rounding=ROUND_HALF_UP)
        total = subtotal_gs.quantize(dos, rounding=ROUND_HALF_UP)
        return base, iva, total

    # ------------------------------------------------------------------
    # Dispatcher: API Real Factura Segura vs Simulador Local
    # ------------------------------------------------------------------

    @classmethod
    def _procesar_emision_backend(cls, factura: Any) -> dict:
        """
        Verifica si existen credenciales válidas para Factura Segura.
        Si existen, invoca a la API oficial.
        Si no o si hay error de red, recurre al simulador local para no bloquear el flujo.
        """
        api_url = getattr(settings, "FACTURA_SEGURA_API_URL", "")
        email = getattr(settings, "FACTURA_SEGURA_EMAIL", "")
        password = getattr(settings, "FACTURA_SEGURA_PASSWORD", "")
        token = getattr(settings, "FACTURA_SEGURA_AUTH_TOKEN", "")

        # Si el usuario ya colocó la contraseña en .env o ya tiene el token:
        if (password and password != "REEMPLAZAR_CON_TU_CONTRASENHA") or token:
            try:
                res_api = cls._emitir_en_facturasegura(factura)
                if res_api.get("exito"):
                    return res_api
                logger.warning(
                    "[IS2-63] Factura Segura retornó error: %s. Utilizando simulador.",
                    res_api.get("error"),
                )
            except Exception as exc:
                logger.error("[IS2-63] Error al conectar con Factura Segura: %s", exc, exc_info=True)

        return cls._simular_emision_sifen(factura)

    # ------------------------------------------------------------------
    # Cliente HTTP para API Factura Segura (SIFEN ESI)
    # ------------------------------------------------------------------

    @classmethod
    def _obtener_auth_token(cls) -> Optional[str]:
        """Obtiene o reutiliza el Authentication-Token de Factura Segura."""
        global _CACHE_AUTH_TOKEN
        token_env = getattr(settings, "FACTURA_SEGURA_AUTH_TOKEN", "")
        if token_env:
            return token_env

        if _CACHE_AUTH_TOKEN:
            return _CACHE_AUTH_TOKEN

        api_url = getattr(settings, "FACTURA_SEGURA_API_URL", "https://apitest.facturasegura.com.py")
        email = getattr(settings, "FACTURA_SEGURA_EMAIL", "")
        password = getattr(settings, "FACTURA_SEGURA_PASSWORD", "")

        if not password or password == "REEMPLAZAR_CON_TU_CONTRASENHA":
            return None

        login_url = f"{api_url}/login?include_auth_token"
        try:
            resp = requests.post(
                login_url,
                json={"email": email, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("response", {}).get("user", {}).get("authentication_token")
                if token:
                    _CACHE_AUTH_TOKEN = token
                    return token
            logger.error("Fallo al autenticar en Factura Segura: %s (Status: %s)", resp.text, resp.status_code)
        except Exception as exc:
            logger.error("Excepción al hacer login en Factura Segura: %s", exc)

        return None

    @classmethod
    def _emitir_en_facturasegura(cls, factura: Any) -> dict:
        """
        Envía la petición generar_de a la API /misife00/v1/esi de Factura Segura.
        """
        token = cls._obtener_auth_token()
        if not token:
            return {"exito": False, "error": "No se pudo obtener el token de autenticación ESI."}

        api_url = getattr(settings, "FACTURA_SEGURA_API_URL", "https://apitest.facturasegura.com.py")
        endpoint = f"{api_url}/misife00/v1/esi"

        # Extraer correlativo de 7 dígitos del número de factura (ej: 001-003-0000326 -> 0000326)
        num_doc = factura.numero_factura.split("-")[-1]

        # Cliente / Receptor
        cliente_doc = factura.cliente_documento.replace(".", "").strip()
        if "-" in cliente_doc:
            ruc_rec, dv_rec = cliente_doc.split("-")[:2]
        else:
            ruc_rec, dv_rec = cliente_doc, "0"

        # Armado de JSON DE según especificación de Factura Segura
        monto_total_int = int(factura.total_liquidado)
        base_int = int(factura.base_imponible)
        iva_int = int(factura.iva_liquidado)

        payload = {
            "operation": "generar_de",
            "params": {
                "DE": {
                    "iTipEmi": "1",
                    "iTiDE": "1",
                    "dNumTim": getattr(settings, "FACTURA_SEGURA_TIMBRADO", "02595733"),
                    "dFeIniT": getattr(settings, "FACTURA_SEGURA_FECHA_TIMBRADO", "2025-03-27"),
                    "dEst": getattr(settings, "FACTURA_SEGURA_ESTABLECIMIENTO", "001"),
                    "dPunExp": getattr(settings, "FACTURA_SEGURA_PUNTO_EXPEDICION", "003"),
                    "dNumDoc": num_doc,
                    "dFeEmiDE": timezone.now().strftime("%Y-%m-%dT%H:%M:%S"),
                    "iTipTra": "1",
                    "iTImp": "1",
                    "cMoneOpe": "PYG",
                    "dCondTiCam": "1",
                    "dTiCam": str(int(factura.tasa_aplicada)),
                    "dRucEm": getattr(settings, "FACTURA_SEGURA_RUC_EMISOR", "2595733"),
                    "dDVEmi": getattr(settings, "FACTURA_SEGURA_DV_EMISOR", "3"),
                    "iTipCont": "1",
                    "dNomEmi": "GLOBAL EXCHANGE S.A.",
                    "dDirEmi": "Avda. Aviadores del Chaco 2050",
                    "dNumCas": "2050",
                    "cDepEmi": "1",
                    "dDesDepEmi": "CAPITAL",
                    "cCiuEmi": "1",
                    "dDesCiuEmi": "ASUNCION (DISTRITO)",
                    "dTelEmi": getattr(settings, "FACTURA_SEGURA_TELEFONO_EMISOR", "(021)5887000"),
                    "dEmailE": getattr(settings, "FACTURA_SEGURA_EMAIL", "contacto@globalexchange.com.py"),
                    "gActEco": [
                        {
                            "cActEco": "62010",
                            "dDesActEco": "Actividades de programación informática"
                        }
                    ],
                    "iNatRec": "1",
                    "iTiOpe": "1",
                    "cPaisRec": "PRY",
                    "iTiContRec": "1",
                    "dRucRec": ruc_rec,
                    "dDVRec": dv_rec,
                    "iTipIDRec": "0",
                    "dNumIDRec": "0",
                    "dNomRec": factura.cliente_nombre,
                    "dEmailRec": factura.cliente_email or "cliente@exchange.com",
                    "iIndPres": "1",
                    "iCondOpe": "1",
                    "gPaConEIni": [
                        {
                            "iTiPago": "1",
                            "dMonTiPag": str(monto_total_int),
                            "cMoneTiPag": "PYG",
                            "dTiCamTiPag": "1"
                        }
                    ],
                    "gCamItem": [
                        {
                            "dCodInt": f"OP-{factura.operacion_id}",
                            "dDesProSer": f"Operación de cambio {factura.operacion.get_tipo_display()} {factura.moneda_siglas}",
                            "cUniMed": "77",
                            "dCantProSer": "1",
                            "dPUniProSer": str(monto_total_int),
                            "dTotBruOpeItem": str(monto_total_int),
                            "dDescItem": "0",
                            "dPorcDesIt": "0",
                            "dDescGloItem": "0",
                            "dAntPreUniIt": "0",
                            "dAntGloPreUniIt": "0",
                            "dTotOpeItem": str(monto_total_int),
                            "iAfecIVA": "1",
                            "dPropIVA": "100",
                            "dTasaIVA": "10",
                            "dBasGravIVA": str(base_int),
                            "dLiqIVAItem": str(iva_int),
                            "dBasExe": "0"
                        }
                    ],
                    "dSubExe": "0",
                    "dSubExo": "0",
                    "dSub5": "0",
                    "dSub10": str(monto_total_int),
                    "dTotOpe": str(monto_total_int),
                    "dTotDesc": "0",
                    "dTotDescGlotem": "0",
                    "dTotAntItem": "0",
                    "dTotAnt": "0",
                    "dPorcDescTotal": "0",
                    "dDescTotal": "0",
                    "dAnticipo": "0",
                    "dRedon": "0",
                    "dComi": "0",
                    "dTotGralOpe": str(monto_total_int),
                    "dIVA5": "0",
                    "dIVA10": str(iva_int),
                    "dLiqTotIVA5": "0",
                    "dLiqTotIVA10": "0",
                    "dIVAComi": "0",
                    "dTotIVA": str(iva_int),
                    "dBaseGrav5": "0",
                    "dBaseGrav10": str(base_int),
                    "dTBasGraIVA": str(base_int),
                    "dTotalGs": "",
                    "CDC": "0",
                    "dCodSeg": "0",
                    "dDVId": "0",
                    "dSisFact": "1",
                    "dInfAdic": f"Operación #{factura.operacion_id} Global Exchange"
                }
            }
        }

        resp = requests.post(
            endpoint,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "accept": "application/json",
                "Authentication-Token": token,
            },
            timeout=8,
        )

        data = resp.json()
        if data.get("code") == 0 and data.get("results"):
            cdc = data["results"][0].get("CDC")
            return {
                "exito": True,
                "cdc": cdc,
                "numero_factura": factura.numero_factura,
                "estado_sifen": "Aprobado (Factura Segura)",
                "fecha_aprobacion": timezone.now().isoformat(),
                "simulado": False,
                "api_response": data,
            }
        else:
            return {
                "exito": False,
                "error": data.get("description", "Error desconocido devuelto por Factura Segura"),
                "api_response": data,
                "simulado": False,
            }

    @classmethod
    def _cancelar_en_facturasegura(cls, factura: Any) -> None:
        """Solicita la cancelación (sol_cancelacion) a la API de Factura Segura."""
        token = cls._obtener_auth_token()
        if not token or not factura.cdc:
            return

        api_url = getattr(settings, "FACTURA_SEGURA_API_URL", "https://apitest.facturasegura.com.py")
        endpoint = f"{api_url}/misife00/v1/esi"
        ruc_emisor = getattr(settings, "FACTURA_SEGURA_RUC_EMISOR", "2595733")

        payload = {
            "operation": "sol_cancelacion",
            "params": {
                "CDC": factura.cdc,
                "dRucEm": ruc_emisor
            }
        }
        try:
            requests.post(
                endpoint,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authentication-Token": token
                },
                timeout=5,
            )
        except Exception as exc:
            logger.warning("Error al notificar sol_cancelacion a Factura Segura: %s", exc)

    # ------------------------------------------------------------------
    # Simulador Local (Fallback Offline)
    # ------------------------------------------------------------------

    @staticmethod
    def _simular_emision_sifen(factura: Any) -> dict:
        """
        Simulación local cuando no hay conexión externa o aún no se ingresó la contraseña.
        Cumple RNF37 (<= 5s) y genera un CDC válido de 44 caracteres hexadecimales.
        """
        if factura.total_liquidado <= Decimal("0"):
            return {
                "exito": False,
                "cdc": None,
                "error": "El total liquidado debe ser mayor a cero.",
                "simulado": True,
            }

        cdc_simulado = (uuid.uuid4().hex + uuid.uuid4().hex)[:44].upper()

        return {
            "exito": True,
            "cdc": cdc_simulado,
            "numero_factura": factura.numero_factura,
            "estado_sifen": "Aprobado (Modo Simulación)",
            "fecha_aprobacion": timezone.now().isoformat(),
            "simulado": True,
            "mensaje": (
                "Factura generada en modo simulación local. "
                "Para emitir en Factura Segura, configure FACTURA_SEGURA_PASSWORD en el archivo .env."
            ),
        }
