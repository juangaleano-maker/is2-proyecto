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


def obtener_clientes_asignados_usuario(user):
    """
    Retorna el QuerySet de clientes asignados a un usuario autenticado.
    - Personal administrativo u operadores: tienen acceso a todos los clientes activos.
    - Clientes / usuarios asignados: únicamente aquellos clientes vinculados explícitamente.
    """
    from clientes.models import Cliente
    from agregar_usuario.models import UsuarioCliente
    from django.db import models

    if not user or not user.is_authenticated:
        return Cliente.objects.none()

    user_roles = set(getattr(user, 'roles', []))
    if hasattr(user, 'groups'):
        user_roles.update(user.groups.values_list('name', flat=True))
    roles_gestion = {'admin', 'supervisor', 'operador', 'empleado'}
    es_personal = bool(user_roles.intersection(roles_gestion)) or getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)

    if es_personal:
        return Cliente.objects.filter(activo=True).order_by('nombre', 'razon_social')


    user_email = user.email or user.username
    clientes_ids = UsuarioCliente.objects.filter(email__iexact=user_email).values_list('cliente_id', flat=True)
    return Cliente.objects.filter(
        models.Q(id__in=clientes_ids) | models.Q(email__iexact=user_email),
        activo=True
    ).order_by('nombre', 'razon_social')


def obtener_tasa_sugerida(moneda, tipo='VENTA'):
    """
    Busca la tasa vigente en Cotizacion para la moneda especificada.
    Para una VENTA (el cliente vende divisa a la casa de cambio):
    sugiere la tasa de compra de la casa (precio al que la entidad adquiere la divisa).
    Para una COMPRA: sugiere la tasa de venta de la casa.
    """
    from .models import Cotizacion
    from monedas.models import Moneda

    if isinstance(moneda, (int, str)) and str(moneda).isdigit():
        moneda_obj = Moneda.objects.filter(id=int(moneda), activa=True).first()
    elif isinstance(moneda, str):
        moneda_obj = Moneda.objects.filter(siglas__iexact=moneda.strip(), activa=True).first()
    else:
        moneda_obj = moneda

    if not moneda_obj:
        return None

    # Si es moneda base (PYG), la tasa de referencia es 1.00
    if moneda_obj.siglas.upper() == 'PYG':
        return {
            'tasa_sugerida': Decimal('1.00'),
            'compra': Decimal('1.00'),
            'venta': Decimal('1.00'),
            'cotizacion_id': None,
            'par': 'PYG a PYG',
            'fecha': None
        }

    # Buscar cotización activa de la divisa respecto a PYG (o cualquier contraparte activa)
    cot = (
        Cotizacion.objects.filter(
            moneda_origen=moneda_obj,
            activo=True
        )
        .order_by('-fecha')
        .first()
    )

    if not cot:
        # Intentar en sentido inverso
        cot = (
            Cotizacion.objects.filter(
                moneda_destino=moneda_obj,
                activo=True
            )
            .order_by('-fecha')
            .first()
        )

    if cot:
        # En una casa de cambio:
        # Cuando el cliente VENDE moneda extranjera, la casa de cambios COMPRA (tasa cot.compra).
        # Cuando el cliente COMPRA moneda extranjera, la casa de cambios VENDE (tasa cot.venta).
        if str(tipo).upper() == 'VENTA':
            tasa = cot.compra
        else:
            tasa = cot.venta

        return {
            'tasa_sugerida': tasa,
            'compra': cot.compra,
            'venta': cot.venta,
            'cotizacion_id': cot.id,
            'par': str(cot),
            'fecha': cot.fecha.strftime('%d/%m/%Y %H:%M') if cot.fecha else None
        }

    return None


def calcular_comision_operacion(cliente, monto, tasa_aplicada, tipo='VENTA') -> dict:
    """
    Calcula de forma automática la comisión y liquidación de una operación de cambio (Venta o Compra).
    
    Criterios:
    1. Subtotal = Monto * Tasa Aplicada.
    2. Porcentaje de comisión segmentado por cliente:
       - VIP: 0.5%
       - Corporativo: 1.0%
       - Minorista / Regular: 1.5%
    3. Comisión = Subtotal * (Porcentaje / 100).
    4. Liquidación neta:
       - VENTA: Subtotal - Comisión (monto a entregar al cliente en moneda local).
       - COMPRA: Subtotal + Comisión (monto a abonar por el cliente).
    """
    from clientes.models import Cliente

    if monto is None or str(monto).strip() == '':
        raise ValueError("Debe ingresar el monto de la operación.")
    
    if tasa_aplicada is None or str(tasa_aplicada).strip() == '':
        raise ValueError("Debe ingresar la tasa aplicada.")

    try:
        monto_dec = Decimal(str(monto))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("El monto ingresado no es un valor numérico válido.")

    try:
        tasa_dec = Decimal(str(tasa_aplicada))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("La tasa aplicada no es un valor numérico válido.")

    if monto_dec <= Decimal('0'):
        raise ValueError("El monto debe ser un valor positivo mayor a cero.")

    if tasa_dec <= Decimal('0'):
        raise ValueError("La tasa aplicada debe ser mayor a cero.")

    # Determinar cliente y segmento
    cliente_obj = None
    if isinstance(cliente, (int, str)) and str(cliente).isdigit():
        cliente_obj = Cliente.objects.filter(id=int(cliente)).first()
    elif isinstance(cliente, Cliente):
        cliente_obj = cliente

    segmento = getattr(cliente_obj, 'segmento', Cliente.Segmento.MINORISTA if hasattr(Cliente, 'Segmento') else 'MINORISTA')
    
    # Tabla de comisiones por segmento
    if segmento == 'VIP':
        porcentaje_comision = Decimal('0.5')
    elif segmento == 'CORPORATIVO':
        porcentaje_comision = Decimal('1.0')
    else:
        porcentaje_comision = Decimal('1.5')

    subtotal = (monto_dec * tasa_dec).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    comision = (subtotal * (porcentaje_comision / Decimal('100'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    tipo_upper = str(tipo).upper().strip()
    if tipo_upper == 'VENTA':
        total_neto = (subtotal - comision).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        total_neto = (subtotal + comision).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return {
        'exito': True,
        'tipo': tipo_upper,
        'monto': monto_dec,
        'tasa_aplicada': tasa_dec,
        'subtotal': subtotal,
        'segmento': segmento,
        'porcentaje_comision': porcentaje_comision,
        'comision': comision,
        'total_neto': total_neto,
    }


def registrar_operacion_cambio(cliente, moneda, tipo, monto, tasa_aplicada, usuario=None):
    """
    Crea y persiste una Operacion en estado PENDIENTE, calculando la comisión
    correspondiente según las reglas del negocio de manera auditable e íntegra.
    Compatible tanto para 'VENTA' como para 'COMPRA'.
    """
    from .models import Operacion
    from monedas.models import Moneda
    from clientes.models import Cliente

    if isinstance(cliente, (int, str)):
        cliente = Cliente.objects.get(id=int(cliente), activo=True)
    if isinstance(moneda, (int, str)):
        moneda = Moneda.objects.get(id=int(moneda), activa=True)

    calculo = calcular_comision_operacion(
        cliente=cliente,
        monto=monto,
        tasa_aplicada=tasa_aplicada,
        tipo=tipo
    )

    operacion = Operacion.objects.create(
        cliente=cliente,
        moneda=moneda,
        tipo=calculo['tipo'],
        monto=calculo['monto'],
        tasa_aplicada=calculo['tasa_aplicada'],
        comision=calculo['comision'],
        estado=Operacion.EstadoOperacion.PENDIENTE,
        registrado_por=usuario if (usuario and getattr(usuario, 'is_authenticated', False)) else None,
    )

    return operacion, calculo

