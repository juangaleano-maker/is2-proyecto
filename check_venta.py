import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('cotizaciones/templates/cotizaciones/operaciones/venta.html', encoding='utf-8') as f:
    lines = f.readlines()

for i, l in enumerate(lines):
    if 'Venta' in l or 'venta' in l or 'VENTA' in l or 'operacion_venta' in l:
        print(f"{i+1}: {l.rstrip()}")
