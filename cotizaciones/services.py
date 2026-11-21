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
    roles_gestion = {'admin', 'supervisor', 'operador', 'empleado', 'cajero'}
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


def registrar_operacion_cambio(cliente, moneda, tipo, monto, tasa_aplicada, usuario=None, caja=None, sesion_caja=None, canal='DIGITAL'):
    """
    Crea y persiste una Operacion en estado PENDIENTE, calculando la comisión
    correspondiente según las reglas del negocio de manera auditable e íntegra.
    Compatible tanto para 'VENTA' como para 'COMPRA', asociando la caja y turno si es canal físico (RN15).
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
        caja=caja,
        sesion_caja=sesion_caja,
        canal=canal,
    )

    return operacion, calculo

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
        from .templatetags.formatos import _formatear_miles
        sentido = "subió" if diferencia > Decimal('0') else "bajó"
        notificacion = (
            f"La cotización de {operacion.moneda.siglas} cambió respecto al inicio de la operación: "
            f"pasó de {_formatear_miles(tasa_inicial)} a {_formatear_miles(tasa_vigente)} "
            f"({sentido} {_formatear_miles(abs(diferencia))} / {abs(porcentaje)}%). "
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


def obtener_metricas_tablero_ganancias(dias_serie: int = 14, fecha_desde=None, fecha_hasta=None) -> Dict[str, Any]:
    """
    Calcula y estructura las métricas financieras para el Tablero de Control de Ganancias (IS2-67).
    Incluye:
    - Ganancias del día actual y comparativa con ayer.
    - Comparativas acumuladas por período: Día, Semana (lunes a hoy) vs semana previa, Mes actual vs mes previo.
    - Desglose de ganancias y operaciones por tipo (Compras vs Ventas).
    - Desglose de ganancias por moneda con totales y porcentajes.
    - Serie temporal diaria para gráficos interactivos (últimos N días).
    
    Parámetros opcionales:
    - fecha_desde: date, filtra operaciones desde esta fecha (inclusive).
    - fecha_hasta: date, filtra operaciones hasta esta fecha (inclusive).
    Cuando se proporcionan, las métricas de período (día/semana/mes) son
    reemplazadas por métricas del rango personalizado.
    """
    from datetime import timedelta
    from django.utils import timezone
    from django.db.models import Sum, Count, Q
    from .models import Operacion

    ahora = timezone.now()
    hoy = ahora.date()
    ayer = hoy - timedelta(days=1)

    # Base queryset: solo operaciones pagadas/completadas
    qs_base = Operacion.objects.filter(estado=Operacion.EstadoOperacion.PAGADA)

    # Aplicar filtro de rango personalizado al queryset global si se indica
    filtro_activo = fecha_desde is not None or fecha_hasta is not None
    if filtro_activo:
        if fecha_desde:
            qs_base = qs_base.filter(fecha__date__gte=fecha_desde)
        if fecha_hasta:
            qs_base = qs_base.filter(fecha__date__lte=fecha_hasta)

    qs_pagadas = qs_base

    # 1. DÍA ACTUAL vs AYER
    ops_hoy = qs_pagadas.filter(fecha__date=hoy)
    agg_hoy = ops_hoy.aggregate(
        ganancias=Sum('comision'),
        total_ops=Count('id'),
        compras_comision=Sum('comision', filter=Q(tipo=Operacion.TipoOperacion.COMPRA)),
        ventas_comision=Sum('comision', filter=Q(tipo=Operacion.TipoOperacion.VENTA)),
        compras_count=Count('id', filter=Q(tipo=Operacion.TipoOperacion.COMPRA)),
        ventas_count=Count('id', filter=Q(tipo=Operacion.TipoOperacion.VENTA)),
    )
    ganancias_hoy = agg_hoy['ganancias'] or Decimal('0.00')
    total_ops_hoy = agg_hoy['total_ops'] or 0

    agg_ayer = qs_pagadas.filter(fecha__date=ayer).aggregate(
        ganancias=Sum('comision'),
        total_ops=Count('id')
    )
    ganancias_ayer = agg_ayer['ganancias'] or Decimal('0.00')

    if ganancias_ayer > 0:
        variacion_dia_pct = ((ganancias_hoy - ganancias_ayer) / ganancias_ayer) * 100
    elif ganancias_hoy > 0:
        variacion_dia_pct = Decimal('100.0')
    else:
        variacion_dia_pct = Decimal('0.0')

    # 2. SEMANA ACTUAL vs SEMANA ANTERIOR
    # Semana actual: desde el lunes de la semana en curso
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    ops_semana = qs_pagadas.filter(fecha__date__gte=inicio_semana, fecha__date__lte=hoy)
    agg_semana = ops_semana.aggregate(
        ganancias=Sum('comision'),
        total_ops=Count('id'),
    )
    ganancias_semana = agg_semana['ganancias'] or Decimal('0.00')
    total_ops_semana = agg_semana['total_ops'] or 0

    inicio_semana_ant = inicio_semana - timedelta(days=7)
    fin_semana_ant = inicio_semana - timedelta(days=1)
    agg_semana_ant = qs_pagadas.filter(fecha__date__gte=inicio_semana_ant, fecha__date__lte=fin_semana_ant).aggregate(
        ganancias=Sum('comision')
    )
    ganancias_semana_ant = agg_semana_ant['ganancias'] or Decimal('0.00')

    if ganancias_semana_ant > 0:
        variacion_semana_pct = ((ganancias_semana - ganancias_semana_ant) / ganancias_semana_ant) * 100
    elif ganancias_semana > 0:
        variacion_semana_pct = Decimal('100.0')
    else:
        variacion_semana_pct = Decimal('0.0')

    # 3. MES ACTUAL vs MES ANTERIOR
    inicio_mes = hoy.replace(day=1)
    ops_mes = qs_pagadas.filter(fecha__date__gte=inicio_mes, fecha__date__lte=hoy)
    agg_mes = ops_mes.aggregate(
        ganancias=Sum('comision'),
        total_ops=Count('id'),
    )
    ganancias_mes = agg_mes['ganancias'] or Decimal('0.00')
    total_ops_mes = agg_mes['total_ops'] or 0

    fin_mes_ant = inicio_mes - timedelta(days=1)
    inicio_mes_ant = fin_mes_ant.replace(day=1)
    agg_mes_ant = qs_pagadas.filter(fecha__date__gte=inicio_mes_ant, fecha__date__lte=fin_mes_ant).aggregate(
        ganancias=Sum('comision')
    )
    ganancias_mes_ant = agg_mes_ant['ganancias'] or Decimal('0.00')

    if ganancias_mes_ant > 0:
        variacion_mes_pct = ((ganancias_mes - ganancias_mes_ant) / ganancias_mes_ant) * 100
    elif ganancias_mes > 0:
        variacion_mes_pct = Decimal('100.0')
    else:
        variacion_mes_pct = Decimal('0.0')

    # 4. TOTAL GENERAL ACUMULADO
    agg_total = qs_pagadas.aggregate(
        ganancias=Sum('comision'),
        total_ops=Count('id'),
        compras_comision=Sum('comision', filter=Q(tipo=Operacion.TipoOperacion.COMPRA)),
        ventas_comision=Sum('comision', filter=Q(tipo=Operacion.TipoOperacion.VENTA)),
        compras_count=Count('id', filter=Q(tipo=Operacion.TipoOperacion.COMPRA)),
        ventas_count=Count('id', filter=Q(tipo=Operacion.TipoOperacion.VENTA)),
    )
    ganancias_total = agg_total['ganancias'] or Decimal('0.00')
    total_ops_general = agg_total['total_ops'] or 0

    compras_comision = agg_total['compras_comision'] or Decimal('0.00')
    ventas_comision = agg_total['ventas_comision'] or Decimal('0.00')
    compras_count = agg_total['compras_count'] or 0
    ventas_count = agg_total['ventas_count'] or 0

    compras_pct = ((compras_comision / ganancias_total) * 100) if ganancias_total > 0 else Decimal('0.0')
    ventas_pct = ((ventas_comision / ganancias_total) * 100) if ganancias_total > 0 else Decimal('0.0')

    # 5. DESGLOSE POR MONEDA
    monedas_qs = (
        qs_pagadas.values('moneda__id', 'moneda__siglas', 'moneda__nombre')
        .annotate(
            total_comisiones=Sum('comision'),
            total_ops=Count('id'),
            total_compras=Count('id', filter=Q(tipo=Operacion.TipoOperacion.COMPRA)),
            total_ventas=Count('id', filter=Q(tipo=Operacion.TipoOperacion.VENTA)),
            comisiones_compras=Sum('comision', filter=Q(tipo=Operacion.TipoOperacion.COMPRA)),
            comisiones_ventas=Sum('comision', filter=Q(tipo=Operacion.TipoOperacion.VENTA)),
            volumen_divisa=Sum('monto'),
        )
        .order_by('-total_comisiones')
    )

    desglose_monedas = []
    for m in monedas_qs:
        comis = m['total_comisiones'] or Decimal('0.00')
        pct = ((comis / ganancias_total) * 100) if ganancias_total > 0 else Decimal('0.0')
        desglose_monedas.append({
            'moneda_id': m['moneda__id'],
            'siglas': m['moneda__siglas'],
            'nombre': m['moneda__nombre'],
            'total_comisiones': comis,
            'total_ops': m['total_ops'] or 0,
            'total_compras': m['total_compras'] or 0,
            'total_ventas': m['total_ventas'] or 0,
            'comisiones_compras': m['comisiones_compras'] or Decimal('0.00'),
            'comisiones_ventas': m['comisiones_ventas'] or Decimal('0.00'),
            'volumen_divisa': m['volumen_divisa'] or Decimal('0.00'),
            'porcentaje': round(float(pct), 2),
        })

    # 6. SERIE TEMPORAL
    # Si hay filtro personalizado, construir la serie en el rango indicado; si no, últimos N días.
    if filtro_activo:
        f_desde_serie = fecha_desde or (hoy - timedelta(days=dias_serie - 1))
        f_hasta_serie = fecha_hasta or hoy
    else:
        f_desde_serie = hoy - timedelta(days=dias_serie - 1)
        f_hasta_serie = hoy

    # Limitar la serie a un máximo de 90 días para no sobrecargar el gráfico
    delta_dias = (f_hasta_serie - f_desde_serie).days + 1
    if delta_dias > 90:
        f_desde_serie = f_hasta_serie - timedelta(days=89)
        delta_dias = 90

    ops_serie = qs_pagadas.filter(fecha__date__gte=f_desde_serie, fecha__date__lte=f_hasta_serie)

    serie_dict = {}
    for i in range(delta_dias):
        f = f_desde_serie + timedelta(days=i)
        serie_dict[f] = {
            'fecha': f.strftime('%d/%m'),
            'fecha_iso': f.strftime('%Y-%m-%d'),
            'ganancias': Decimal('0.00'),
            'compras': Decimal('0.00'),
            'ventas': Decimal('0.00'),
            'operaciones': 0
        }

    for op in ops_serie:
        f_date = op.fecha.date()
        if f_date in serie_dict:
            serie_dict[f_date]['ganancias'] += (op.comision or Decimal('0.00'))
            serie_dict[f_date]['operaciones'] += 1
            if op.tipo == Operacion.TipoOperacion.COMPRA:
                serie_dict[f_date]['compras'] += (op.comision or Decimal('0.00'))
            else:
                serie_dict[f_date]['ventas'] += (op.comision or Decimal('0.00'))

    serie_temporal = list(serie_dict.values())

    # 7. ÚLTIMAS OPERACIONES (recientes pagadas dentro del rango)
    ultimas_operaciones = list(qs_pagadas.select_related('cliente', 'moneda').order_by('-fecha')[:8])

    return {
        'ahora': ahora,
        'hoy': hoy,
        'ayer': ayer,
        'filtro_activo': filtro_activo,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'dia': {
            'ganancias': ganancias_hoy,
            'operaciones': total_ops_hoy,
            'variacion_pct': round(float(variacion_dia_pct), 1),
            'ganancias_ayer': ganancias_ayer,
            'compras_ganancia': agg_hoy['compras_comision'] or Decimal('0.00'),
            'ventas_ganancia': agg_hoy['ventas_comision'] or Decimal('0.00'),
            'compras_count': agg_hoy['compras_count'] or 0,
            'ventas_count': agg_hoy['ventas_count'] or 0,
        },
        'semana': {
            'inicio': inicio_semana,
            'ganancias': ganancias_semana,
            'operaciones': total_ops_semana,
            'variacion_pct': round(float(variacion_semana_pct), 1),
            'ganancias_anterior': ganancias_semana_ant,
        },
        'mes': {
            'inicio': inicio_mes,
            'nombre_mes': hoy.strftime('%B'),
            'ganancias': ganancias_mes,
            'operaciones': total_ops_mes,
            'variacion_pct': round(float(variacion_mes_pct), 1),
            'ganancias_anterior': ganancias_mes_ant,
        },
        'total': {
            'ganancias': ganancias_total,
            'operaciones': total_ops_general,
        },
        'tipo_operacion': {
            'compras_comision': compras_comision,
            'compras_count': compras_count,
            'compras_pct': round(float(compras_pct), 1),
            'ventas_comision': ventas_comision,
            'ventas_count': ventas_count,
            'ventas_pct': round(float(ventas_pct), 1),
        },
        'desglose_monedas': desglose_monedas,
        'serie_temporal': serie_temporal,
        'ultimas_operaciones': ultimas_operaciones,
    }


