from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from authentication.decorators import rol_requerido
from .models import Cotizacion, Operacion, AlertaTasa, NotificacionTasa
from .forms import CotizacionForm, AlertaTasaForm

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

    monedas_activas = Moneda.objects.filter(activa=True).exclude(siglas__iexact='PYG').order_by('siglas')

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

    roles = set(getattr(request, 'roles', [])) | set(getattr(request.user, 'roles', []))
    if hasattr(request.user, 'groups'):
        roles.update(request.user.groups.values_list('name', flat=True))
    roles_gestion = {'admin', 'supervisor', 'operador', 'empleado', 'cajero'}
    es_personal = bool(roles.intersection(roles_gestion)) or getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)

    from .models import SesionCaja
    sesion_caja_activa = None
    if 'cajero' in roles:
        sesion_caja_activa = SesionCaja.objects.filter(
            cajero=request.user,
            estado=SesionCaja.EstadoSesion.ABIERTA,
        ).first()
        if not sesion_caja_activa:
            messages.error(
                request,
                "⚠️ [RN16] Para registrar operaciones de compra en ventanilla, "
                "tu caja física asignada debe encontrarse abierta. "
                "Por favor apertura tu turno primero."
            )
            return redirect('apertura_caja')

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
                    usuario=request.user,
                    caja=sesion_caja_activa.caja if sesion_caja_activa else None,
                    sesion_caja=sesion_caja_activa,
                    canal='FISICO' if sesion_caja_activa else 'DIGITAL',
                )

                if es_personal:
                    messages.info(
                        request,
                        f'Operación de compra #{operacion.id} iniciada. '
                        f'Por favor revise la cotización vigente antes de confirmar el pago.'
                    )
                    return redirect('confirmar_operacion_pago', operacion_id=operacion.id)
                else:
                    messages.success(
                        request,
                        f'¡Operación de compra #{operacion.id} iniciada con éxito! '
                        f'Seleccioná tu método de pago (Stripe o SIPAP) para abonar tu pedido.'
                    )
                    return redirect('operacion_detalle', operacion_id=operacion.id)
            except Exception as e:
                messages.error(request, f"Error al procesar la operación de compra: {str(e)}")
        else:
            messages.error(request, "Por favor corrija los errores indicados en el formulario.")
    else:
        form = CompraMonedaForm(user=request.user, initial={'cliente': cliente_inicial})

    return render(request, 'cotizaciones/operaciones/compra.html', {
        'form': form,
        'clientes_asignados': clientes_asignados,
        'tiene_clientes': clientes_asignados.exists(),
        'cliente_inicial': cliente_inicial,
        'monedas': monedas_activas,
        'tasas_json': json.dumps(tasas_map),
        'clientes_json': json.dumps(clientes_map),
        'es_compra': True,
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

    monedas_activas = Moneda.objects.filter(activa=True).exclude(siglas__iexact='PYG').order_by('siglas')

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

    roles = set(getattr(request, 'roles', [])) | set(getattr(request.user, 'roles', []))
    if hasattr(request.user, 'groups'):
        roles.update(request.user.groups.values_list('name', flat=True))

    from .models import SesionCaja
    sesion_caja_activa = None
    if 'cajero' in roles:
        sesion_caja_activa = SesionCaja.objects.filter(
            cajero=request.user,
            estado=SesionCaja.EstadoSesion.ABIERTA,
        ).first()
        if not sesion_caja_activa:
            messages.error(
                request,
                "⚠️ [RN16] Para registrar operaciones de venta en ventanilla, "
                "tu caja física asignada debe encontrarse abierta. "
                "Por favor apertura tu turno primero."
            )
            return redirect('apertura_caja')

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
                    usuario=request.user,
                    caja=sesion_caja_activa.caja if sesion_caja_activa else None,
                    sesion_caja=sesion_caja_activa,
                    canal='FISICO' if sesion_caja_activa else 'DIGITAL',
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
        'es_compra': False,
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
    roles_gestion = {'admin', 'supervisor', 'operador', 'empleado', 'cajero'}
    es_personal = bool(roles.intersection(roles_gestion)) or getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)

    is_cajero = 'cajero' in roles and not bool({'admin', 'supervisor'} & roles)

    if is_cajero:
        # El Cajero solo tiene acceso a las operaciones de su caja asignada en su turno activo (RN15 y ERS Sección 4.1)
        from django.db import models
        from .models import SesionCaja
        sesion_activa = SesionCaja.objects.filter(
            cajero=request.user,
            estado=SesionCaja.EstadoSesion.ABIERTA,
        ).first()
        if sesion_activa:
            operaciones = Operacion.objects.filter(
                models.Q(sesion_caja=sesion_activa) |
                models.Q(registrado_por=request.user)
            )
        else:
            operaciones = Operacion.objects.filter(registrado_por=request.user)
    elif es_personal:
        operaciones = Operacion.objects.all()
    else:
        cliente_activo_id = request.session.get('cliente_activo_id')
        clientes_asignados = list(obtener_clientes_asignados_usuario(request.user).values_list('id', flat=True))
        if cliente_activo_id and cliente_activo_id in clientes_asignados:
            operaciones = Operacion.objects.filter(cliente_id=cliente_activo_id)
        elif clientes_asignados:
            operaciones = Operacion.objects.filter(cliente_id__in=clientes_asignados)
        else:
            operaciones = Operacion.objects.filter(registrado_por=request.user)


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

    roles = set(getattr(request, 'roles', [])) | set(getattr(request.user, 'roles', []))
    if hasattr(request.user, 'groups'):
        roles.update(request.user.groups.values_list('name', flat=True))
    roles_gestion = {'admin', 'supervisor', 'operador', 'empleado', 'cajero'}
    es_personal = bool(roles.intersection(roles_gestion)) or getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)

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

            if not es_personal:
                # Clientes regulares: confirman la cotización y son derivados al pago digital (Stripe/SIPAP)
                if validacion['cambio'] and not aceptar_cambio:
                    messages.error(
                        request,
                        "La cotización cambió. Por favor revise el nuevo valor y confirme si desea "
                        "aceptar la nueva cotización o cancelar la transacción."
                    )
                else:
                    messages.success(
                        request,
                        "Cotización confirmada. Seleccioná tu método de pago digital (Stripe o SIPAP)."
                    )
                    return redirect('operacion_detalle', operacion_id=operacion.id)
            else:
                # IS2-61: Verificar que el cajero tenga una sesión de caja abierta antes de confirmar (RN16)
                from .models import SesionCaja
                sesion_caja_activa = SesionCaja.objects.filter(
                    cajero=request.user,
                    estado=SesionCaja.EstadoSesion.ABIERTA,
                ).first()
                if not sesion_caja_activa:
                    messages.error(
                        request,
                        "⚠️ [RN16] No tenés ninguna sesión de caja abierta. "
                        "Debés aperturar una caja antes de poder confirmar y registrar pagos."
                    )
                    return redirect('apertura_caja')

                if validacion['cambio'] and not aceptar_cambio:
                    messages.error(
                        request,
                        "La cotización cambió. Por favor revise el nuevo valor y confirme si desea "
                        "aceptar la nueva cotización o cancelar la transacción."
                    )
                else:
                    try:
                        if not operacion.registrado_por:
                            operacion.registrado_por = request.user
                        if not operacion.sesion_caja:
                            operacion.sesion_caja = sesion_caja_activa
                        if sesion_caja_activa.caja and not operacion.caja:
                            operacion.caja = sesion_caja_activa.caja
                        operacion.canal = 'FISICO'
                        operacion.save(update_fields=['registrado_por', 'sesion_caja', 'caja', 'canal'])

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
        'es_personal': es_personal,
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
    from .services import obtener_clientes_asignados_usuario

    roles = set(getattr(request, 'roles', [])) | set(getattr(request.user, 'roles', []))
    if hasattr(request.user, 'groups'):
        roles.update(request.user.groups.values_list('name', flat=True))
    roles_gestion = {'admin', 'supervisor', 'operador', 'empleado', 'cajero'}
    es_personal = bool(roles.intersection(roles_gestion)) or getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)

    estado_filtro = request.GET.get('estado', '')

    if es_personal:
        operaciones_qs = Operacion.objects.all()
    else:
        cliente_activo_id = request.session.get('cliente_activo_id')
        clientes_asignados = list(obtener_clientes_asignados_usuario(request.user).values_list('id', flat=True))
        if cliente_activo_id and cliente_activo_id in clientes_asignados:
            operaciones_qs = Operacion.objects.filter(cliente_id=cliente_activo_id)
        elif clientes_asignados:
            operaciones_qs = Operacion.objects.filter(cliente_id__in=clientes_asignados)
        else:
            operaciones_qs = Operacion.objects.filter(registrado_por=request.user)

    operaciones_qs = operaciones_qs.select_related('cliente', 'moneda').order_by('-fecha')
    if estado_filtro:
        operaciones_qs = operaciones_qs.filter(estado=estado_filtro)
    return render(request, 'cotizaciones/historial_operaciones.html', {
        'operaciones': operaciones_qs,
        'estado_filtro': estado_filtro,
        'estados': Operacion.EstadoOperacion.choices,
        'es_personal': es_personal,
    })

@login_required
def descargar_comprobante_operacion(request, operacion_id):
    from django.shortcuts import get_object_or_404
    from .models import Operacion
    operacion = get_object_or_404(Operacion, id=operacion_id)
    return render(request, 'cotizaciones/comprobante_operacion.html', {
        'operacion': operacion
    })


# ==============================================================================
# Vistas de Alertas y Notificaciones de Tasas (IS2-57 e IS2-58)
# ==============================================================================

@login_required
def configurar_alertas_view(request):
    """
    Vista principal para gestión de alertas de tasas y notificaciones (IS2-57 / IS2-58).
    Permite al usuario:
    1. Activar/desactivar seguimiento rápido de monedas ("Estar al pendiente").
    2. Configurar alertas por umbral específico de compra/venta.
    3. Ver sus alertas configuradas y el historial de notificaciones.
    """
    from monedas.models import Moneda

    monedas_activas = Moneda.objects.filter(activa=True)
    alertas_usuario = AlertaTasa.objects.filter(usuario=request.user).select_related('moneda')

    if request.method == 'POST':
        form = AlertaTasaForm(request.POST)
        if form.is_valid():
            alerta = form.save(commit=False)
            alerta.usuario = request.user
            alerta.save()
            messages.success(request, f"Alerta para {alerta.moneda.siglas} configurada con éxito.")
            return redirect('alertas_tasas')
        else:
            messages.error(request, "Por favor revise los datos del formulario de alerta.")
    else:
        form = AlertaTasaForm()

    # Monedas que el usuario está siguiendo con alerta tipo VARIACION
    monedas_seguidas_ids = set(
        alertas_usuario.filter(tipo=AlertaTasa.TipoAlerta.VARIACION, activa=True)
        .values_list('moneda_id', flat=True)
    )

    # Últimas cotizaciones vigentes para dar contexto
    cotizaciones_vigentes = {
        c.moneda_origen_id: c
        for c in Cotizacion.objects.filter(activo=True).select_related('moneda_origen')
    }

    monedas_info = []
    for m in monedas_activas:
        cot = cotizaciones_vigentes.get(m.id)
        monedas_info.append({
            'moneda': m,
            'siguiendo': m.id in monedas_seguidas_ids,
            'compra': cot.compra if cot else None,
            'venta': cot.venta if cot else None,
        })

    notificaciones_qs = NotificacionTasa.objects.filter(usuario=request.user)
    no_leidas_count = notificaciones_qs.filter(leida=False).count()
    notificaciones_recientes = notificaciones_qs.select_related('moneda').order_by('-fecha_creacion')[:30]

    return render(request, 'cotizaciones/alertas.html', {
        'form': form,
        'monedas_info': monedas_info,
        'alertas': alertas_usuario,
        'notificaciones': notificaciones_recientes,
        'no_leidas_count': no_leidas_count,
    })


@login_required
@require_http_methods(["POST"])
def api_toggle_moneda_seguimiento(request, moneda_id):
    """
    Endpoint rápido para suscribirse / desuscribirse de una moneda con un solo clic.
    Crea o elimina la alerta de tipo VARIACION (estar al pendiente de la tasa).
    """
    from monedas.models import Moneda
    moneda = get_object_or_404(Moneda, id=moneda_id, activa=True)

    alertas_existentes = AlertaTasa.objects.filter(
        usuario=request.user,
        moneda=moneda,
        tipo=AlertaTasa.TipoAlerta.VARIACION
    )

    if alertas_existentes.exists():
        # Eliminar todas (incluyendo duplicados) → queda desuscripto
        alertas_existentes.delete()
        siguiendo = False
        mensaje = f"Ya no estás siguiendo las variaciones de {moneda.siglas}."
    else:
        AlertaTasa.objects.get_or_create(
            usuario=request.user,
            moneda=moneda,
            tipo=AlertaTasa.TipoAlerta.VARIACION,
            defaults={'activa': True}
        )
        siguiendo = True
        mensaje = f"Ahora estás al pendiente de las variaciones de {moneda.siglas}."

    return JsonResponse({
        'exito': True,
        'siguiendo': siguiendo,
        'mensaje': mensaje,
        'moneda_siglas': moneda.siglas,
    })


@login_required
@require_http_methods(["POST"])
def api_seguir_todas_las_monedas(request):
    """Permite al usuario activar el seguimiento de variación para todas las monedas activas con un clic."""
    from monedas.models import Moneda
    monedas_activas = Moneda.objects.filter(activa=True)
    creadas = 0
    for moneda in monedas_activas:
        _, created = AlertaTasa.objects.get_or_create(
            usuario=request.user,
            moneda=moneda,
            tipo=AlertaTasa.TipoAlerta.VARIACION,
            defaults={'activa': True}
        )
        if created:
            creadas += 1

    return JsonResponse({
        'exito': True,
        'creadas': creadas,
        'mensaje': f'Ahora sigues todas las divisas activas ({monedas_activas.count()} monedas).'
    })


@login_required
@require_http_methods(["POST"])
def eliminar_alerta_view(request, alerta_id):
    """Elimina una alerta configurada por el usuario."""
    alerta = get_object_or_404(AlertaTasa, id=alerta_id, usuario=request.user)
    siglas = alerta.moneda.siglas
    alerta.delete()
    messages.success(request, f"Alerta para {siglas} eliminada correctamente.")
    return redirect('alertas_tasas')


@login_required
@require_http_methods(["GET"])
def api_notificaciones(request):
    """
    Endpoint JSON consumido por el widget de la campanita (navbar) en tiempo real.
    Retorna el contador de no leídas y la lista de las últimas notificaciones.
    """
    qs = NotificacionTasa.objects.filter(usuario=request.user).select_related('moneda')
    no_leidas_count = qs.filter(leida=False).count()
    ultimas = qs.order_by('-fecha_creacion')[:10]

    notificaciones_data = []
    for n in ultimas:
        fecha_str = n.fecha_actualizacion.strftime('%d/%m/%Y %H:%M') if n.fecha_actualizacion else ''
        notificaciones_data.append({
            'id': n.id,
            'moneda': n.moneda.siglas,
            'moneda_nombre': n.moneda.nombre,
            'titulo': n.titulo,
            'mensaje': n.mensaje,
            'tasa_compra': str(n.tasa_compra),
            'tasa_venta': str(n.tasa_venta),
            'fecha': fecha_str,
            'leida': n.leida,
        })

    return JsonResponse({
        'no_leidas_count': no_leidas_count,
        'notificaciones': notificaciones_data,
    })


@login_required
@require_http_methods(["POST"])
def api_marcar_notificaciones_leidas(request):
    """Marca todas las notificaciones del usuario actual como leídas."""
    actualizadas = NotificacionTasa.objects.filter(
        usuario=request.user,
        leida=False
    ).update(leida=True)

    return JsonResponse({
        'exito': True,
        'actualizadas': actualizadas,
        'mensaje': 'Todas las notificaciones fueron marcadas como leídas.'
    })


# ===========================================================================
# Apertura y Cierre de Caja (IS2-60)
# ===========================================================================

@rol_requerido('cajero', 'admin', 'operador', 'supervisor')
def apertura_caja_view(request):
    """
    Vista para aperturar una sesión de caja al inicio del turno (IS2-60).
    Asigna una caja física al cajero durante su turno (Definición ERS Pág 4, RN15).
    Valida que el cajero no tenga ya una sesión abierta y que la caja no esté ocupada (RN15, RN16).
    Registra el stock inicial de billetes por denominación (Definición ERS Pág 4).
    """
    from .models import Caja, SesionCaja, SaldoSesionMoneda, ConteoBilleteSesion, StockBilleteCaja
    from .forms import AperturaCajaForm
    from monedas.models import Moneda, DenominacionMoneda
    from django.db.models import Prefetch
    from decimal import Decimal

    # Verificar si el cajero ya tiene una sesión abierta
    sesion_activa = SesionCaja.objects.filter(
        cajero=request.user,
        estado=SesionCaja.EstadoSesion.ABIERTA,
    ).first()

    if sesion_activa:
        messages.warning(
            request,
            f'Ya tenés una sesión de caja abierta desde '
            f'{sesion_activa.fecha_apertura.strftime("%d/%m/%Y %H:%M")}. '
            f'Debés cerrarla antes de abrir una nueva.',
        )
        return redirect('caja_dashboard')

    cajas_disponibles = Caja.objects.filter(activa=True).order_by('numero')
    if not cajas_disponibles.exists():
        cajas_disponibles = [
            Caja.objects.create(numero=1, nombre='Caja 1 - Ventanilla Principal', sucursal='Casa Central', activa=True),
            Caja.objects.create(numero=2, nombre='Caja 2 - Ventanilla Rápida', sucursal='Casa Central', activa=True),
        ]

    # Solo considerar monedas activas con sus denominaciones activas
    monedas_activas = Moneda.objects.filter(activa=True).prefetch_related(
        Prefetch('denominaciones', queryset=DenominacionMoneda.objects.filter(activo=True).order_by('-valor'))
    ).order_by('id')

    if request.method == 'POST':
        caja_id = request.POST.get('caja_id', '').strip()
        caja_obj = None
        if caja_id:
            caja_obj = Caja.objects.filter(id=caja_id, activa=True).first()
            if caja_obj and caja_obj.esta_abierta:
                messages.error(
                    request,
                    f'⚠️ [RN15/RN16] La Caja #{caja_obj.numero} ({caja_obj.nombre}) ya tiene un turno abierto por otro cajero. '
                    f'Por favor selecciona una caja disponible.'
                )
                form = AperturaCajaForm(request.POST)
                return render(request, 'cotizaciones/caja/apertura.html', {
                    'form': form,
                    'monedas_activas': monedas_activas,
                    'cajas_disponibles': Caja.objects.filter(activa=True).order_by('numero'),
                })

        if not caja_obj:
            for c in Caja.objects.filter(activa=True).order_by('numero'):
                if not c.esta_abierta:
                    caja_obj = c
                    break
            if not caja_obj:
                caja_obj = Caja.objects.first()

        nombre_caja = request.POST.get('nombre_caja', '').strip() or (caja_obj.nombre if caja_obj else 'Caja Principal')
        monto_inicial_pyg = Decimal('0.00')

        datos_por_moneda = {}
        for m in monedas_activas:
            total_m = Decimal('0.00')
            conteos_m = []
            for d in m.denominaciones.all():
                cant_str = request.POST.get(f'cant_billete_{d.id}', '0').strip()
                try:
                    cant = int(cant_str) if cant_str else 0
                except ValueError:
                    cant = 0
                if cant > 0:
                    sub = Decimal(str(cant)) * d.valor
                    total_m += sub
                    conteos_m.append((d, cant))

            monto_directo_str = request.POST.get(f'monto_inicial_moneda_{m.id}', '').strip()
            if monto_directo_str:
                try:
                    monto_directo = Decimal(monto_directo_str)
                    if monto_directo > total_m or (len(conteos_m) == 0):
                        total_m = monto_directo
                except Exception:
                    pass

            datos_por_moneda[m.id] = {
                'moneda': m,
                'total': total_m,
                'conteos': conteos_m,
            }
            if m.siglas.upper() == 'PYG':
                monto_inicial_pyg = total_m

        # Fallback si se usó el campo legado 'monto_inicial' del AperturaCajaForm
        monto_inicial_legacy = request.POST.get('monto_inicial', '').strip()
        if monto_inicial_legacy:
            try:
                legacy_dec = Decimal(monto_inicial_legacy)
                if legacy_dec > monto_inicial_pyg or monto_inicial_pyg == Decimal('0.00'):
                    monto_inicial_pyg = legacy_dec
                    for m_id, info in datos_por_moneda.items():
                        if info['moneda'].siglas.upper() == 'PYG':
                            info['total'] = legacy_dec
            except Exception:
                pass

        sesion = SesionCaja.objects.create(
            caja=caja_obj,
            cajero=request.user,
            nombre_caja=nombre_caja,
            monto_inicial=monto_inicial_pyg,
        )

        for m_id, info in datos_por_moneda.items():
            SaldoSesionMoneda.objects.create(
                sesion=sesion,
                moneda=info['moneda'],
                monto_inicial=info['total'],
            )
            for d, cant in info['conteos']:
                ConteoBilleteSesion.objects.create(
                    sesion=sesion,
                    denominacion=d,
                    momento=ConteoBilleteSesion.MomentoConteo.APERTURA,
                    cantidad=cant,
                    cantidad_sistema=cant,
                    diferencia_piezas=0,
                )
                if caja_obj:
                    StockBilleteCaja.objects.update_or_create(
                        caja=caja_obj,
                        denominacion=d,
                        defaults={'cantidad': cant}
                    )

        messages.success(
            request,
            f'✅ Caja "{sesion.nombre_caja}" aperturada correctamente con control multidivisa '
            f'({monedas_activas.count()} monedas activas monitoreadas).',
        )
        return redirect('caja_dashboard')

    form = AperturaCajaForm()
    return render(request, 'cotizaciones/caja/apertura.html', {
        'form': form,
        'monedas_activas': monedas_activas,
        'cajas_disponibles': Caja.objects.filter(activa=True).order_by('numero'),
    })


@rol_requerido('cajero', 'admin', 'operador', 'supervisor')
def caja_dashboard_view(request):
    """
    Dashboard del cajero: muestra el estado multidivisa de la sesión actual,
    la caja física asignada (RN15), operaciones físicas del turno y movimientos (IS2-60/61).
    """
    from .models import SesionCaja, MovimientoCaja, ConteoBilleteSesion
    from decimal import Decimal

    sesion_activa = SesionCaja.objects.select_related('caja', 'cajero').filter(
        cajero=request.user,
        estado=SesionCaja.EstadoSesion.ABIERTA,
    ).first()

    sesiones_cerradas = SesionCaja.objects.select_related('caja').filter(
        cajero=request.user,
        estado=SesionCaja.EstadoSesion.CERRADA,
    ).order_by('-fecha_cierre')[:10]

    movimientos_turno = []
    operaciones_turno = []
    conteos_apertura = []
    saldo_estimado = None
    total_ingresos = Decimal('0.00')
    total_egresos = Decimal('0.00')
    saldos_multidivisa = []

    if sesion_activa:
        movimientos_turno = sesion_activa.movimientos.select_related('operacion', 'registrado_por', 'moneda').all()
        operaciones_turno = sesion_activa.operaciones.select_related('cliente', 'moneda', 'registrado_por').order_by('-fecha')
        conteos_apertura = sesion_activa.conteos_billetes.filter(
            momento=ConteoBilleteSesion.MomentoConteo.APERTURA
        ).select_related('denominacion__moneda').order_by('denominacion__moneda', '-denominacion__valor')
        total_ingresos, total_egresos = sesion_activa.calcular_ingresos_turno()
        saldo_estimado = sesion_activa.calcular_saldo_esperado()
        saldos_multidivisa = sesion_activa.calcular_saldos_esperados_multidivisa()

    return render(request, 'cotizaciones/caja/dashboard.html', {
        'sesion_activa': sesion_activa,
        'sesiones_cerradas': sesiones_cerradas,
        'movimientos_turno': movimientos_turno,
        'operaciones_turno': operaciones_turno,
        'conteos_apertura': conteos_apertura,
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'saldo_estimado': saldo_estimado,
        'saldos_multidivisa': saldos_multidivisa,
    })


@rol_requerido('cajero', 'admin', 'operador', 'supervisor')
def historial_movimientos_view(request):
    """
    Historial de movimientos de caja (IS2-61).
    - Para Cajero: ve los movimientos de su sesión de caja actual y pasadas.
    - Para Admin / Supervisor: puede filtrar por cajero, tipo de movimiento y fechas.
    """
    from .models import MovimientoCaja, SesionCaja
    from django.contrib.auth.models import User
    from django.utils.dateparse import parse_date
    from decimal import Decimal


    user_roles = getattr(request, 'roles', set())
    is_admin = bool({'admin', 'supervisor'} & user_roles)

    movimientos = MovimientoCaja.objects.select_related('sesion', 'sesion__cajero', 'operacion', 'registrado_por')

    cajero_filtro = request.GET.get('cajero', '').strip()
    tipo_filtro = request.GET.get('tipo', '').strip()
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()

    if not is_admin:
        # El cajero regular solo ve movimientos de sus sesiones
        movimientos = movimientos.filter(sesion__cajero=request.user)
    else:
        # Administrador/supervisor puede filtrar por cualquier cajero
        if cajero_filtro:
            movimientos = movimientos.filter(sesion__cajero__id=cajero_filtro)

    if tipo_filtro in ['INGRESO', 'EGRESO']:
        movimientos = movimientos.filter(tipo=tipo_filtro)

    if fecha_desde:
        f_d = parse_date(fecha_desde)
        if f_d:
            movimientos = movimientos.filter(fecha__date__gte=f_d)

    if fecha_hasta:
        f_h = parse_date(fecha_hasta)
        if f_h:
            movimientos = movimientos.filter(fecha__date__lte=f_h)

    # Lista de cajeros disponibles para el dropdown del admin
    cajeros_list = []
    if is_admin:
        cajeros_ids = SesionCaja.objects.values_list('cajero_id', flat=True).distinct()
        cajeros_list = User.objects.filter(id__in=cajeros_ids).order_by('first_name', 'username')

    # Totales acumulados del conjunto filtrado
    from django.db.models import Sum
    total_ingresos = movimientos.filter(tipo='INGRESO').aggregate(s=Sum('monto'))['s'] or Decimal('0.00')
    total_egresos = movimientos.filter(tipo='EGRESO').aggregate(s=Sum('monto'))['s'] or Decimal('0.00')

    return render(request, 'cotizaciones/caja/movimientos.html', {
        'movimientos': movimientos[:100],  # límite de 100 más recientes
        'is_admin': is_admin,
        'cajeros_list': cajeros_list,
        'cajero_filtro': cajero_filtro,
        'tipo_filtro': tipo_filtro,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'total_ingresos': total_ingresos,
        'total_egresos': total_egresos,
        'balance_neto': total_ingresos - total_egresos,
    })



@rol_requerido('cajero', 'admin', 'operador', 'supervisor')
def cierre_caja_view(request):
    """
    Vista para cerrar la sesión de caja activa.
    Cumple taxativamente RN17: El cierre de turno de una caja solo podrá completarse
    luego de haber registrado el arqueo de billetes correspondiente a cada denominación
    de las divisas habilitadas en dicha caja.
    Compara la cantidad de billetes registrada por el sistema con la contada físicamente en la caja (Definición ERS Pág 4).
    """
    from .models import SesionCaja, SaldoSesionMoneda, ConteoBilleteSesion, StockBilleteCaja
    from .forms import CierreCajaForm
    from monedas.models import Moneda, DenominacionMoneda
    from django.db.models import Prefetch
    from decimal import Decimal

    sesion_activa = SesionCaja.objects.filter(
        cajero=request.user,
        estado=SesionCaja.EstadoSesion.ABIERTA,
    ).first()

    if not sesion_activa:
        messages.error(
            request,
            'No tenés ninguna sesión de caja abierta. Debés aperturar la caja primero.',
        )
        return redirect('apertura_caja')

    # Monedas activas con sus denominaciones
    monedas_activas = Moneda.objects.filter(activa=True).prefetch_related(
        Prefetch('denominaciones', queryset=DenominacionMoneda.objects.filter(activo=True).order_by('-valor'))
    ).order_by('id')

    saldos_multidivisa = sesion_activa.calcular_saldos_esperados_multidivisa()
    saldo_esperado_preview = sesion_activa.calcular_saldo_esperado()

    # Mapeo de conteos de billetes en apertura para obtener la cantidad registrada por el sistema
    conteos_apertura_map = {
        c.denominacion_id: c.cantidad
        for c in ConteoBilleteSesion.objects.filter(
            sesion=sesion_activa,
            momento=ConteoBilleteSesion.MomentoConteo.APERTURA
        )
    }

    if request.method == 'POST':
        observaciones = request.POST.get('observaciones', '').strip()
        monto_final_legacy_str = request.POST.get('monto_final_declarado', '').strip()

        tiene_campos_billetes = any(key.startswith('cant_cierre_billete_') for key in request.POST.keys())

        monto_final_pyg = Decimal('0.00')
        if monto_final_legacy_str:
            try:
                monto_final_pyg = Decimal(monto_final_legacy_str)
            except Exception:
                pass

        hay_diferencias = False
        resumen_arqueo = []
        datos_arqueo_map = {item['moneda'].id: item for item in saldos_multidivisa}

        for m in monedas_activas:
            info_esp = datos_arqueo_map.get(m.id, {})
            esperado = info_esp.get('saldo_esperado', Decimal('0.00'))

            # 1. Conteo de billetes para esta moneda
            total_declarado_m = Decimal('0.00')
            conteos_m = []
            denominaciones_activas = m.denominaciones.filter(activo=True)

            for d in denominaciones_activas:
                cant_str = request.POST.get(f'cant_cierre_billete_{d.id}', '').strip()
                try:
                    cant = int(cant_str) if cant_str else 0
                except ValueError:
                    cant = 0

                sub = Decimal(str(cant)) * d.valor
                total_declarado_m += sub

                # Cantidad registrada por el sistema (inicial de apertura)
                cant_sistema = conteos_apertura_map.get(d.id, 0)
                dif_piezas = cant - cant_sistema
                conteos_m.append((d, cant, cant_sistema, dif_piezas))

            # 2. O ingreso directo si la moneda no tiene denominaciones configuradas
            monto_directo_str = request.POST.get(f'monto_final_moneda_{m.id}', '').strip()
            if monto_directo_str:
                try:
                    m_dec = Decimal(monto_directo_str)
                    if not denominaciones_activas.exists() or m_dec > total_declarado_m or (len(conteos_m) == 0):
                        total_declarado_m = m_dec
                except Exception:
                    pass

            if m.siglas.upper() == 'PYG' and monto_final_legacy_str and not tiene_campos_billetes:
                try:
                    total_declarado_m = Decimal(monto_final_legacy_str)
                except Exception:
                    pass

            if m.siglas.upper() == 'PYG':
                monto_final_pyg = total_declarado_m

            dif = total_declarado_m - esperado
            if dif != Decimal('0.00'):
                hay_diferencias = True

            saldo_obj, _ = SaldoSesionMoneda.objects.get_or_create(
                sesion=sesion_activa,
                moneda=m,
                defaults={'monto_inicial': Decimal('0.00')}
            )
            saldo_obj.monto_final_declarado = total_declarado_m
            saldo_obj.saldo_esperado = esperado
            saldo_obj.diferencia = dif
            saldo_obj.save()

            for d, cant, cant_sis, dif_piezas in conteos_m:
                ConteoBilleteSesion.objects.create(
                    sesion=sesion_activa,
                    denominacion=d,
                    momento=ConteoBilleteSesion.MomentoConteo.CIERRE,
                    cantidad=cant,
                    cantidad_sistema=cant_sis,
                    diferencia_piezas=dif_piezas,
                )
                if sesion_activa.caja:
                    StockBilleteCaja.objects.update_or_create(
                        caja=sesion_activa.caja,
                        denominacion=d,
                        defaults={'cantidad': cant}
                    )

            resumen_arqueo.append({
                'moneda': m,
                'esperado': esperado,
                'declarado': total_declarado_m,
                'diferencia': dif,
                'tipo': saldo_obj.tipo_diferencia,
            })

        sesion_activa.cerrar(
            monto_final_declarado=monto_final_pyg,
            observaciones=observaciones,
        )

        caja_desc = f'Caja #{sesion_activa.caja.numero} "{sesion_activa.nombre_caja}"' if sesion_activa.caja else f'Caja "{sesion_activa.nombre_caja}"'
        if not hay_diferencias:
            messages.success(
                request,
                f'✅ {caja_desc} cerrada. Arqueo EXACTO en todas las divisas.',
            )
        else:
            detalles_dif = [f"{r['moneda'].siglas}: {r['diferencia']:+,.2f}" for r in resumen_arqueo if r['diferencia'] != 0]
            messages.warning(
                request,
                f'⚠️ {caja_desc} cerrada con diferencias en arqueo: ' + ', '.join(detalles_dif),
            )

        return redirect('caja_dashboard')

    form = CierreCajaForm()
    arqueo_items = []
    for item in saldos_multidivisa:
        m = item['moneda']
        denoms_con_sistema = []
        for d in m.denominaciones.filter(activo=True):
            cant_sis = conteos_apertura_map.get(d.id, 0)
            denoms_con_sistema.append({
                'denominacion': d,
                'cantidad_sistema': cant_sis,
                'subtotal_sistema': Decimal(str(cant_sis)) * d.valor
            })
        arqueo_items.append({
            'moneda': m,
            'saldo_esperado': item['saldo_esperado'],
            'denominaciones': denoms_con_sistema,
        })

    return render(request, 'cotizaciones/caja/cierre.html', {
        'form': form,
        'sesion': sesion_activa,
        'saldo_esperado_preview': saldo_esperado_preview,
        'monedas_activas': monedas_activas,
        'saldos_multidivisa': saldos_multidivisa,
        'arqueo_items': arqueo_items,
    })

