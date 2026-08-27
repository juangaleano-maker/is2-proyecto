
from django.test import TestCase
from .models import Cliente

class ClienteModelTest(TestCase):
    def test_no_permite_documento_duplicado(self):
        Cliente.objects.create(tipo_persona="FISICA", documento="123456", nombre="Juan", email="a@a.com")
        with self.assertRaises(Exception):
            Cliente.objects.create(tipo_persona="FISICA", documento="123456", nombre="Otro", email="b@b.com")