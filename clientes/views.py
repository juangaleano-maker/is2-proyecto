from django.shortcuts import render, get_object_or_404, redirect
from .models import Cliente

def elegir_cliente(request):
    clientes = Cliente.objects.all().order_by('nombre')
    seleccionado_id = None
    seleccionado = None
    
    if request.method == 'POST':
        seleccionado_id = request.POST.get('cliente_seleccionado')
        if seleccionado_id:
            seleccionado = get_object_or_404(Cliente, id=seleccionado_id)
            
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
