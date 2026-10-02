from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Any, Optional
from .models import Cotizacion
from monedas.models import Moneda


def obtener_monedas_disponibles() -> list:
    """
    Retorna la lista de tuplas (codigo, nombre) de monedas activas configuradas
    en el sistema para poblar los selectores del simulador.
    """
    return list(Moneda.objects.filter(activa=True).order_by('siglas').values_list('siglas', 'nombre'))


def redondear_monto(monto: Decimal, moneda: str) -> Decimal:
    """
    Redondea el monto según la moneda (PYG suele manejarse entero o 2 decimales, otras con 2 decimales).
    """
    if str(moneda).upper() == 'PYG':
        return monto.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return monto.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def simular_conversion(
    moneda_origen: str,
    moneda_destino: str,
    monto: Any
) -> Dict[str, Any]:
    """
    Simula la conversión entre dos monedas utilizando la tasa de cambio vigente.
    
    Criterios de Aceptación (IS2-10):
    1. Permite seleccionar moneda de origen, moneda destino y monto.
    2. El resultado se calcula con la tasa vigente al momento de la simulación.
    3. La simulación NO genera ningún movimiento real ni afecta saldos (operación en memoria / pura).
    
    Retorna un diccionario con los resultados del cálculo o levanta ValueError.
    """
    # 1. Validación de monto
    if monto is None or str(monto).strip() == '':
        raise ValueError("Debe ingresar un monto a simular.")
    
    try:
        monto_decimal = Decimal(str(monto))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("El monto ingresado no es un número válido.")
    
    if monto_decimal <= Decimal('0'):
        raise ValueError("El monto a simular debe ser mayor a cero.")
    
    moneda_origen_cod = str(moneda_origen).upper().strip()
    moneda_destino_cod = str(moneda_destino).upper().strip()
    
    origen_obj = Moneda.objects.filter(siglas__iexact=moneda_origen_cod, activa=True).first()
    if not origen_obj:
        raise ValueError(f"La moneda de origen '{moneda_origen_cod}' no es válida en el sistema.")
        
    destino_obj = Moneda.objects.filter(siglas__iexact=moneda_destino_cod, activa=True).first()
    if not destino_obj:
        raise ValueError(f"La moneda de destino '{moneda_destino_cod}' no es válida en el sistema.")
    
    # Caso 1: Misma moneda
    if origen_obj.pk == destino_obj.pk or origen_obj.siglas == destino_obj.siglas:
        return {
            'exito': True,
            'moneda_origen': origen_obj.siglas,
            'moneda_origen_nombre': origen_obj.nombre,
            'moneda_destino': destino_obj.siglas,
            'moneda_destino_nombre': destino_obj.nombre,
            'monto_origen': monto_decimal,
            'monto_destino': redondear_monto(monto_decimal, destino_obj.siglas),
            'tasa_aplicada': Decimal('1.0'),
            'tipo_operacion': 'paridad',
            'descripcion_tasa': 'Misma moneda (conversión 1:1)',
            'fecha_tasa': None,
            'cotizacion_id': None,
            'es_simulacion': True,
            'aviso': 'Simulación informativa. No se genera ningún débito ni crédito en sus cuentas ni saldos.',
        }
    
    # Caso 2: Par directo existente (moneda_origen -> moneda_destino)
    cot_directa = (
        Cotizacion.objects.filter(
            moneda_origen=origen_obj,
            moneda_destino=destino_obj,
            activo=True
        )
        .order_by('-fecha')
        .first()
    )
    
    if cot_directa:
        # Tasa de compra: la entidad compra la moneda origen pagando en moneda destino
        tasa = cot_directa.compra
        monto_destino = monto_decimal * tasa
        return {
            'exito': True,
            'moneda_origen': origen_obj.siglas,
            'moneda_origen_nombre': origen_obj.nombre,
            'moneda_destino': destino_obj.siglas,
            'moneda_destino_nombre': destino_obj.nombre,
            'monto_origen': monto_decimal,
            'monto_destino': redondear_monto(monto_destino, destino_obj.siglas),
            'tasa_aplicada': tasa,
            'tipo_operacion': 'compra_directa',
            'descripcion_tasa': f"1 {origen_obj.siglas} = {tasa} {destino_obj.siglas} (Precio Compra vigente)",
            'fecha_tasa': cot_directa.fecha,
            'cotizacion_id': cot_directa.id,
            'es_simulacion': True,
            'aviso': 'Simulación informativa. No se genera ningún débito ni crédito en sus cuentas ni saldos.',
        }
    
    # Caso 3: Par inverso existente (moneda_destino -> moneda_origen)
    cot_inversa = (
        Cotizacion.objects.filter(
            moneda_origen=destino_obj,
            moneda_destino=origen_obj,
            activo=True
        )
        .order_by('-fecha')
        .first()
    )
    
    if cot_inversa:
        # La entidad vende la moneda destino a precio de venta
        tasa_venta = cot_inversa.venta
        if tasa_venta <= Decimal('0'):
            raise ValueError("La cotización vigente tiene una tasa de venta no válida.")
        monto_destino = monto_decimal / tasa_venta
        tasa_efectiva = (Decimal('1') / tasa_venta).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        return {
            'exito': True,
            'moneda_origen': origen_obj.siglas,
            'moneda_origen_nombre': origen_obj.nombre,
            'moneda_destino': destino_obj.siglas,
            'moneda_destino_nombre': destino_obj.nombre,
            'monto_origen': monto_decimal,
            'monto_destino': redondear_monto(monto_destino, destino_obj.siglas),
            'tasa_aplicada': tasa_efectiva,
            'tasa_referencia_inversa': tasa_venta,
            'tipo_operacion': 'venta_inversa',
            'descripcion_tasa': f"1 {destino_obj.siglas} = {tasa_venta} {origen_obj.siglas} (Precio Venta vigente)",
            'fecha_tasa': cot_inversa.fecha,
            'cotizacion_id': cot_inversa.id,
            'es_simulacion': True,
            'aviso': 'Simulación informativa. No se genera ningún débito ni crédito en sus cuentas ni saldos.',
        }
    
    # Caso 4: Triangulación a través de monedas puente (PYG o USD)
    for puente in ['PYG', 'USD']:
        if puente not in (origen_obj.siglas, destino_obj.siglas):
            try:
                sim_paso_1 = simular_conversion(origen_obj.siglas, puente, monto_decimal)
                sim_paso_2 = simular_conversion(puente, destino_obj.siglas, sim_paso_1['monto_destino'])
                
                tasa_cruzada = (sim_paso_2['monto_destino'] / monto_decimal).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
                return {
                    'exito': True,
                    'moneda_origen': origen_obj.siglas,
                    'moneda_origen_nombre': origen_obj.nombre,
                    'moneda_destino': destino_obj.siglas,
                    'moneda_destino_nombre': destino_obj.nombre,
                    'monto_origen': monto_decimal,
                    'monto_destino': redondear_monto(sim_paso_2['monto_destino'], destino_obj.siglas),
                    'tasa_aplicada': tasa_cruzada,
                    'tipo_operacion': f'triangulada_via_{puente.lower()}',
                    'descripcion_tasa': f"Tasa cruzada triangulada a través de {puente}",
                    'fecha_tasa': sim_paso_2['fecha_tasa'] or sim_paso_1['fecha_tasa'],
                    'cotizacion_id': None,
                    'es_simulacion': True,
                    'aviso': 'Simulación informativa. No se genera ningún débito ni crédito en sus cuentas ni saldos.',
                }
            except ValueError:
                continue
    
    # Si no se encontró ninguna cotización aplicable
    raise ValueError(
        f"No se encontró una cotización activa vigente entre {origen_obj.siglas} y {destino_obj.siglas}."
    )


# =======================================================================
# Cancelación de Transacción por Cambio de Cotización (Historia IS2-52)
# =======================================================================

def obtener_tasa_vigente_operacion(moneda, tipo: str) -> tuple[Optional[Decimal], Optional[Cotizacion]]:
    """
    Obtiene la cotización y tasa vigente en el sistema para la moneda y tipo de operación especificados.
    Para tipo COMPRA se toma el precio de compra; para VENTA, el precio de venta.
    """
    tipo_norm = str(tipo).upper()
    
    # 1. Buscar cotización donde la divisa sea moneda_origen
    cotizacion = (
        Cotizacion.objects.filter(moneda_origen=moneda, activo=True)
        .order_by('-fecha')
        .first()
    )
    if cotizacion:
        tasa = cotizacion.compra if tipo_norm == 'COMPRA' else cotizacion.venta
        return tasa, cotizacion

    # 2. Buscar cotización donde la divisa sea moneda_destino (par inverso)
    cotizacion_inv = (
        Cotizacion.objects.filter(moneda_destino=moneda, activo=True)
        .order_by('-fecha')
        .first()
    )
    if cotizacion_inv:
        tasa = cotizacion_inv.compra if tipo_norm == 'COMPRA' else cotizacion_inv.venta
        return tasa, cotizacion_inv

    return None, None


def verificar_cambio_cotizacion(operacion) -> Dict[str, Any]:
    """
    Criterio 1 y 2 (IS2-52):
    Durante el proceso de pago/confirmación, valida si la cotización de la moneda
    cambió respecto al inicio de la operación (tasa_aplicada).
    Si cambió, genera los datos para la notificación al usuario.
    """
    tasa_vigente, cotizacion_vigente = obtener_tasa_vigente_operacion(
        moneda=operacion.moneda,
        tipo=operacion.tipo
    )

    tasa_inicial = operacion.tasa_aplicada

    if tasa_vigente is None:
        # Si no hay nueva cotización registrada, se asume que no cambió
        return {
            'cambio': False,
            'tasa_inicial': tasa_inicial,
            'tasa_vigente': tasa_inicial,
            'diferencia': Decimal('0.00'),
            'porcentaje_variacion': Decimal('0.00'),
            'cotizacion_vigente': None,
            'notificacion': None,
        }

    ha_cambiado = (tasa_vigente != tasa_inicial)
    diferencia = (tasa_vigente - tasa_inicial).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    porcentaje = Decimal('0.00')
    if tasa_inicial > Decimal('0'):
        porcentaje = ((diferencia / tasa_inicial) * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    notificacion = None
    if ha_cambiado:
        sentido = "subió" if diferencia > Decimal('0') else "bajó"
        notificacion = (
            f"La cotización de {operacion.moneda.siglas} cambió respecto al inicio de la operación: "
            f"pasó de {tasa_inicial} a {tasa_vigente} ({sentido} {abs(diferencia)} / {abs(porcentaje)}%). "
            f"Puedes cancelar la transacción sin ningún cargo o aceptar la nueva cotización."
        )

    return {
        'cambio': ha_cambiado,
        'tasa_inicial': tasa_inicial,
        'tasa_vigente': tasa_vigente,
        'diferencia': diferencia,
        'porcentaje_variacion': porcentaje,
        'cotizacion_vigente': cotizacion_vigente,
        'notificacion': notificacion,
    }


def cancelar_operacion_por_cambio_tasa(operacion, motivo: str = "Cambio de cotización", usuario=None):
    """
    Criterio 3 (IS2-52):
    Permite al usuario cancelar la transacción sin que se registre ningún cargo
    ni movimiento financiero definitivo.
    """
    from .models import Operacion

    if operacion.estado == Operacion.EstadoOperacion.PAGADA:
        raise ValueError("No se puede cancelar una transacción que ya ha sido pagada y completada.")

    if operacion.estado == Operacion.EstadoOperacion.CANCELADA:
        return operacion

    # Cancelar la operación
    operacion.estado = Operacion.EstadoOperacion.CANCELADA
    # Criterio 3: Sin que se registre ningún cargo ni movimiento definitivo
    operacion.comision = Decimal('0.00')
    operacion.save()

    return operacion


def confirmar_y_pagar_operacion(operacion, aceptar_cambio_tasa: bool = False):
    """
    Procesa el pago y confirmación definitiva de la operación.
    Si la tasa cambió y el usuario no aceptó expresamente la nueva cotización,
    rechaza la confirmación para proteger al usuario.
    """
    from .models import Operacion

    if operacion.estado != Operacion.EstadoOperacion.PENDIENTE:
        raise ValueError(f"No se puede confirmar una operación en estado '{operacion.get_estado_display()}'.")

    validacion = verificar_cambio_cotizacion(operacion)
    if validacion['cambio']:
        if not aceptar_cambio_tasa:
            raise ValueError(
                "La cotización ha cambiado desde el inicio de la operación. "
                "Debe aceptar la nueva cotización o cancelar la transacción sin cargos."
            )
        # Si aceptó la nueva tasa, actualizar tasa_aplicada
        operacion.tasa_aplicada = validacion['tasa_vigente']
        # Recalcular comisión según la nueva tasa (2% estándar o paramétrico)
        operacion.comision = (operacion.monto * Decimal('0.02')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    operacion.estado = Operacion.EstadoOperacion.PAGADA
    operacion.save()
    return operacion

