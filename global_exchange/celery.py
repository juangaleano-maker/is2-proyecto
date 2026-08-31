import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'global_exchange.settings')

app = Celery('global_exchange')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
