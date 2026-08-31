# Keycloak & Login — Integrante 1

Historias cubiertas: IS2-11 (Iniciar sesión), IS2-13 (Cerrar sesión),
IS2-29 (Crear rol), IS2-30 (Modificar rol), IS2-31 (Asignar rol a usuario).

## 1. Levantar Keycloak

```bash
docker compose up -d
```

Levanta Keycloak en `http://localhost:8080` e importa `keycloak/realm-export.json`:
realm `global-exchange`, client `django-app`, roles `admin / operador /
supervisor / empleado / cliente`, `cliente` como rol por defecto para
autoregistro, autoregistro + verificación de email activados, y 2 usuarios
demo (`admin.demo`, `operador.demo`) ya con rol asignado.

Consola admin: `http://localhost:8080` → user `admin` / pass `admin`.

## 2. Configurar Django

```bash
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

El client secret en `realm-export.json` es `CHANGE_ME_IN_ENV` (dev). Para
uno real: Keycloak → Clients → django-app → Credentials → Regenerate, y
copiarlo a `.env`.

## 3. Demo para el checkpoint

**Crear + asignar rol (IS2-29 / IS2-31):**
1. Keycloak → realm `global-exchange` → Users → Add user.
2. Credentials → poner contraseña.
3. Role mapping → Assign role → elegir uno de los 5 roles de negocio.
4. Loguearse en `http://localhost:8000/login/` → mostrar que `/menu/` ya
   muestra ese rol sincronizado, y que `/solo-admin/` da 403 si el rol no
   es `admin`.

**Modificar rol (IS2-30):**
- Mostrar que el rol `cliente` es parte del `default-roles-global-exchange`
  compuesto (Keycloak → Realm roles → default-roles-global-exchange).
- Registrarse desde el link "Register" del login de Keycloak y mostrar que
  el usuario nuevo queda con rol `cliente` sin asignación manual.

**Cerrar sesión (IS2-13):**
- Desde `/menu/`, click en "Cerrar sesión" → vuelve a `/login/`.

## 4. Cómo funciona la autorización en Django

- `authentication/backends.py` (`KeycloakOIDCBackend`): en cada login lee
  `realm_access.roles` del token y sincroniza esos roles como `Group` de
  Django (crea el usuario Django si no existía, matcheando por email).
- `authentication/middleware.py` (`RolesMiddleware`): agrega `request.roles`
  a cada request.
- `authentication/decorators.py` (`@rol_requerido('admin', 'supervisor')`):
  protege una vista por rol. Sin sesión → redirige a login. Sin el rol → 403.

Para usar en vistas de otros módulos:

```python
from authentication.decorators import rol_requerido

@rol_requerido('admin', 'operador')
def mi_vista(request):
    ...
```

No usamos Django admin en ningún punto de este flujo: la gestión de
usuarios/roles es toda vía Keycloak, y la autorización en Django es por
Groups + decorador, no por `is_staff`.
