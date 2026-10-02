import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('cotizaciones/templates/cotizaciones/operaciones/venta.html', encoding='utf-8') as f:
    content = f.read()

replacements = [
    # Page title
    ("{% block title %}Venta de Moneda | Global Exchange{% endblock %}",
     "{% block title %}Compra de Moneda | Global Exchange{% endblock %}"),
    # Header gradient color (green → blue)
    ("linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #047857 100%)",
     "linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #1d4ed8 100%)"),
    # Header title
    ("💵</span> Venta de Moneda", "💵</span> Compra de Moneda"),
    # Header description
    ("Registre una operación de venta de divisas en nombre de un cliente asignado.",
     "Registre una operación de compra de divisas a nombre de un cliente asignado."),
    # Form id and action
    ('<form method="post" id="ventaForm" novalidate>',
     '<form method="post" id="compraForm" action="{% url \'comprar_moneda\' %}" novalidate>'),
    # Client info label
    ("Selecciona el cliente a nombre del cual se realiza la venta.",
     "Selecciona el cliente a nombre del cual se realiza la compra."),
    # Confirm button
    ("✅</span> Confirmar Venta de Moneda", "✅</span> Confirmar Compra de Moneda"),
    # Resumen flujo label
    ("<strong>Flujo de Venta:</strong> El cliente entrega divisas a la entidad y recibe su contravalor en moneda local (PYG), deduciendo la comisión aplicable.",
     "<strong>Flujo de Compra:</strong> El cliente recibe divisas de la entidad entregando su contravalor en moneda local (PYG), más la comisión aplicable."),
    # Tipo operacion badge
    ('style="color: #047857;">VENTA DE DIVISAS', 'style="color: #1d4ed8;">COMPRA DE DIVISAS'),
    # JS: form variable name and references
    ("const ventaForm = document.getElementById('ventaForm');",
     "const ventaForm = document.getElementById('compraForm');"),
    # JS: tipo for API calls
    ("tipo: 'VENTA'", "tipo: 'COMPRA'"),
    ("tipo: \"VENTA\"", "tipo: \"COMPRA\""),
    # JS confirm dialog
    ("¿Confirmar operación de Venta de Moneda?\\n\\n",
     "¿Confirmar operación de Compra de Moneda?\\n\\n"),
    # IS2 badge
    ("Operación Cambiaria (IS2-16)", "Operación Cambiaria (IS2-15)"),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('cotizaciones/templates/cotizaciones/operaciones/compra.html', 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open('cotizaciones/templates/cotizaciones/operaciones/compra.html', encoding='utf-8') as f:
    result = f.read()

print("=== VERIFICATION ===")
print(f"Has 'Compra de Moneda': {'Compra de Moneda' in result}")
print(f"Has 'comprar_moneda' URL: {'comprar_moneda' in result}")
print(f"Has 'COMPRA DE DIVISAS': {'COMPRA DE DIVISAS' in result}")
print(f"Has 'VENTA DE DIVISAS': {'VENTA DE DIVISAS' in result}")
print(f"Has 'Confirmar Compra': {'Confirmar Compra' in result}")
print(f"Has 'compraForm': {'compraForm' in result}")
print("Done!")
