# clientes/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .forms import ClienteForm
from .models import Cliente


def listado_clientes(request):
    clientes = Cliente.objects.all().order_by("-creado_en")

    # Filtro simple por segmento (útil para el checkpoint de segmentación)
    segmento = request.GET.get("segmento")
    if segmento:
        clientes = clientes.filter(segmento=segmento)

    return render(request, "clientes/listado.html", {
        "clientes": clientes,
        "segmentos": Cliente.Segmento.choices,
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


def eliminar_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    if request.method == "POST":
        cliente.delete()
        messages.success(request, "Cliente eliminado.")
        return redirect("clientes:listado")
    return render(request, "clientes/eliminar_confirmacion.html", {"cliente": cliente})