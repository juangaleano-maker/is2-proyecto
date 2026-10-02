import re

with open('cotizaciones/templates/cotizaciones/operaciones/compra.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace all occurrences of Venta/venta with Compra/compra where semantically needed
replacements = [
    # Title and headings
    ("Venta de Moneda | Global Exchange", "Compra de Moneda | Global Exchange"),
    # Header gradient: venta uses green (#047857), compra uses blue/indigo
    ("linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #047857 100%)", 
     "linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #1d4ed8 100%)"),
    # Main heading
    ('<span>💱 Registrar Venta de Moneda</span>', '<span>💱 Registrar Compra de Moneda</span>'),
    ('<span>Venta de Divisa</span>', '<span>Compra de Divisa</span>'),
    # Description text
    ('Registre la venta de divisas', 'Registre la compra de divisas'),
    ('para registrar una venta', 'para registrar una compra'),
    # Form action redirect
    ("action=\"{% url 'operacion_venta' %}\"", "action=\"{% url 'comprar_moneda' %}\""),
    # Button text
    ('Registrar Venta', 'Registrar Compra'),
    # TIPO hint
    ("'VENTA'", "'COMPRA'"),
    ("tipo='VENTA'", "tipo='COMPRA'"),
    # Script: tipo variable used in JS
    ("tipo: 'VENTA'", "tipo: 'COMPRA'"),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('cotizaciones/templates/cotizaciones/operaciones/compra.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("compra.html customized successfully.")
