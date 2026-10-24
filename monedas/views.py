from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from authentication.decorators import rol_requerido
from .models import Moneda
from .forms import MonedaForm, MonedaEditForm

@rol_requerido('admin', 'analista', 'analista_cambiario')
def consultar_monedas(request):
    """
    Lista el catálogo completo de monedas con su estado.
    Permite filtrar por nombre mediante el parámetro '?q='.
    """
    query = request.GET.get('q', '').strip()
    
    if query:
        monedas = Moneda.objects.filter(nombre__icontains=query)
    else:
        monedas = Moneda.objects.all()
        
    return render(request, 'monedas/consultar.html', {
        'monedas': monedas,
        'query': query,
    })

@rol_requerido('admin')
def registrar_moneda(request):
    """
    Registra una nueva moneda habilitada en el sistema.
    La moneda se crea en estado activo por defecto.
    """
    if request.method == 'POST':
        form = MonedaForm(request.POST)
        if form.is_valid():
            moneda = form.save(commit=False)
            moneda.activa = True  # Aseguramos que se guarde activa
            moneda.save()
            messages.success(request, f'La moneda "{moneda.nombre} ({moneda.siglas})" fue registrada exitosamente.')
            return redirect('monedas:consultar')
    else:
        form = MonedaForm()

    return render(request, 'monedas/registrar.html', {
        'form': form,
    })

@rol_requerido('admin')
def alternar_estado_moneda(request, pk):
    """
    Alterna el estado (activa/inactiva) de una moneda.
    Garantiza que el historial no se borre al no eliminar el registro físico.
    Solo acepta solicitudes POST para prevenir cambios accidentales por GET.
    """
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])

    moneda = get_object_or_404(Moneda, pk=pk)
    
    # Invertir el estado
    moneda.activa = not moneda.activa
    moneda.save(update_fields=['activa'])
    
    accion = "activada" if moneda.activa else "desactivada"
    messages.success(request, f'La moneda "{moneda.nombre} ({moneda.siglas})" ha sido {accion} exitosamente.')
    
    return redirect('monedas:consultar')

@rol_requerido('admin')
def editar_moneda(request, pk):
    """
    Permite modificar los datos de una moneda existente (como su nombre y siglas).
    Si la moneda posee cotizaciones asociadas, el sistema requiere confirmación explícita
    para autorizar la modificación y preservar la integridad histórica.
    """
    moneda = get_object_or_404(Moneda, pk=pk)
    tiene_cotizaciones = moneda.tiene_cotizaciones()

    if request.method == 'POST':
        form = MonedaEditForm(request.POST, instance=moneda)
        confirmado = request.POST.get('confirmar_modificacion') in ['true', '1', 'on']

        if form.is_valid():
            if tiene_cotizaciones and not confirmado:
                form.add_error(None, 'Esta moneda tiene cotizaciones asociadas. Para guardar los cambios debe confirmar explícitamente.')
                return render(request, 'monedas/editar.html', {
                    'form': form,
                    'moneda': moneda,
                    'tiene_cotizaciones': True,
                    'requiere_confirmacion': True,
                })

            moneda = form.save()
            messages.success(request, f'La moneda "{moneda.nombre} ({moneda.siglas})" fue modificada exitosamente.')
            return redirect('monedas:consultar')
    else:
        form = MonedaEditForm(instance=moneda)

    return render(request, 'monedas/editar.html', {
        'form': form,
        'moneda': moneda,
        'tiene_cotizaciones': tiene_cotizaciones,
        'requiere_confirmacion': tiene_cotizaciones,
    })


@rol_requerido('admin', 'analista_cambiario')
def gestionar_denominaciones_moneda(request, moneda_id):
    """
    Permite ver y agregar denominaciones (cortes de billetes) para una moneda (RF38).
    Solo las denominaciones y monedas activas se consideran en apertura y arqueo de caja.
    """
    from decimal import Decimal, InvalidOperation
    from .models import DenominacionMoneda

    moneda = get_object_or_404(Moneda, pk=moneda_id)
    denominaciones = moneda.denominaciones.all().order_by('-valor')

    if request.method == 'POST':
        valor_raw = request.POST.get('valor', '').strip()
        try:
            valor = Decimal(valor_raw)
            if valor <= Decimal('0'):
                messages.error(request, 'El valor del billete debe ser mayor a cero.')
            else:
                _, created = DenominacionMoneda.objects.get_or_create(
                    moneda=moneda,
                    valor=valor,
                    defaults={'activo': True}
                )
                if created:
                    messages.success(request, f'Billete de {moneda.siglas} {valor:,.0f} agregado exitosamente.')
                else:
                    messages.warning(request, f'El billete de {moneda.siglas} {valor:,.0f} ya existe.')
                return redirect('monedas:gestionar_billetes', moneda_id=moneda.id)
        except (InvalidOperation, ValueError):
            messages.error(request, 'Ingrese un valor numérico válido para el billete.')

    return render(request, 'monedas/billetes.html', {
        'moneda': moneda,
        'denominaciones': denominaciones,
    })


@rol_requerido('admin', 'analista_cambiario')
def alternar_estado_denominacion(request, pk):
    """Alterna el estado activo/inactivo de una denominación de billete (RF38)."""
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])

    from .models import DenominacionMoneda
    denom = get_object_or_404(DenominacionMoneda, pk=pk)
    denom.activo = not denom.activo
    denom.save(update_fields=['activo'])
    estado_str = "activado" if denom.activo else "desactivado"
    messages.success(request, f'Billete {denom} {estado_str} correctamente.')
    return redirect('monedas:gestionar_billetes', moneda_id=denom.moneda_id)


@rol_requerido('admin', 'analista_cambiario')
def eliminar_denominacion(request, pk):
    """Elimina una denominación si no tiene registros históricos (RF38)."""
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])

    from .models import DenominacionMoneda
    denom = get_object_or_404(DenominacionMoneda, pk=pk)
    moneda_id = denom.moneda_id
    if hasattr(denom, 'conteos_sesion') and denom.conteos_sesion.exists():
        denom.activo = False
        denom.save(update_fields=['activo'])
        messages.warning(request, f'El billete {denom} tiene registros en caja; ha sido desactivado en lugar de eliminado.')
    else:
        denom.delete()
        messages.success(request, 'Denominación eliminada correctamente.')
    return redirect('monedas:gestionar_billetes', moneda_id=moneda_id)

