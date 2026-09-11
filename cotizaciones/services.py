from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Any, Optional
from .models import Cotizacion


def obtener_monedas_disponibles() -> list:
    """
    Retorna la lista de tuplas (codigo, nombre) de monedas configuradas
    en el sistema o presentes en las cotizaciones.
    """
    return list(Cotizacion.MONEDAS)


def redondear_monto(monto: Decimal, moneda: str) -> Decimal:
    """
    Redondea el monto según la moneda (PYG suele manejarse entero o 2 decimales, otras con 2 decimales).
    """
    if moneda == 'PYG':
        # En Guaraníes se redondea típicamente a entero o 2 decimales
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
    
    moneda_origen = str(moneda_origen).upper().strip()
    moneda_destino = str(moneda_destino).upper().strip()
    
    monedas_validas = dict(Cotizacion.MONEDAS)
    if moneda_origen not in monedas_validas:
        raise ValueError(f"La moneda de origen '{moneda_origen}' no es válida en el sistema.")
    if moneda_destino not in monedas_validas:
        raise ValueError(f"La moneda de destino '{moneda_destino}' no es válida en el sistema.")
    
    # Caso 1: Misma moneda
    if moneda_origen == moneda_destino:
        return {
            'exito': True,
            'moneda_origen': moneda_origen,
            'moneda_origen_nombre': monedas_validas.get(moneda_origen, moneda_origen),
            'moneda_destino': moneda_destino,
            'moneda_destino_nombre': monedas_validas.get(moneda_destino, moneda_destino),
            'monto_origen': monto_decimal,
            'monto_destino': redondear_monto(monto_decimal, moneda_destino),
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
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
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
            'moneda_origen': moneda_origen,
            'moneda_origen_nombre': monedas_validas.get(moneda_origen, moneda_origen),
            'moneda_destino': moneda_destino,
            'moneda_destino_nombre': monedas_validas.get(moneda_destino, moneda_destino),
            'monto_origen': monto_decimal,
            'monto_destino': redondear_monto(monto_destino, moneda_destino),
            'tasa_aplicada': tasa,
            'tipo_operacion': 'compra_directa',
            'descripcion_tasa': f"1 {moneda_origen} = {tasa} {moneda_destino} (Precio Compra vigente)",
            'fecha_tasa': cot_directa.fecha,
            'cotizacion_id': cot_directa.id,
            'es_simulacion': True,
            'aviso': 'Simulación informativa. No se genera ningún débito ni crédito en sus cuentas ni saldos.',
        }
    
    # Caso 3: Par inverso existente (moneda_destino -> moneda_origen)
    cot_inversa = (
        Cotizacion.objects.filter(
            moneda_origen=moneda_destino,
            moneda_destino=moneda_origen,
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
            'moneda_origen': moneda_origen,
            'moneda_origen_nombre': monedas_validas.get(moneda_origen, moneda_origen),
            'moneda_destino': moneda_destino,
            'moneda_destino_nombre': monedas_validas.get(moneda_destino, moneda_destino),
            'monto_origen': monto_decimal,
            'monto_destino': redondear_monto(monto_destino, moneda_destino),
            'tasa_aplicada': tasa_efectiva,
            'tasa_referencia_inversa': tasa_venta,
            'tipo_operacion': 'venta_inversa',
            'descripcion_tasa': f"1 {moneda_destino} = {tasa_venta} {moneda_origen} (Precio Venta vigente)",
            'fecha_tasa': cot_inversa.fecha,
            'cotizacion_id': cot_inversa.id,
            'es_simulacion': True,
            'aviso': 'Simulación informativa. No se genera ningún débito ni crédito en sus cuentas ni saldos.',
        }
    
    # Caso 4: Triangulación a través de monedas puente (PYG o USD)
    for puente in ['PYG', 'USD']:
        if puente not in (moneda_origen, moneda_destino):
            try:
                # Paso A: origen -> puente
                sim_paso_1 = simular_conversion(moneda_origen, puente, monto_decimal)
                # Paso B: puente -> destino
                sim_paso_2 = simular_conversion(puente, moneda_destino, sim_paso_1['monto_destino'])
                
                tasa_cruzada = (sim_paso_2['monto_destino'] / monto_decimal).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
                return {
                    'exito': True,
                    'moneda_origen': moneda_origen,
                    'moneda_origen_nombre': monedas_validas.get(moneda_origen, moneda_origen),
                    'moneda_destino': moneda_destino,
                    'moneda_destino_nombre': monedas_validas.get(moneda_destino, moneda_destino),
                    'monto_origen': monto_decimal,
                    'monto_destino': redondear_monto(sim_paso_2['monto_destino'], moneda_destino),
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
        f"No se encontró una cotización activa vigente entre {moneda_origen} y {moneda_destino}."
    )
