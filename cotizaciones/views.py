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
    return render(request, 'cotizaciones/registrar.html')

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
            moneda_origen=moneda_origen,
            moneda_destino=moneda_destino,
            compra=compra,
            venta=venta,
        )
        return JsonResponse({'mensaje': 'Cotización registrada exitosamente.', 'id': cotizacion.id}, status=201)
    except ValueError:
        return JsonResponse({'error': 'Los valores de compra y venta deben ser numéricos.'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Formato JSON inválido.'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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
    
    # Soporta parámetros vía GET o POST
    moneda_origen = request.GET.get('moneda_origen') or request.POST.get('moneda_origen') or 'USD'
    moneda_destino = request.GET.get('moneda_destino') or request.POST.get('moneda_destino') or 'PYG'
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

