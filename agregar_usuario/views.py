from django.shortcuts import render, redirect
from clientes.models import Cliente
from .models import UsuarioCliente
from django.contrib.auth.models import User

from authentication.decorators import rol_requerido

@rol_requerido('admin', 'supervisor', 'operador')
def agregar_usuario(request):
    """
    GET  → muestra el formulario con los clientes disponibles y los usuarios registrados
    POST → asocia el usuario seleccionado al cliente indicado
    """
    clientes = Cliente.objects.filter(activo=True).order_by('nombre')
    usuarios = User.objects.all().order_by('email')
    mensaje = None
    usuario_creado = None
    error = False

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        user_id = request.POST.get('user_id')
        rol = request.POST.get('rol', 'Empleado')

        if cliente_id and user_id:
            cliente = Cliente.objects.get(id=cliente_id)
            user = User.objects.get(id=user_id)
            
            if UsuarioCliente.objects.filter(cliente=cliente, email=user.email).exists():
                mensaje = f"El usuario '{user.email}' ya se encuentra asociado al cliente '{cliente.nombre}'."
                error = True
            else:
                usuario_creado = UsuarioCliente.objects.create(
                    cliente=cliente,
                    nombre=user.first_name or user.username,
                    apellido=user.last_name,
                    email=user.email,
                    rol=rol,
                )
                mensaje = f"¡Usuario '{user.email}' asociado exitosamente al cliente '{cliente.nombre}'!"

    return render(request, 'agregar_usuario/agregar.html', {
        'clientes': clientes,
        'usuarios': usuarios,
        'mensaje': mensaje,
        'error': error,
        'usuario_creado': usuario_creado,
    })
