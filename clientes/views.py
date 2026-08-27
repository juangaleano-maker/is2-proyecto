from django.shortcuts import render

def elegir_cliente(request):
    seleccionado = None
    if request.method == 'POST':
        seleccionado = request.POST.get('cliente_seleccionado')
    
    return render(request, 'clientes/seleccionar.html', {
        'seleccionado': seleccionado
    })

