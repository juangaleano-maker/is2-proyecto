from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from authentication.decorators import rol_requerido
from .models import Moneda
from .forms import MonedaForm, MonedaEditForm

@rol_requerido('admin', 'analista')
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
