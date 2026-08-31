# clientes/views.py
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .forms import ClienteForm
from .models import Cliente


#  Vistas HTML (Panel Administrativo)

def listado_clientes(request):
    """Panel principal y listado de clientes con estadísticas, búsqueda y filtros."""
    ver_inactivos = request.GET.get("ver_inactivos") == "1"
    segmento = request.GET.get("segmento", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    busqueda = request.GET.get("q", "").strip()

    clientes = Cliente.objects.all().order_by("-creado_en")

    if not ver_inactivos:
        clientes = clientes.filter(activo=True)

    if segmento:
        clientes = clientes.filter(segmento=segmento)

    if tipo:
        clientes = clientes.filter(tipo_persona=tipo)

    if busqueda:
        from django.db.models import Q
        clientes = clientes.filter(
            Q(documento__icontains=busqueda)
            | Q(nombre__icontains=busqueda)
            | Q(apellido__icontains=busqueda)
            | Q(razon_social__icontains=busqueda)
            | Q(email__icontains=busqueda)
            | Q(telefono__icontains=busqueda)
        )

    todos = Cliente.objects.all()
    stats = {
        "total": todos.count(),
        "activos": todos.filter(activo=True).count(),
        "inactivos": todos.filter(activo=False).count(),
        "vip": todos.filter(segmento="VIP", activo=True).count(),
        "corporativo": todos.filter(segmento="CORPORATIVO", activo=True).count(),
        "minorista": todos.filter(segmento="MINORISTA", activo=True).count(),
        "fisica": todos.filter(tipo_persona="FISICA", activo=True).count(),
        "juridica": todos.filter(tipo_persona="JURIDICA", activo=True).count(),
    }

    return render(request, "clientes/listado.html", {
        "clientes": clientes,
        "segmentos": Cliente.Segmento.choices,
        "tipos": Cliente.TipoPersona.choices,
        "ver_inactivos": ver_inactivos,
        "filtro_segmento": segmento,
        "filtro_tipo": tipo,
        "busqueda": busqueda,
        "stats": stats,
    })


def registrar_cliente(request):
    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            cliente = form.save()
            messages.success(request, f"Cliente «{cliente}» registrado correctamente.")
            return redirect("clientes:listado")
    else:
        form = ClienteForm()
    return render(request, "clientes/form.html", {"form": form, "titulo": "Registrar Nuevo Cliente"})


def detalle_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    return render(request, "clientes/detalle.html", {"cliente": cliente})


def editar_cliente(request, pk):
    """Modificar datos de un cliente existente (activo o inactivo)."""
    cliente = get_object_or_404(Cliente, pk=pk)

    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            messages.success(request, f"Los datos de «{cliente}» fueron actualizados correctamente.")
            return redirect("clientes:detalle", pk=cliente.pk)
    else:
        form = ClienteForm(instance=cliente)

    return render(request, "clientes/form.html", {
        "form": form,
        "titulo": "Modificar Cliente",
        "cliente": cliente,
    })


def desactivar_cliente(request, pk):
    """Baja lógica: marca el cliente como inactivo sin eliminar el registro."""
    cliente = get_object_or_404(Cliente, pk=pk)

    if not cliente.activo:
        messages.warning(request, "El cliente ya se encuentra inactivo.")
        return redirect("clientes:detalle", pk=cliente.pk)

    if request.method == "POST":
        cliente.activo = False
        cliente.save()
        messages.success(
            request,
            f"El cliente «{cliente}» fue desactivado correctamente."
        )
        return redirect("clientes:listado")

    return render(request, "clientes/desactivar_confirmacion.html", {"cliente": cliente})


def reactivar_cliente(request, pk):
    """Reactiva un cliente previamente desactivado."""
    cliente = get_object_or_404(Cliente, pk=pk)

    if cliente.activo:
        messages.warning(request, "El cliente ya se encuentra activo.")
        return redirect("clientes:detalle", pk=cliente.pk)

    if request.method == "POST":
        cliente.activo = True
        cliente.save()
        messages.success(request, f"El cliente «{cliente}» fue reactivado exitosamente.")
        return redirect("clientes:detalle", pk=cliente.pk)

    return render(request, "clientes/reactivar_confirmacion.html", {"cliente": cliente})


#  API REST

def _cliente_a_dict(cliente):
    """Serializa un Cliente a dict para la API."""
    return {
        "id": cliente.pk,
        "tipo_persona": cliente.tipo_persona,
        "tipo_persona_display": cliente.get_tipo_persona_display(),
        "segmento": cliente.segmento,
        "segmento_display": cliente.get_segmento_display(),
        "documento": cliente.documento,
        "nombre": cliente.nombre,
        "apellido": cliente.apellido,
        "razon_social": cliente.razon_social,
        "nombre_display": str(cliente),
        "email": cliente.email,
        "telefono": cliente.telefono,
        "direccion": cliente.direccion,
        "activo": cliente.activo,
        "creado_en": cliente.creado_en.isoformat(),
        "actualizado_en": cliente.actualizado_en.isoformat(),
    }


@csrf_exempt
def api_clientes(request):
    """
    GET  /clientes/api/  → lista de clientes activos (acepta ?segmento= y ?ver_inactivos=1)
    POST /clientes/api/  → crear nuevo cliente
    """
    if request.method == "GET":
        ver_inactivos = request.GET.get("ver_inactivos") == "1"
        qs = Cliente.objects.all().order_by("-creado_en")
        if not ver_inactivos:
            qs = qs.filter(activo=True)
        segmento = request.GET.get("segmento")
        if segmento:
            qs = qs.filter(segmento=segmento)
        return JsonResponse({"clientes": [_cliente_a_dict(c) for c in qs]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Cuerpo JSON inválido."}, status=400)

        form = ClienteForm(data)
        if form.is_valid():
            cliente = form.save()
            return JsonResponse(_cliente_a_dict(cliente), status=201)
        return JsonResponse({"errores": form.errors}, status=400)

    return JsonResponse({"error": "Método no permitido."}, status=405)


@csrf_exempt
def api_cliente_detalle(request, pk):
    """
    GET    /clientes/api/<pk>/  → detalle de un cliente
    PUT    /clientes/api/<pk>/  → modificar cliente
    DELETE /clientes/api/<pk>/  → baja lógica
    """
    cliente = get_object_or_404(Cliente, pk=pk)

    if request.method == "GET":
        return JsonResponse(_cliente_a_dict(cliente))

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Cuerpo JSON inválido."}, status=400)

        form = ClienteForm(data, instance=cliente)
        if form.is_valid():
            cliente = form.save()
            return JsonResponse(_cliente_a_dict(cliente))
        return JsonResponse({"errores": form.errors}, status=400)

    if request.method == "DELETE":
        if not cliente.activo:
            return JsonResponse({"error": "El cliente ya se encuentra inactivo."}, status=400)
        cliente.activo = False
        cliente.save()
        return JsonResponse({"mensaje": f"Cliente «{cliente}» desactivado correctamente."})

    return JsonResponse({"error": "Método no permitido."}, status=405)