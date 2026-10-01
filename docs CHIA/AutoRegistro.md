# Auto‑registro de usuarios con Django y Keycloak

## 📋 Overview

Este documento describe **todo el flujo de autoregistro** implementado en el proyecto **is2‑proyecto**.  Incluye:
- Configuración de los *views* y *forms* de Django (sin usar el admin de Django).
- Uso de la **Admin API de Keycloak** para crear usuarios desde el formulario de registro.
- **Verificación por correo** mediante la acción requerida de Keycloak (o un webhook/callback en Django).
- Manejo del **estado del usuario** (pendiente de verificación → activo).
- Instrucciones de despliegue y pruebas.

> **Nota:** Esta documentación está generada automáticamente a partir del código fuente presente en el repositorio y complementada con la conversación mantenida con la IA (CHIA).  Se almacena en `docs/AutoRegistro.md`.

---

## 🏗️ Arquitectura del flujo

```mermaid
flowchart TD
    A[Usuario abre página de registro] --> B[Formulario Django (RegisterForm)]
    B --> C[POST → RegisterView]
    C --> D[Keycloak Admin API: crear usuario]
    D --> E{¿Creación OK?}
    E -->|Sí| F[Asignar rol "cliente" en Keycloak]
    F --> G[Generar acción requerida "VERIFY_EMAIL"]
    G --> H[Keycloak envía email de verificación]
    H --> I[Usuario confirma email]
    I --> J[Keycloak actualiza estado a "ACTIVE"]
    J --> K[Webhook/Django POST /keycloak/callback]
    K --> L[Actualizar modelo UserProfile (estado = activo)]
    E -->|No| M[Mostrar error en formulario]
```

---

## 📂 Código involucrado

| Archivo | Propósito |
|---|---|
| `authentication/forms.py` | Define `RegisterForm` con campos: `username`, `email`, `password1`, `password2`. Validaciones personalizadas para dominio permitido y coincidencia de contraseñas. |
| `authentication/views.py` | `RegisterView` (class‑based) gestiona GET y POST. En POST llama a `keycloak_client.create_user(...)` y maneja respuestas. |
| `keycloak/client.py` | Wrapper sencillo alrededor de la **Admin REST API** de Keycloak (creación de usuarios, asignación de roles, envío de acciones requeridas). |
| `users/models.py` | Modelo `UserProfile` que enlaza con `auth.User` y almacena `keycloak_id` y `status` (`PENDING`, `ACTIVE`). |
| `users/signals.py` | Señal `post_save` para sincronizar cambios de estado con Keycloak (opcional). |
| `settings.py` | Variables de entorno `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`, y configuración de **SMTP** (`EMAIL_HOST`, `EMAIL_PORT`, ...). |
| `urls.py` | Ruta `path('register/', RegisterView.as_view(), name='register')`. |
| `templates/register.html` | Formulario HTML con `{{ form.as_p }}` y manejo de mensajes de error. |

---

## 🔐 Configuración de Keycloak

1. **Crear cliente confidencial**
   - `Client ID`: `django-app`
   - `Access Type`: `confidential`
   - Habilitar **Service Accounts**.
2. **Crear rol** `cliente` (u otro según tu dominio).
3. **Permitir acciones requeridas**: `Update Email`, `Verify Email`.
4. **Obtener credenciales** (`client‑secret`).
5. **Configurar variables de entorno** en ``.env`` o en el settings de Django:
   ```
   KEYCLOAK_URL=https://keycloak.example.com/auth
   KEYCLOAK_REALM=mi‑realm
   KEYCLOAK_CLIENT_ID=django-app
   KEYCLOAK_CLIENT_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

---

## 📧 Configuración SMTP (verificación por email)

En `settings.py`:
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'          # o tu servidor SMTP
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('SMTP_USER')
EMAIL_HOST_PASSWORD = os.getenv('SMTP_PASSWORD')
DEFAULT_FROM_EMAIL = 'no-reply@miapp.com'
```

Keycloak usará estas credenciales para enviar el correo de verificación al usuario recién creado.

---

## 🛠️ Paso a paso para desarrolladores

1. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```
2. **Aplicar migraciones**
   ```bash
   python manage.py migrate
   ```
3. **Crear super‑usuario de Django** (para acceso al admin interno si lo necesitas)
   ```bash
   python manage.py createsuperuser
   ```
4. **Ejecutar servidor local**
   ```bash
   python manage.py runserver
   ```
5. **Acceder a `/register/`** y probar con un email no registrado.
6. **Revisar Keycloak** → **Users** → debería aparecer el nuevo usuario en estado `UNVERIFIED`.
7. **Confirmar email** → después de hacer clic en el enlace, el usuario pasa a `ACTIVE` y el webhook de Django actualiza `UserProfile.status`.

---

## 🧪 Pruebas automáticas

```python
# tests/test_registration.py
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch

class RegistrationFlowTests(TestCase):
    def setUp(self):
        self.client = Client()

    @patch('keycloak.client.KeycloakClient.create_user')
    def test_successful_registration(self, mock_create):
        mock_create.return_value = {
            'id': '12345',
            'createdTimestamp': 0,
            'username': 'juan',
            'email': 'juan@example.com',
        }
        resp = self.client.post(reverse('register'), {
            'username': 'juan',
            'email': 'juan@example.com',
            'password1': 'Secret123!',
            'password2': 'Secret123!',
        })
        self.assertRedirects(resp, reverse('login'))
        # Verificar que el UserProfile fue creado con status=PENDING
        from users.models import UserProfile
        profile = UserProfile.objects.get(user__username='juan')
        self.assertEqual(profile.status, 'PENDING')
```

---

## 📚 Referencias a la conversación CHIA

El diseño de este flujo fue elaborado a partir de la conversación mantenida con la IA (documentada en `docs/CHIA.md`).  En esa charla, se definieron los requisitos de:
- **Separación de roles** (admin vs. cliente).
- **Redirección del login** para usuarios sin cliente asociado.
- **Selección obligatoria de cliente activo** en el menú.

Los cambios en los templates (`menu.html`, `base.html`) y el middleware de selección de cliente se describen en la sección **3.2** de `CHIA.md`.

---

## 🚀 Próximos pasos / Mejora continua

- Implementar **refresh token** automático para mantener la sesión de Keycloak.
- Añadir **recuperación de contraseña** mediante la API de Keycloak.
- Integrar **Webhooks** para eventos adicionales (p. ej., borrado de usuario).

---

*Este documento está actualizado a la última versión del repositorio (commit `1f0199d`).*
