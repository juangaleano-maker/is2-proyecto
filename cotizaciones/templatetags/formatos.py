from django import template
from decimal import Decimal

register = template.Library()

def _formatear_miles(val, decimales=0):
    if val is None or val == '':
        return ''
    try:
        val = Decimal(str(val).replace(',', '.'))
    except Exception:
        return str(val)

    # En Paraguay y en este sistema, las monedas y cotizaciones se formatean con separador
    # de miles mediante punto (.) y sin comas decimales (,00).
    try:
        val_rounded = val.quantize(Decimal('1'))
    except Exception:
        val_rounded = Decimal(int(val))

    sign = '-' if val_rounded < 0 else ''
    int_str = f'{abs(int(val_rounded)):,}'.replace(',', '.')
    return f'{sign}{int_str}'


@register.filter(name='punto_miles')
def punto_miles(val, decimales=0):
    """
    Formatea un número utilizando punto (.) como separador de miles y sin comas.
    Ejemplos:
        5800.00 -> 5.800
        115160 -> 115.160
        1250000 -> 1.250.000
    """
    return _formatear_miles(val, decimales=0)


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

