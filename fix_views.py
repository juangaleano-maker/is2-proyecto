import re
import json

with open('cotizaciones/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

start_str = "@login_required\ndef venta_moneda_view(request):"
end_str = "        'clientes_json': json.dumps(clientes_map),\n    })"

start_idx = content.find(start_str)
end_idx = content.find(end_str) + len(end_str)

head_venta_moneda = """@login_required
def comprar_moneda(request):
    \"\"\"
    Vista para que un usuario registre la compra de una moneda 
    a favor de un cliente asignado (IS2-15).
    Al completarse, redirige al proceso de confirmación y pago (IS2-52).
    \"\"\"
    from django.contrib import messages
    from decimal import Decimal, ROUND_HALF_UP
    from .forms import ComprarMonedaForm
    from .models import Operacion

    if request.method == 'POST':
        form = ComprarMonedaForm(request.POST)
        if form.is_valid():
            operacion = form.save(commit=False)
            operacion.tipo = Operacion.TipoOperacion.COMPRA
            
            # Comisión estimada del 2%
            operacion.comision = (operacion.monto * Decimal('0.02')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            # Estado inicial PENDIENTE antes del pago
            operacion.estado = Operacion.EstadoOperacion.PENDIENTE
            operacion.save()

            messages.info(
                request, 
                f'Operación de compra #{operacion.id} iniciada. '
                f'Por favor revise la cotización vigente antes de confirmar el pago.'
            )
            return redirect('confirmar_operacion_pago', operacion_id=operacion.id)
    else:
        form = ComprarMonedaForm()
        
    return render(request, 'cotizaciones/comprar_moneda.html', {'form': form})


@login_required
def venta_moneda_view(request):
    \"\"\"
    Vista y flujo para vender moneda a nombre de un cliente asignado (IS2-16).
    Requerimientos:
    1. Requiere autenticación válida.
    2. Formulario con Cliente asignado, Moneda, Monto a vender y Tasa aplicada.
    3. Cálculo automático de la comisión correspondiente antes de confirmar.
    4. Registro de Operación: Tipo 'Venta', estado inicial obligatorio 'Pendiente'.
    \"\"\"
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
    })"""

new_content = content[:start_idx] + head_venta_moneda + content[end_idx:]

with open('cotizaciones/views.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("views.py fixed!")
