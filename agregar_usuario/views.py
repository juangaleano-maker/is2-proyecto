from django.shortcuts import render, redirect
from clientes.models import Cliente
from .models import UsuarioCliente


def agregar_usuario(request):
    """
    GET  → muestra el formulario con los clientes disponibles y los campos del nuevo usuario
    POST → guarda el nuevo usuario vinculado al cliente seleccionado y muestra confirmación
    """
    clientes = Cliente.objects.all().order_by('nombre')
    mensaje = None
    usuario_creado = None

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        nombre = request.POST.get('nombre')
        apellido = request.POST.get('apellido')
        email = request.POST.get('email')
        rol = request.POST.get('rol', 'Empleado')

        if cliente_id and nombre and email:
            cliente = Cliente.objects.get(id=cliente_id)
            usuario_creado = UsuarioCliente.objects.create(
                cliente=cliente,
                nombre=nombre,
                apellido=apellido,
                email=email,
                rol=rol,
            )
            mensaje = f"¡Usuario '{nombre} {apellido}' agregado exitosamente al cliente '{cliente.nombre}'!"

    return render(request, 'agregar_usuario/agregar.html', {
        'clientes': clientes,
        'mensaje': mensaje,
        'usuario_creado': usuario_creado,
    })
