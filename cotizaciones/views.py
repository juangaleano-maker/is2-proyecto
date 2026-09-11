from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from authentication.decorators import rol_requerido
from .models import Cotizacion
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


