from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from authentication.decorators import rol_requerido
from .models import Cotizacion, Operacion
from .forms import CotizacionForm

import json
import csv
from datetime import datetime
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie

@rol_requerido('analista_cambiario', 'admin')
def analista_panel(request):
    """Panel principal del analista cambiario."""
    cotizaciones = Cotizacion.objects.all().order_by('-fecha')
    return render(request, 'cotizaciones/panel.html', {
        'cotizaciones': cotizaciones,
        'cotizaciones_activas': cotizaciones.filter(activo=True).count(),
        'cotizaciones_inactivas': cotizaciones.filter(activo=False).count(),
    })

@rol_requerido('analista_cambiario', 'admin')
@ensure_csrf_cookie
def cotizaciones_frontend(request):
    """Renderiza la interfaz frontend para registrar cotizaciones."""
    from monedas.models import Moneda
    monedas = Moneda.objects.filter(activa=True)
    return render(request, 'cotizaciones/registrar.html', {'monedas': monedas})

@rol_requerido('analista_cambiario', 'admin')
@require_http_methods(["POST"])
def registrar_cotizacion_api(request):
    """Endpoint API para registrar una nueva cotización."""
    try:
        data = json.loads(request.body)
        moneda_origen = data.get('moneda_origen')
        moneda_destino = data.get('moneda_destino')
        compra = data.get('compra')
        venta = data.get('venta')
        if not all([moneda_origen, moneda_destino, compra, venta]):
            return JsonResponse({'error': 'Todos los campos son obligatorios.'}, status=400)
        
        # Validar que la tasa de venta no sea menor a la compra
        if float(venta) < float(compra):
            return JsonResponse({'error': 'La tasa de venta no puede ser menor a la tasa de compra.'}, status=400)

        cotizacion = Cotizacion.objects.create(
            moneda_origen_id=moneda_origen,
            moneda_destino_id=moneda_destino,
            compra=compra,
            venta=venta,
            registrado_por=request.user if request.user.is_authenticated else None,
        )
        return JsonResponse({'mensaje': 'Cotización registrada exitosamente.', 'id': cotizacion.id}, status=201)
    except ValueError:
        return JsonResponse({'error': 'Los valores de compra y venta deben ser numéricos.'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Formato JSON inválido.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@rol_requerido('analista_cambiario', 'admin')
@ensure_csrf_cookie
def cotizaciones_modificar_frontend(request, cotizacion_id):
    """Renderiza la interfaz frontend para modificar una cotización."""
    from django.shortcuts import get_object_or_404
    from monedas.models import Moneda
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, activo=True)
    monedas = Moneda.objects.filter(activa=True)
    return render(request, 'cotizaciones/modificar.html', {'cotizacion': cotizacion, 'monedas': monedas})

@rol_requerido('analista_cambiario', 'admin')
@require_http_methods(["POST"])
def modificar_cotizacion_api(request, cotizacion_id):
    """Endpoint API para modificar una cotización (pasa al historial la anterior)."""
    from django.shortcuts import get_object_or_404
    try:
        cotizacion_anterior = get_object_or_404(Cotizacion, id=cotizacion_id, activo=True)
        data = json.loads(request.body)
        compra = data.get('compra')
        venta = data.get('venta')
        
        if not compra or not venta:
            return JsonResponse({'error': 'Los precios de compra y venta son obligatorios.'}, status=400)
            
        if float(venta) < float(compra):
            return JsonResponse({'error': 'La tasa de venta no puede ser menor a la tasa de compra.'}, status=400)
            
        # Pasar la actual al historial
        cotizacion_anterior.activo = False
        cotizacion_anterior.save()
        
        # Crear la nueva como vigente
        nueva_cotizacion = Cotizacion.objects.create(
            moneda_origen=cotizacion_anterior.moneda_origen,
            moneda_destino=cotizacion_anterior.moneda_destino,
            compra=compra,
            venta=venta,
            activo=True,
            registrado_por=request.user if request.user.is_authenticated else None,
        )
        return JsonResponse({'mensaje': 'Cotización actualizada exitosamente.', 'id': nueva_cotizacion.id}, status=201)
    except ValueError:
        return JsonResponse({'error': 'Los valores de compra y venta deben ser numéricos.'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Formato JSON inválido.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@rol_requerido('analista_cambiario', 'admin')
@require_http_methods(["POST"])
def desactivar_cotizacion_api(request, cotizacion_id):
    """Endpoint API para desactivar una cotización."""
    from django.shortcuts import get_object_or_404
    try:
        cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, activo=True)
        cotizacion.activo = False
        cotizacion.save()
        return JsonResponse({'mensaje': 'Cotización desactivada exitosamente.'}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def obtener_tasa_vigente_api(request, origen, destino):
    """Endpoint público/interno para obtener la tasa activa de un par de monedas."""
    cotizacion = Cotizacion.objects.filter(moneda_origen__siglas=origen.upper(), moneda_destino__siglas=destino.upper(), activo=True).first()
    
    if not cotizacion:
        return JsonResponse({'error': 'No hay cotización disponible para operar'}, status=404)
        
    return JsonResponse({
        'moneda_origen': cotizacion.moneda_origen.siglas,
        'moneda_destino': cotizacion.moneda_destino.siglas,
        'compra': str(cotizacion.compra),
        'venta': str(cotizacion.venta),
        'fecha': cotizacion.fecha.isoformat()
    }, status=200)

@rol_requerido('analista_cambiario', 'admin')
def consultar_cotizaciones(request):
    """Vista que muestra el historial de cotizaciones con filtro por moneda."""
    from monedas.models import Moneda
    monedas = Moneda.objects.filter(activa=True)
    moneda_origen_filtro = request.GET.get('moneda_origen', '')
    moneda_destino_filtro = request.GET.get('moneda_destino', '')

    cotizaciones = Cotizacion.objects.select_related('registrado_por', 'moneda_origen', 'moneda_destino').order_by('-fecha')
    if moneda_origen_filtro:
        cotizaciones = cotizaciones.filter(moneda_origen_id=moneda_origen_filtro)
    if moneda_destino_filtro:
        cotizaciones = cotizaciones.filter(moneda_destino_id=moneda_destino_filtro)

    return render(request, 'cotizaciones/consultar.html', {
        'cotizaciones': cotizaciones,
        'monedas': monedas,
        'moneda_origen_filtro': moneda_origen_filtro,
        'moneda_destino_filtro': moneda_destino_filtro,
    })


@login_required
def consultar_tasas_vigentes(request):
    """
    Permite a cualquier Usuario Registrado consultar las tasas de cambio vigentes
    (compra y venta) antes de operar, reflejando la información más reciente.
    (IS2-6 / IS2-7)
    """
    from monedas.models import Moneda
    monedas_activas = Moneda.objects.filter(activa=True).order_by('siglas')
    
    moneda_origen_filtro = request.GET.get('moneda_origen', '').strip()
    moneda_destino_filtro = request.GET.get('moneda_destino', '').strip()
    busqueda = request.GET.get('q', '').strip().upper()

    # Cotizaciones activas ordenadas por fecha descendente
    cotizaciones_qs = (
        Cotizacion.objects.filter(
            activo=True,
            moneda_origen__activa=True,
            moneda_destino__activa=True
        )
        .select_related('moneda_origen', 'moneda_destino')
        .order_by('-fecha')
    )

    # Filtrar únicamente la cotización más reciente de cada par (moneda_origen, moneda_destino)
    seen_pairs = set()
    tasas_vigentes = []
    for cot in cotizaciones_qs:
        pair_key = (cot.moneda_origen_id, cot.moneda_destino_id)
        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            # Calcular spread (margen cambiario)
            cot.spread = cot.venta - cot.compra
            tasas_vigentes.append(cot)

    # Aplicar filtros si fueron provistos
    if moneda_origen_filtro:
        tasas_vigentes = [t for t in tasas_vigentes if str(t.moneda_origen_id) == moneda_origen_filtro or t.moneda_origen.siglas == moneda_origen_filtro.upper()]
    if moneda_destino_filtro:
        tasas_vigentes = [t for t in tasas_vigentes if str(t.moneda_destino_id) == moneda_destino_filtro or t.moneda_destino.siglas == moneda_destino_filtro.upper()]
    if busqueda:
        tasas_vigentes = [
            t for t in tasas_vigentes
            if busqueda in t.moneda_origen.siglas.upper()
            or busqueda in t.moneda_origen.nombre.upper()
            or busqueda in t.moneda_destino.siglas.upper()
            or busqueda in t.moneda_destino.nombre.upper()
        ]

    # Datos serializados para el conversor interactivo en JavaScript
    tasas_json = [
        {
            'id': t.id,
            'origen': t.moneda_origen.siglas,
            'origen_nombre': t.moneda_origen.nombre,
            'destino': t.moneda_destino.siglas,
            'destino_nombre': t.moneda_destino.nombre,
            'compra': float(t.compra),
            'venta': float(t.venta),
            'fecha': t.fecha.strftime('%d/%m/%Y %H:%M'),
        }
        for t in tasas_vigentes
    ]

    return render(request, 'cotizaciones/tasas_vigentes.html', {
        'tasas': tasas_vigentes,
        'tasas_count': len(tasas_vigentes),
        'monedas': monedas_activas,
        'moneda_origen_filtro': moneda_origen_filtro,
        'moneda_destino_filtro': moneda_destino_filtro,
        'busqueda': busqueda,
        'tasas_json': json.dumps(tasas_json),
    })


@login_required
@require_http_methods(["GET"])
def listar_tasas_vigentes_api(request):
    """
    Endpoint JSON para que cualquier usuario registrado consulte
    las tasas de cambio vigentes sin recargar la página.
    """
    cotizaciones_qs = (
        Cotizacion.objects.filter(
            activo=True,
            moneda_origen__activa=True,
            moneda_destino__activa=True
        )
        .select_related('moneda_origen', 'moneda_destino')
        .order_by('-fecha')
    )

    seen_pairs = set()
    tasas_vigentes = []
    for cot in cotizaciones_qs:
        pair_key = (cot.moneda_origen_id, cot.moneda_destino_id)
        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            tasas_vigentes.append({
                'id': cot.id,
                'moneda_origen': cot.moneda_origen.siglas,
                'moneda_origen_nombre': cot.moneda_origen.nombre,
                'moneda_destino': cot.moneda_destino.siglas,
                'moneda_destino_nombre': cot.moneda_destino.nombre,
                'compra': str(cot.compra),
                'venta': str(cot.venta),
                'spread': str(cot.venta - cot.compra),
                'fecha': cot.fecha.isoformat(),
            })

    return JsonResponse({'tasas': tasas_vigentes, 'total': len(tasas_vigentes)}, status=200)


def _obtener_cotizaciones_filtradas(request):
    """Función auxiliar compartida para filtrar cotizaciones por fecha y par de monedas."""
    moneda_origen_filtro = request.GET.get('moneda_origen', '').strip()
    moneda_destino_filtro = request.GET.get('moneda_destino', '').strip()
    fecha_desde_str = request.GET.get('fecha_desde', '').strip()
    fecha_hasta_str = request.GET.get('fecha_hasta', '').strip()

    cotizaciones_qs = Cotizacion.objects.select_related(
        'moneda_origen', 'moneda_destino', 'registrado_por'
    ).order_by('-fecha')

    if moneda_origen_filtro:
        if moneda_origen_filtro.isdigit():
            cotizaciones_qs = cotizaciones_qs.filter(moneda_origen_id=int(moneda_origen_filtro))
        else:
            cotizaciones_qs = cotizaciones_qs.filter(moneda_origen__siglas__iexact=moneda_origen_filtro)

    if moneda_destino_filtro:
        if moneda_destino_filtro.isdigit():
            cotizaciones_qs = cotizaciones_qs.filter(moneda_destino_id=int(moneda_destino_filtro))
        else:
            cotizaciones_qs = cotizaciones_qs.filter(moneda_destino__siglas__iexact=moneda_destino_filtro)

    if fecha_desde_str:
        try:
            f_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d').date()
            cotizaciones_qs = cotizaciones_qs.filter(fecha__date__gte=f_desde)
        except ValueError:
            pass

    if fecha_hasta_str:
        try:
            f_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').date()
            cotizaciones_qs = cotizaciones_qs.filter(fecha__date__lte=f_hasta)
        except ValueError:
            pass

    return cotizaciones_qs, moneda_origen_filtro, moneda_destino_filtro, fecha_desde_str, fecha_hasta_str


@login_required
def historial_tasas(request):
    """
    Permite a cualquier Usuario Registrado ver el historial de tasas de cambio
    en un rango de fechas determinado para analizar la evolución de una moneda.
    (IS2-8)
    """
    from monedas.models import Moneda
    monedas_activas = Moneda.objects.filter(activa=True).order_by('siglas')

    cotizaciones_qs, moneda_origen_filtro, moneda_destino_filtro, fecha_desde_str, fecha_hasta_str = (
        _obtener_cotizaciones_filtradas(request)
    )

    cotizaciones = list(cotizaciones_qs)
    for c in cotizaciones:
        c.spread = c.venta - c.compra

    # Estadísticas básicas del periodo seleccionado
    min_compra = min((c.compra for c in cotizaciones), default=None)
    max_compra = max((c.compra for c in cotizaciones), default=None)
    min_venta = min((c.venta for c in cotizaciones), default=None)
    max_venta = max((c.venta for c in cotizaciones), default=None)

    # Datos cronológicos (ascendentes) para el gráfico interactivo de evolución
    chart_data = [
        {
            'fecha': c.fecha.strftime('%d/%m/%Y %H:%M'),
            'compra': float(c.compra),
            'venta': float(c.venta),
            'par': f"{c.moneda_origen.siglas}/{c.moneda_destino.siglas}",
        }
        for c in reversed(cotizaciones)
    ]

    return render(request, 'cotizaciones/historial_tasas.html', {
        'cotizaciones': cotizaciones,
        'total_registros': len(cotizaciones),
        'monedas': monedas_activas,
        'moneda_origen_filtro': moneda_origen_filtro,
        'moneda_destino_filtro': moneda_destino_filtro,
        'fecha_desde': fecha_desde_str,
        'fecha_hasta': fecha_hasta_str,
        'min_compra': min_compra,
        'max_compra': max_compra,
        'min_venta': min_venta,
        'max_venta': max_venta,
        'chart_data_json': json.dumps(chart_data),
    })


@login_required
def descargar_reporte_historial(request):
    """
    Descarga el reporte del historial de cotizaciones consultado en formato CSV
    compatible con Microsoft Excel y hojas de cálculo. (IS2-8)
    """
    cotizaciones_qs, moneda_origen_filtro, moneda_destino_filtro, fecha_desde_str, fecha_hasta_str = (
        _obtener_cotizaciones_filtradas(request)
    )

    filename_parts = ['historial_tasas']
    if moneda_origen_filtro:
        filename_parts.append(moneda_origen_filtro.upper())
    if moneda_destino_filtro:
        filename_parts.append(moneda_destino_filtro.upper())
    if fecha_desde_str:
        filename_parts.append(f"desde_{fecha_desde_str}")
    if fecha_hasta_str:
        filename_parts.append(f"hasta_{fecha_hasta_str}")
    filename = "_".join(filename_parts) + ".csv"

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        'Fecha',
        'Hora',
        'Moneda Origen',
        'Código Origen',
        'Moneda Destino',
        'Código Destino',
        'Precio Compra',
        'Precio Venta',
        'Spread / Margen',
        'Estado'
    ])

    for c in cotizaciones_qs:
        writer.writerow([
            c.fecha.strftime('%d/%m/%Y'),
            c.fecha.strftime('%H:%M:%S'),
            c.moneda_origen.nombre,
            c.moneda_origen.siglas,
            c.moneda_destino.nombre,
            c.moneda_destino.siglas,
            str(c.compra),
            str(c.venta),
            str(c.venta - c.compra),
            'Vigente' if c.activo else 'Histórico'
        ])

    return response


def tasas_visitante(request):
    """
    Vista pública: permite a un visitante (no registrado) consultar las tasas
    de cambio vigentes sin necesidad de iniciar sesión. (IS2-20)
    """
    from monedas.models import Moneda
    monedas_activas = Moneda.objects.filter(activa=True).order_by('siglas')

    moneda_origen_filtro = request.GET.get('moneda_origen', '').strip()
    moneda_destino_filtro = request.GET.get('moneda_destino', '').strip()
    busqueda = request.GET.get('q', '').strip().upper()

    cotizaciones_qs = (
        Cotizacion.objects.filter(
            activo=True,
            moneda_origen__activa=True,
            moneda_destino__activa=True
        )
        .select_related('moneda_origen', 'moneda_destino')
        .order_by('-fecha')
    )

    seen_pairs = set()
    tasas_vigentes = []
    for cot in cotizaciones_qs:
        pair_key = (cot.moneda_origen_id, cot.moneda_destino_id)
        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            cot.spread = cot.venta - cot.compra
            tasas_vigentes.append(cot)

    if moneda_origen_filtro:
        tasas_vigentes = [t for t in tasas_vigentes if str(t.moneda_origen_id) == moneda_origen_filtro or t.moneda_origen.siglas == moneda_origen_filtro.upper()]
    if moneda_destino_filtro:
        tasas_vigentes = [t for t in tasas_vigentes if str(t.moneda_destino_id) == moneda_destino_filtro or t.moneda_destino.siglas == moneda_destino_filtro.upper()]
    if busqueda:
        tasas_vigentes = [
            t for t in tasas_vigentes
            if busqueda in t.moneda_origen.siglas.upper()
            or busqueda in t.moneda_origen.nombre.upper()
            or busqueda in t.moneda_destino.siglas.upper()
            or busqueda in t.moneda_destino.nombre.upper()
        ]

    tasas_json = [
        {
            'id': t.id,
            'origen': t.moneda_origen.siglas,
            'origen_nombre': t.moneda_origen.nombre,
            'destino': t.moneda_destino.siglas,
            'destino_nombre': t.moneda_destino.nombre,
            'compra': float(t.compra),
            'venta': float(t.venta),
            'fecha': t.fecha.strftime('%d/%m/%Y %H:%M'),
        }
        for t in tasas_vigentes
    ]

    return render(request, 'cotizaciones/tasas_visitante.html', {
        'tasas': tasas_vigentes,
        'tasas_count': len(tasas_vigentes),
        'monedas': monedas_activas,
        'moneda_origen_filtro': moneda_origen_filtro,
        'moneda_destino_filtro': moneda_destino_filtro,
        'busqueda': busqueda,
        'tasas_json': json.dumps(tasas_json),
    })


# ==========================================
# Simulador de Conversión de Moneda (IS2-10)
# ==========================================

@login_required
def simulador_conversion_view(request):
    """
    Vista web interactiva para que un usuario registrado simule
    la conversión entre dos monedas según la tasa vigente (IS2-10).
    """
    from .services import simular_conversion, obtener_monedas_disponibles
    
    monedas = obtener_monedas_disponibles()
    resultado = None
    error = None
    
    # Soporta parámetros vía GET o POST (por defecto PYG a USD para el público paraguayo)
    moneda_origen = request.GET.get('moneda_origen') or request.POST.get('moneda_origen') or 'PYG'
    moneda_destino = request.GET.get('moneda_destino') or request.POST.get('moneda_destino') or 'USD'
    monto = request.GET.get('monto') or request.POST.get('monto') or ''
    
    if monto:
        try:
            resultado = simular_conversion(
                moneda_origen=moneda_origen,
                moneda_destino=moneda_destino,
                monto=monto
            )
        except ValueError as ve:
            error = str(ve)
        except Exception as e:
            error = f"Ocurrió un error inesperado al calcular la conversión: {str(e)}"
            
    return render(request, 'cotizaciones/simulador.html', {
        'monedas': monedas,
        'moneda_origen': moneda_origen,
        'moneda_destino': moneda_destino,
        'monto': monto,
        'resultado': resultado,
        'error': error,
    })


@login_required
@require_http_methods(["GET", "POST"])
def api_simular_conversion(request):
    """
    Endpoint API para simular conversión de monedas en tiempo real (IS2-10).
    Retorna JSON con el monto calculado y tasa aplicada.
    """
    from .services import simular_conversion
    
    if request.method == 'POST':
        try:
            if request.content_type == 'application/json' and request.body:
                data = json.loads(request.body)
            else:
                data = request.POST
        except json.JSONDecodeError:
            return JsonResponse({'exito': False, 'error': 'Formato JSON inválido.'}, status=400)
    else:
        data = request.GET

    moneda_origen = data.get('moneda_origen')
    moneda_destino = data.get('moneda_destino')
    monto = data.get('monto')

    if not all([moneda_origen, moneda_destino, monto]):
        return JsonResponse({
            'exito': False,
            'error': 'Parámetros obligatorios: moneda_origen, moneda_destino y monto.'
        }, status=400)

    try:
        resultado = simular_conversion(
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
            monto=monto
        )
        # Serializar tipos no nativos JSON
        payload = {
            'exito': True,
            'moneda_origen': resultado['moneda_origen'],
            'moneda_origen_nombre': resultado['moneda_origen_nombre'],
            'moneda_destino': resultado['moneda_destino'],
            'moneda_destino_nombre': resultado['moneda_destino_nombre'],
            'monto_origen': str(resultado['monto_origen']),
            'monto_destino': str(resultado['monto_destino']),
            'tasa_aplicada': str(resultado['tasa_aplicada']),
            'tipo_operacion': resultado['tipo_operacion'],
            'descripcion_tasa': resultado['descripcion_tasa'],
            'fecha_tasa': resultado['fecha_tasa'].isoformat() if resultado['fecha_tasa'] else None,
            'cotizacion_id': resultado['cotizacion_id'],
            'es_simulacion': True,
            'aviso': resultado['aviso'],
        }
        return JsonResponse(payload, status=200)
    except ValueError as ve:
        return JsonResponse({'exito': False, 'error': str(ve)}, status=400)
    except Exception as e:
        return JsonResponse({'exito': False, 'error': str(e)}, status=500)


# ==============================================================================
# OPERACIONES DE CAMBIO: VENTA Y COMPRA DE MONEDA (IS2-16)
# ==============================================================================

@login_required
@login_required
def comprar_moneda(request):
    """
    Vista para que un usuario registre la compra de una moneda
    a favor de un cliente asignado (IS2-15).
    Al completarse, redirige al proceso de confirmación y pago (IS2-52).
    """
    from .forms import CompraMonedaForm
    from .services import (
        obtener_clientes_asignados_usuario,
        obtener_tasa_sugerida,
        registrar_operacion_cambio
    )
    from monedas.models import Moneda

    clientes_asignados = obtener_clientes_asignados_usuario(request.user)
    cliente_activo_id = request.session.get('cliente_activo_id')
    cliente_inicial = None
    if cliente_activo_id and clientes_asignados.filter(id=cliente_activo_id).exists():
        cliente_inicial = cliente_activo_id
    elif clientes_asignados.count() == 1:
        cliente_inicial = clientes_asignados.first().id

    monedas_activas = Moneda.objects.filter(activa=True).order_by('siglas')

    # Pre-calcular mapa de tasas sugeridas para el frontend
    tasas_map = {}
    for m in monedas_activas:
        tasa_info = obtener_tasa_sugerida(m, tipo='COMPRA')
        if tasa_info:
            tasas_map[m.id] = {
                'tasa': float(tasa_info['tasa_sugerida']),
                'compra': float(tasa_info['compra']),
                'venta': float(tasa_info['venta']),
                'par': tasa_info['par'],
                'fecha': tasa_info['fecha']
            }

    # Pre-calcular mapa de comisiones por cliente
    clientes_map = {}
    for c in clientes_asignados:
        clientes_map[c.id] = {
            'nombre': str(c),
            'documento': c.documento,
            'segmento': c.segmento,
            'segmento_display': c.get_segmento_display(),
            'porcentaje_comision': 0.5 if c.segmento == 'VIP' else (1.0 if c.segmento == 'CORPORATIVO' else 1.5)
        }

    if request.method == 'POST':
        form = CompraMonedaForm(request.POST, user=request.user)
        if form.is_valid():
            cliente = form.cleaned_data['cliente']
            moneda = form.cleaned_data['moneda']
            monto = form.cleaned_data['monto']
            tasa_aplicada = form.cleaned_data['tasa_aplicada']

            try:
                operacion, calculo = registrar_operacion_cambio(
                    cliente=cliente,
                    moneda=moneda,
                    tipo=Operacion.TipoOperacion.COMPRA,
                    monto=monto,
                    tasa_aplicada=tasa_aplicada,
                    usuario=request.user
                )
                messages.info(
                    request,
                    f'Operación de compra #{operacion.id} iniciada. '
                    f'Por favor revise la cotización vigente antes de confirmar el pago.'
                )
                return redirect('confirmar_operacion_pago', operacion_id=operacion.id)
            except Exception as e:
                messages.error(request, f"Error al procesar la operación de compra: {str(e)}")
        else:
            messages.error(request, "Por favor corrija los errores indicados en el formulario.")
    else:
        form = CompraMonedaForm(user=request.user, initial={'cliente': cliente_inicial})

    return render(request, 'cotizaciones/comprar_moneda.html', {
        'form': form,
        'clientes_asignados': clientes_asignados,
        'tiene_clientes': clientes_asignados.exists(),
        'cliente_inicial': cliente_inicial,
        'monedas': monedas_activas,
        'tasas_json': json.dumps(tasas_map),
        'clientes_json': json.dumps(clientes_map),
    })


@login_required
def venta_moneda_view(request):
    """
    Vista y flujo para vender moneda a nombre de un cliente asignado (IS2-16).
    Requerimientos:
    1. Requiere autenticación válida.
    2. Formulario con Cliente asignado, Moneda, Monto a vender y Tasa aplicada.
    3. Cálculo automático de la comisión correspondiente antes de confirmar.
    4. Registro de Operación: Tipo 'Venta', estado inicial obligatorio 'Pendiente'.
    """
    from .forms import VentaMonedaForm
    from .services import (
        obtener_clientes_asignados_usuario,
        obtener_tasa_sugerida,
        calcular_comision_operacion,
        registrar_operacion_cambio
    )
    from monedas.models import Moneda

    clientes_asignados = obtener_clientes_asignados_usuario(request.user)
    cliente_activo_id = request.session.get('cliente_activo_id')
    cliente_inicial = None
    if cliente_activo_id and clientes_asignados.filter(id=cliente_activo_id).exists():
        cliente_inicial = cliente_activo_id
    elif clientes_asignados.count() == 1:
        cliente_inicial = clientes_asignados.first().id

    monedas_activas = Moneda.objects.filter(activa=True).order_by('siglas')

    # Pre-calcular mapa de tasas sugeridas para el frontend en JSON
    tasas_map = {}
    for m in monedas_activas:
        tasa_info = obtener_tasa_sugerida(m, tipo='VENTA')
        if tasa_info:
            tasas_map[m.id] = {
                'tasa': float(tasa_info['tasa_sugerida']),
                'compra': float(tasa_info['compra']),
                'venta': float(tasa_info['venta']),
                'par': tasa_info['par'],
                'fecha': tasa_info['fecha']
            }

    # Pre-calcular mapa de comisiones por cliente
    clientes_map = {}
    for c in clientes_asignados:
        clientes_map[c.id] = {
            'nombre': str(c),
            'documento': c.documento,
            'segmento': c.segmento,
            'segmento_display': c.get_segmento_display(),
            'porcentaje_comision': 0.5 if c.segmento == 'VIP' else (1.0 if c.segmento == 'CORPORATIVO' else 1.5)
        }

    if request.method == 'POST':
        form = VentaMonedaForm(request.POST, user=request.user)
        if form.is_valid():
            cliente = form.cleaned_data['cliente']
            moneda = form.cleaned_data['moneda']
            monto = form.cleaned_data['monto']
            tasa_aplicada = form.cleaned_data['tasa_aplicada']

            try:
                operacion, calculo = registrar_operacion_cambio(
                    cliente=cliente,
                    moneda=moneda,
                    tipo=Operacion.TipoOperacion.VENTA,
                    monto=monto,
                    tasa_aplicada=tasa_aplicada,
                    usuario=request.user
                )

                messages.success(
                    request,
                    f"¡Operación de Venta #{operacion.id} registrada con éxito! "
                    f"Monto: {operacion.monto} {operacion.moneda.siglas} — Estado inicial: {operacion.get_estado_display()}."
                )
                return redirect('operacion_detalle', operacion_id=operacion.id)
            except Exception as e:
                messages.error(request, f"Error al procesar la operación de venta: {str(e)}")
        else:
            messages.error(request, "Por favor corrija los errores indicados en el formulario.")
    else:
        form = VentaMonedaForm(user=request.user, initial={'cliente': cliente_inicial})

    return render(request, 'cotizaciones/operaciones/venta.html', {
        'form': form,
        'clientes_asignados': clientes_asignados,
        'tiene_clientes': clientes_asignados.exists(),
        'cliente_inicial': cliente_inicial,
        'monedas': monedas_activas,
        'tasas_json': json.dumps(tasas_map),
        'clientes_json': json.dumps(clientes_map),
    })



@login_required
def detalle_operacion_view(request, operacion_id):
    """
    Muestra la ficha y comprobante detallado de una operación registrada.
    """
    operacion = get_object_or_404(Operacion.objects.select_related('cliente', 'moneda', 'registrado_por'), id=operacion_id)

    # Validar que el usuario tenga acceso a la operación
    roles = set(getattr(request, 'roles', [])) | set(getattr(request.user, 'roles', []))
    if hasattr(request.user, 'groups'):
        roles.update(request.user.groups.values_list('name', flat=True))
    roles_gestion = {'admin', 'supervisor', 'operador', 'empleado'}
    es_personal = bool(roles.intersection(roles_gestion)) or getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)

    if not es_personal:
        from .services import obtener_clientes_asignados_usuario
        clientes_ids = obtener_clientes_asignados_usuario(request.user).values_list('id', flat=True)
        if operacion.cliente_id not in clientes_ids and operacion.registrado_por_id != request.user.id:
            messages.error(request, "No tienes permiso para consultar esta operación.")
            return redirect('menu')

    return render(request, 'cotizaciones/operaciones/detalle.html', {
        'operacion': operacion,
        'es_personal': es_personal,
    })


@login_required
def listar_operaciones_view(request):
    """
    Listado y consulta de operaciones (Ventas y Compras) para el usuario autenticado.
    """
    from .services import obtener_clientes_asignados_usuario

    roles = set(getattr(request, 'roles', [])) | set(getattr(request.user, 'roles', []))
    if hasattr(request.user, 'groups'):
        roles.update(request.user.groups.values_list('name', flat=True))
    roles_gestion = {'admin', 'supervisor', 'operador', 'empleado'}
    es_personal = bool(roles.intersection(roles_gestion)) or getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)

    if es_personal:
        operaciones = Operacion.objects.all()
    else:
        clientes_ids = obtener_clientes_asignados_usuario(request.user).values_list('id', flat=True)
        operaciones = Operacion.objects.filter(cliente_id__in=clientes_ids)


    # Filtros opcionales
    tipo_filtro = request.GET.get('tipo', '').strip().upper()
    estado_filtro = request.GET.get('estado', '').strip().upper()
    q = request.GET.get('q', '').strip()

    if tipo_filtro and tipo_filtro in Operacion.TipoOperacion.values:
        operaciones = operaciones.filter(tipo=tipo_filtro)
    if estado_filtro and estado_filtro in Operacion.EstadoOperacion.values:
        operaciones = operaciones.filter(estado=estado_filtro)
    if q:
        from django.db.models import Q
        operaciones = operaciones.filter(
            Q(cliente__nombre__icontains=q) |
            Q(cliente__apellido__icontains=q) |
            Q(cliente__razon_social__icontains=q) |
            Q(cliente__documento__icontains=q) |
            Q(moneda__siglas__icontains=q) |
            Q(id__icontains=q)
        )

    operaciones = operaciones.select_related('cliente', 'moneda', 'registrado_por').order_by('-fecha')

    return render(request, 'cotizaciones/operaciones/lista.html', {
        'operaciones': operaciones,
        'tipo_filtro': tipo_filtro,
        'estado_filtro': estado_filtro,
        'q': q,
        'es_personal': es_personal,
        'tipos': Operacion.TipoOperacion.choices,
        'estados': Operacion.EstadoOperacion.choices,
    })


@login_required
@require_http_methods(["GET", "POST"])
def api_calcular_operacion(request):
    """
    Endpoint JSON para calcular la comisión y totales en tiempo real antes de confirmar.
    """
    from .services import calcular_comision_operacion

    data = request.POST if request.method == 'POST' else request.GET
    cliente_id = data.get('cliente_id') or data.get('cliente')
    monto = data.get('monto')
    tasa_aplicada = data.get('tasa_aplicada') or data.get('tasa')
    tipo = data.get('tipo', 'VENTA')

    if not all([cliente_id, monto, tasa_aplicada]):
        return JsonResponse({
            'exito': False,
            'error': 'Parámetros obligatorios: cliente_id, monto y tasa_aplicada.'
        }, status=400)

    try:
        resultado = calcular_comision_operacion(
            cliente=cliente_id,
            monto=monto,
            tasa_aplicada=tasa_aplicada,
            tipo=tipo
        )
        return JsonResponse({
            'exito': True,
            'tipo': resultado['tipo'],
            'monto': float(resultado['monto']),
            'tasa_aplicada': float(resultado['tasa_aplicada']),
            'subtotal': float(resultado['subtotal']),
            'segmento': resultado['segmento'],
            'porcentaje_comision': float(resultado['porcentaje_comision']),
            'comision': float(resultado['comision']),
            'total_neto': float(resultado['total_neto']),
        }, status=200)
    except ValueError as ve:
        return JsonResponse({'exito': False, 'error': str(ve)}, status=400)
    except Exception as e:
        return JsonResponse({'exito': False, 'error': f"Error en cálculo: {str(e)}"}, status=500)


@login_required
@require_http_methods(["GET"])
def api_tasa_vigente_operacion(request, moneda_id):
    """
    Endpoint JSON que retorna la tasa sugerida/vigente para una divisa en la operación.
    """
    from .services import obtener_tasa_sugerida

    tipo = request.GET.get('tipo', 'VENTA')
    info = obtener_tasa_sugerida(moneda_id, tipo=tipo)

    if not info:
        return JsonResponse({
            'exito': False,
            'mensaje': 'No se encontró cotización activa para esta divisa.'
        }, status=200)

    return JsonResponse({
        'exito': True,
        'tasa_sugerida': float(info['tasa_sugerida']),
        'compra': float(info['compra']),
        'venta': float(info['venta']),
        'par': info['par'],
        'fecha': info['fecha'],
        'cotizacion_id': info['cotizacion_id']
    }, status=200)


# =======================================================================
# Flujo de Confirmación, Validación de Cotización y Cancelación (IS2-52)
# =======================================================================

@login_required
def confirmar_operacion_pago(request, operacion_id):
    """
    Vista para el proceso de confirmación y pago de una transacción (IS2-52).
    - Criterio 1: Durante el proceso de confirmación/pago, valida si la cotización cambió respecto al inicio.
    - Criterio 2: Si cambió, notifica al usuario.
    - Criterio 3: Permite al usuario cancelar la transacción sin que se registre ningún cargo ni movimiento definitivo.
    """
    from django.shortcuts import get_object_or_404
    from django.contrib import messages
    from decimal import Decimal, ROUND_HALF_UP
    from .models import Operacion
    from .services import (
        verificar_cambio_cotizacion, 
        confirmar_y_pagar_operacion,
        cancelar_operacion_por_cambio_tasa
    )

    operacion = get_object_or_404(
        Operacion.objects.select_related('cliente', 'moneda'), 
        id=operacion_id
    )

    # Si ya está cancelada o pagada, redirigir con mensaje
    if operacion.estado == Operacion.EstadoOperacion.CANCELADA:
        messages.info(request, f"La transacción #{operacion.id} ya se encuentra cancelada. No se aplicó ningún cargo.")
        return redirect('listar_operaciones')

    if operacion.estado == Operacion.EstadoOperacion.PAGADA:
        messages.success(request, f"La transacción #{operacion.id} ya fue pagada y procesada.")
        return redirect('listar_operaciones')

    # Validación de cambio de cotización (Criterio 1)
    validacion = verificar_cambio_cotizacion(operacion)

    # Procesar acción vía POST
    if request.method == 'POST':
        accion = request.POST.get('accion', 'pagar')

        if accion == 'cancelar':
            # Cancelación de la transacción (Criterio 3)
            cancelar_operacion_por_cambio_tasa(
                operacion, 
                motivo=request.POST.get('motivo', 'Cancelada por cambio de cotización')
            )
            messages.success(
                request,
                f"La transacción #{operacion.id} ha sido cancelada exitosamente. "
                f"No se ha registrado ningún cargo ni movimiento financiero definitivo."
            )
            return redirect('listar_operaciones')

        elif accion == 'pagar':
            aceptar_cambio = request.POST.get('aceptar_cambio') == '1'

            if validacion['cambio'] and not aceptar_cambio:
                messages.error(
                    request,
                    "La cotización cambió. Por favor revise el nuevo valor y confirme si desea "
                    "aceptar la nueva cotización o cancelar la transacción."
                )
            else:
                try:
                    confirmar_y_pagar_operacion(operacion, aceptar_cambio_tasa=aceptar_cambio)
                    messages.success(
                        request,
                        f"¡Pago confirmado exitosamente! Transacción #{operacion.id} pagada."
                    )
                    return redirect('listar_operaciones')
                except ValueError as ve:
                    messages.error(request, str(ve))

    # Notificación al usuario si la cotización cambió (Criterio 2)
    if validacion['cambio']:
        messages.warning(request, validacion['notificacion'])

    # Totales para la pantalla
    total_inicial = (operacion.monto * operacion.tasa_aplicada + operacion.comision).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    tasa_actual = validacion['tasa_vigente'] if validacion['tasa_vigente'] is not None else operacion.tasa_aplicada
    total_actual = (operacion.monto * tasa_actual + operacion.comision).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return render(request, 'cotizaciones/operaciones/confirmar_pago.html', {
        'operacion': operacion,
        'validacion': validacion,
        'total_inicial': total_inicial,
        'total_actual': total_actual,
        'diferencia_total': (total_actual - total_inicial).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
    })


@login_required
@require_http_methods(["GET", "POST"])
def cancelar_operacion_view(request, operacion_id):
    """
    Cancela una transacción antes de realizar el pago (IS2-52).
    Criterio 3: Permite al usuario cancelar la transacción sin que se registre ningún cargo
    ni movimiento definitivo.
    """
    from django.shortcuts import get_object_or_404
    from django.contrib import messages
    from .models import Operacion
    from .services import cancelar_operacion_por_cambio_tasa

    operacion = get_object_or_404(
        Operacion.objects.select_related('cliente', 'moneda'), 
        id=operacion_id
    )

    try:
        motivo = request.POST.get('motivo', 'Cancelación voluntaria por cambio de cotización')
        cancelar_operacion_por_cambio_tasa(operacion, motivo=motivo, usuario=request.user)
        messages.success(
            request,
            f"La transacción #{operacion.id} ha sido cancelada exitosamente. "
            f"No se ha registrado ningún cargo ni movimiento definitivo."
        )
    except ValueError as ve:
        messages.error(request, str(ve))

    return redirect('listar_operaciones')


@login_required
@require_http_methods(["GET"])
def api_validar_tasa_operacion(request, operacion_id):
    """
    Endpoint JSON para validar si la cotización cambió respecto al inicio de la operación (IS2-52).
    """
    from django.shortcuts import get_object_or_404
    from .models import Operacion
    from .services import verificar_cambio_cotizacion

    operacion = get_object_or_404(Operacion, id=operacion_id)
    validacion = verificar_cambio_cotizacion(operacion)

    return JsonResponse({
        'exito': True,
        'operacion_id': operacion.id,
        'estado': operacion.estado,
        'cambio': validacion['cambio'],
        'tasa_inicial': float(validacion['tasa_inicial']),
        'tasa_vigente': float(validacion['tasa_vigente']) if validacion['tasa_vigente'] is not None else None,
        'diferencia': float(validacion['diferencia']),
        'porcentaje_variacion': float(validacion['porcentaje_variacion']),
        'notificacion': validacion['notificacion'],
        'puede_cancelar': operacion.estado == Operacion.EstadoOperacion.PENDIENTE,
    })


@login_required
@require_http_methods(["POST"])
def api_cancelar_operacion(request, operacion_id):
    """
    Endpoint API JSON para cancelar una operación sin cargos ni movimientos definitivos (IS2-52).
    """
    from django.shortcuts import get_object_or_404
    from .models import Operacion
    from .services import cancelar_operacion_por_cambio_tasa

    operacion = get_object_or_404(Operacion, id=operacion_id)

    try:
        data = json.loads(request.body) if request.body else {}
        motivo = data.get('motivo', 'Cancelación por cambio de cotización')
    except (json.JSONDecodeError, AttributeError):
        motivo = request.POST.get('motivo', 'Cancelación por cambio de cotización')

    try:
        op_cancelada = cancelar_operacion_por_cambio_tasa(operacion, motivo=motivo, usuario=request.user)
        return JsonResponse({
            'exito': True,
            'operacion_id': op_cancelada.id,
            'estado': op_cancelada.estado,
            'comision': float(op_cancelada.comision),
            'mensaje': (
                f"La transacción #{op_cancelada.id} fue cancelada exitosamente. "
                f"No se registró ningún cargo ni movimiento definitivo."
            )
        }, status=200)
    except ValueError as ve:
        return JsonResponse({'exito': False, 'error': str(ve)}, status=400)
    except Exception as e:
        return JsonResponse({'exito': False, 'error': str(e)}, status=500)



@login_required
def historial_operaciones(request):
    from .models import Operacion
    estado_filtro = request.GET.get('estado', '')
    operaciones_qs = Operacion.objects.select_related('cliente', 'moneda').order_by('-fecha')
    if estado_filtro:
        operaciones_qs = operaciones_qs.filter(estado=estado_filtro)
    return render(request, 'cotizaciones/historial_operaciones.html', {
        'operaciones': operaciones_qs,
        'estado_filtro': estado_filtro,
        'estados': Operacion.EstadoOperacion.choices,
    })

@login_required
def descargar_comprobante_operacion(request, operacion_id):
    from django.shortcuts import get_object_or_404
    from .models import Operacion
    operacion = get_object_or_404(Operacion, id=operacion_id)
    return render(request, 'cotizaciones/comprobante_operacion.html', {
        'operacion': operacion
    })
