from django import template
from decimal import Decimal

register = template.Library()

def _formatear_miles(val, decimales=2):
    if val is None or val == '':
        return ''
    try:
        val = Decimal(str(val).replace(',', '.'))
    except Exception:
        return str(val)

    try:
        decimales = int(decimales)
    except (ValueError, TypeError):
        decimales = 2

    if decimales == 0:
        val_rounded = val.quantize(Decimal('1'))
        sign = '-' if val_rounded < 0 else ''
        int_str = f'{abs(int(val_rounded)):,}'.replace(',', '.')
        return f'{sign}{int_str}'
    else:
        q = Decimal('10') ** -decimales
        val_rounded = val.quantize(q)
        sign = '-' if val_rounded < 0 else ''
        abs_val = abs(val_rounded)
        parts = f'{abs_val:,.{decimales}f}'.split('.')
        int_part = parts[0].replace(',', '.')
        dec_part = parts[1]
        return f'{sign}{int_part},{dec_part}'


@register.filter(name='punto_miles')
def punto_miles(val, decimales=2):
    """
    Formatea un número utilizando punto (.) como separador de miles y coma (,) como decimal.
    Ejemplos:
        5800.00 -> 5.800,00
        115160 -> 115.160,00 (con decimales=2)
        115160 -> 115.160 (con decimales=0)
    """
    return _formatear_miles(val, decimales)


@register.filter(name='guaranies')
def guaranies(val):
    """
    Formatea un monto en Guaraníes sin decimales con punto como separador de miles.
    Ejemplo: 1250000 -> 1.250.000
    """
    return _formatear_miles(val, decimales=0)


@register.filter(name='formato_gs')
def formato_gs(val):
    """
    Formatea un monto agregando prefijo Gs. y separador de miles con punto.
    Ejemplo: 1250000 -> Gs. 1.250.000
    """
    return f"Gs. {_formatear_miles(val, decimales=0)}"
