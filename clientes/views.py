# clientes/views.py
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .forms import ClienteForm, MedioDePagoForm
from .models import Cliente, MedioDePago

def elegir_cliente(request):
    """
    Selector de cliente activo en sesión.
    Permite al usuario seleccionar el cliente con el que desea operar/consultar durante la sesión.
    """
    user_email = request.user.email or request.user.username
    roles = set(getattr(request, 'roles', []))
    roles_gestion = {'admin', 'supervisor', 'operador', 'empleado'}
    es_personal = bool(roles.intersection(roles_gestion))

    if es_personal:
        clientes = Cliente.objects.filter(activo=True).order_by('nombre')
    else:
        from agregar_usuario.models import UsuarioCliente
        from django.db import models
        clientes_ids = UsuarioCliente.objects.filter(email__iexact=user_email).values_list('cliente_id', flat=True)
        clientes = Cliente.objects.filter(models.Q(id__in=clientes_ids) | models.Q(email__iexact=user_email), activo=True).order_by('nombre')
        
    seleccionado = None

    cliente_activo_id = request.session.get('cliente_activo_id')
    if cliente_activo_id:
        seleccionado = Cliente.objects.filter(id=cliente_activo_id, activo=True).first()

    if request.method == 'POST':
        seleccionado_id = request.POST.get('cliente_seleccionado')
        if seleccionado_id:
            seleccionado = get_object_or_404(Cliente, id=seleccionado_id, activo=True)
            request.session['cliente_activo_id'] = seleccionado.id
            request.session['cliente_activo_nombre'] = str(seleccionado)
            messages.success(request, f"Cliente activo en sesión establecido: «{seleccionado}»")
            return redirect('menu')

    return render(request, 'clientes/seleccionar.html', {
        'clientes': clientes,
        'seleccionado': seleccionado
    })

def consultar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    mensaje = None
    
    if request.method == 'POST':
        # Procesar la modificación de datos del cliente (RF9)
        cliente.nombre = request.POST.get('nombre')
        cliente.email = request.POST.get('email')
        cliente.telefono = request.POST.get('telefono')
        cliente.direccion = request.POST.get('direccion')
        cliente.save()
        mensaje = "¡Datos modificados y guardados con éxito en la Base de Datos!"
        
    return render(request, 'clientes/consultar.html', {
        'cliente': cliente,
        'mensaje': mensaje
    })



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
    # Mostrar medios de pago solo si este cliente es el activo en sesión
    cliente_activo_id = request.session.get('cliente_activo_id')
    medios_pago = MedioDePago.objects.filter(cliente=cliente).order_by('-creado_en') if str(cliente.pk) == str(cliente_activo_id) else None
    return render(request, "clientes/detalle.html", {"cliente": cliente, "medios_pago": medios_pago})



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

def agregar_medio_pago(request):
    cliente_activo_id = request.session.get('cliente_activo_id')
    
    if not cliente_activo_id:
        messages.error(request, "Debe seleccionar un cliente activo antes de registrar un medio de pago.")
        # Redirigir al home o donde tenga sentido
        return redirect('menu')
    
    cliente = get_object_or_404(Cliente, id=cliente_activo_id)
    
    if request.method == "POST":
        form = MedioDePagoForm(request.POST)
        if form.is_valid():
            medio_pago = form.save(commit=False)
            medio_pago.cliente = cliente
            medio_pago.save()
            messages.success(request, f"Medio de pago agregado correctamente para el cliente {cliente}.")
            # Se puede redirigir al detalle del cliente, asumo "clientes:detalle"
            return redirect("clientes:detalle", pk=cliente.pk)
    else:
        form = MedioDePagoForm()
        
    return render(request, "clientes/medio_pago_form.html", {
        "form": form,
        "cliente": cliente,
        "titulo": "Agregar Medio de Pago"
    })

def editar_medio_pago(request, pk):
    cliente_activo_id = request.session.get('cliente_activo_id')
    
    if not cliente_activo_id:
        messages.error(request, "Debe seleccionar un cliente activo antes de editar un medio de pago.")
        return redirect('menu')
        
    medio_pago = get_object_or_404(MedioDePago, pk=pk, cliente_id=cliente_activo_id)
    
    # Simulación de validación de transacciones pendientes (esto se reemplazará en el futuro sprint)
    # Aquí podríamos hacer un random o fijarlo en True para probar el warning.
    import random
    tiene_transacciones = random.choice([True, False])
    
    if request.method == "POST":
        form = MedioDePagoForm(request.POST, instance=medio_pago)
        confirmacion = request.POST.get('confirmacion_transacciones')
        
        if form.is_valid():
            if tiene_transacciones and confirmacion != 'true':
                # No ha confirmado, se recarga con advertencia
                return render(request, "clientes/medio_pago_form.html", {
                    "form": form,
                    "cliente": medio_pago.cliente,
                    "titulo": "Modificar Medio de Pago",
                    "advertencia_transacciones": True,
                    "medio_pago": medio_pago
                })
            
            form.save()
            messages.success(request, f"Medio de pago actualizado correctamente para el cliente {medio_pago.cliente}.")
            return redirect("clientes:detalle", pk=medio_pago.cliente.pk)
    else:
        form = MedioDePagoForm(instance=medio_pago)
        
    return render(request, "clientes/medio_pago_form.html", {
        "form": form,
        "cliente": medio_pago.cliente,
        "titulo": "Modificar Medio de Pago",
        "medio_pago": medio_pago,
        # Si tiene_transacciones es true la primera vez que entra, podríamos avisar o esperar al POST.
        # Lo haremos en el POST para que intente guardar y salte la alerta como pide el Criterio de Aceptación.
    })

def listar_medios_pago(request):
    cliente_activo_id = request.session.get('cliente_activo_id')
    
    if not cliente_activo_id:
        messages.error(request, "Debe seleccionar un cliente activo para ver sus medios de pago.")
        return redirect('menu')
        
    cliente = get_object_or_404(Cliente, id=cliente_activo_id)
    medios_pago = MedioDePago.objects.filter(cliente=cliente).order_by('-creado_en')
    
    return render(request, "clientes/medio_pago_list.html", {
        "cliente": cliente,
        "medios_pago": medios_pago,
        "titulo": "Mis Medios de Pago"
    })


def eliminar_medio_pago(request, pk):
    """
    Baja lógica de un medio de pago (lo marca como inactivo).
    Si tiene transacciones pendientes, el sistema impide la eliminación.
    """
    cliente_activo_id = request.session.get('cliente_activo_id')

    if not cliente_activo_id:
        messages.error(request, "Debe seleccionar un cliente activo para gestionar medios de pago.")
        return redirect('menu')

    medio_pago = get_object_or_404(MedioDePago, pk=pk, cliente_id=cliente_activo_id)

    if not medio_pago.activo:
        messages.warning(request, "Este medio de pago ya se encuentra inactivo.")
        return redirect("clientes:listar_medios_pago")

    # Simulación de transacciones pendientes (se reemplazará con el módulo real de transacciones)
    import random
    tiene_transacciones = random.choice([True, False])

    if request.method == "POST":
        if tiene_transacciones:
            # Si tiene transacciones pendientes, se bloquea el intento
            messages.error(
                request,
                f"No se puede eliminar el medio de pago «{medio_pago}» porque tiene transacciones pendientes asociadas."
            )
            return redirect("clientes:listar_medios_pago")

        medio_pago.activo = False
        medio_pago.save()
        messages.success(request, f"El medio de pago «{medio_pago}» fue desactivado correctamente.")
        return redirect("clientes:listar_medios_pago")

    # GET: mostrar pantalla de confirmación
    return render(request, "clientes/medio_pago_eliminar.html", {
        "medio_pago": medio_pago,
        "cliente": medio_pago.cliente,
        "tiene_transacciones": tiene_transacciones,
        "titulo": "Eliminar Medio de Pago",
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
