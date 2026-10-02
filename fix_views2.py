import re

with open('cotizaciones/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# -------------------------------------------------------------------
# 1. Replace comprar_moneda (lines 600-634)
# -------------------------------------------------------------------
old_comprar = '''@login_required
def comprar_moneda(request):
    """
    Vista para que un usuario registre la compra de una moneda \r
    a favor de un cliente asignado (IS2-15).\r
    Al completarse, redirige al proceso de confirmación y pago (IS2-52).
    """
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
        
    return render(request, 'cotizaciones/comprar_moneda.html', {'form': form})'''

new_comprar = '''@login_required
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

    return render(request, 'cotizaciones/operaciones/compra.html', {
        'form': form,
        'clientes_asignados': clientes_asignados,
        'tiene_clientes': clientes_asignados.exists(),
        'cliente_inicial': cliente_inicial,
        'monedas': monedas_activas,
        'tasas_json': json.dumps(tasas_map),
        'clientes_json': json.dumps(clientes_map),
    })'''

# -------------------------------------------------------------------
# 2. Fix the conflict marker in detalle_operacion_view docstring
# -------------------------------------------------------------------
old_detalle_marker = '    """\n<<<<<<< HEAD\n    Muestra la ficha y comprobante detallado de una operación registrada.'
new_detalle_marker = '    """\n    Muestra la ficha y comprobante detallado de una operación registrada.'

# Apply replacements using line-based approach
lines = content.split('\n')

# Find and replace old_comprar block
# It spans lines 600-634 (0-indexed: 599-633)
new_lines = []
i = 0
skip_until = -1
inserted_comprar = False

while i < len(lines):
    line = lines[i]
    
    # Detect start of comprar_moneda
    if not inserted_comprar and i >= 598 and 'def comprar_moneda(request):' in line:
        # Find end: next @login_required after this
        j = i + 1
        while j < len(lines) and not (lines[j].startswith('@login_required') and j > i + 5):
            j += 1
        # Replace range i to j-1
        new_lines.append(new_comprar)
        new_lines.append('')
        new_lines.append('')
        skip_until = j
        inserted_comprar = True
        i = j
        continue
    
    # Detect conflict marker in detalle docstring
    if '<<<<<<< HEAD' in line and i > 730:
        # skip this line (remove marker)
        i += 1
        continue
    
    new_lines.append(line)
    i += 1

content = '\n'.join(new_lines)

with open('cotizaciones/views.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done! views.py patched successfully.")
