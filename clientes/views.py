# clientes/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import ClienteForm
from .models import Cliente


def listado_clientes(request):
    # Por defecto solo se muestran clientes activos; ?ver_inactivos=1 incluye los inactivos
    ver_inactivos = request.GET.get("ver_inactivos") == "1"
    clientes = Cliente.objects.all().order_by("-creado_en")
    if not ver_inactivos:
        clientes = clientes.filter(activo=True)

    # Filtro por segmento
    segmento = request.GET.get("segmento")
    if segmento:
        clientes = clientes.filter(segmento=segmento)

    return render(request, "clientes/listado.html", {
        "clientes": clientes,
        "segmentos": Cliente.Segmento.choices,
        "ver_inactivos": ver_inactivos,
    })


def registrar_cliente(request):
    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Cliente registrado correctamente.")
            return redirect("clientes:listado")
    else:
        form = ClienteForm()
    return render(request, "clientes/form.html", {"form": form, "titulo": "Registrar Cliente"})


def detalle_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    return render(request, "clientes/detalle.html", {"cliente": cliente})


def editar_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, "Cliente actualizado correctamente.")
            return redirect("clientes:detalle", pk=cliente.pk)
    else:
        form = ClienteForm(instance=cliente)
    return render(request, "clientes/form.html", {"form": form, "titulo": "Editar Cliente"})


def desactivar_cliente(request, pk):
    """Baja lógica: marca el cliente como inactivo sin eliminar el registro."""
    cliente = get_object_or_404(Cliente, pk=pk)

    # Si ya está inactivo, no hacer nada
    if not cliente.activo:
        messages.warning(request, "El cliente ya se encuentra inactivo.")
        return redirect("clientes:detalle", pk=cliente.pk)

    if request.method == "POST":
        cliente.activo = False
        cliente.save()
        messages.success(
            request,
            f"El cliente «{cliente}» fue desactivado correctamente. El registro se conserva en el sistema."
        )
        return redirect("clientes:listado")

    return render(request, "clientes/desactivar_confirmacion.html", {"cliente": cliente})