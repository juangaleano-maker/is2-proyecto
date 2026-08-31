from django.shortcuts import render, get_object_or_404, redirect
from .models import Usuario


def listar_usuarios(request):
    """Lista todos los usuarios disponibles para seleccionar cuál modificar."""
    usuarios = Usuario.objects.all().order_by('nombre')
    return render(request, 'usuarios/listar.html', {
        'usuarios': usuarios,
    })


def modificar_usuario(request, usuario_id):
    """Muestra y procesa el formulario de modificación de un usuario."""
    usuario = get_object_or_404(Usuario, id=usuario_id)
    mensaje = None

    if request.method == 'POST':
        usuario.nombre = request.POST.get('nombre')
        usuario.apellido = request.POST.get('apellido')
        usuario.email = request.POST.get('email')
        usuario.telefono = request.POST.get('telefono')
        usuario.rol = request.POST.get('rol')
        usuario.save()
        mensaje = "¡Datos del usuario modificados con éxito!"

    return render(request, 'usuarios/modificar.html', {
        'usuario': usuario,
        'mensaje': mensaje,
    })
