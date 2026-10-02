try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    pass

# Compatibilidad con Python 3.14 en Django BaseContext.__copy__
try:
    import django.template.context as _ctx
    def _patched_copy(self):
        duplicate = object.__new__(self.__class__)
        duplicate.dicts = self.dicts[:]
        return duplicate
    _ctx.BaseContext.__copy__ = _patched_copy
except Exception:
    pass

