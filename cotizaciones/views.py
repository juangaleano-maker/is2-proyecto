from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from authentication.decorators import rol_requerido
from .models import Cotizacion
from .forms import CotizacionForm
import json
from django.http import JsonResponse
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
