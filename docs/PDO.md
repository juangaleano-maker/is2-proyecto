# PDO — Documentación Automática del Código Fuente

**Proyecto:** Global Exchange  
**Tecnología:** Django 5.1 + Keycloak 26 + PostgreSQL 16  
**Generado:** 2026-08-31  

---

## Tabla de Contenidos

1. [Configuración del sistema de documentación](#1-configuración-del-sistema-de-documentación)
2. [Arquitectura general del proyecto](#2-arquitectura-general-del-proyecto)
3. [Módulo authentication](#3-módulo-authentication)
4. [Módulo usuarios](#4-módulo-usuarios)
5. [Módulo clientes](#5-módulo-clientes)
6. [Módulo agregar_usuario](#6-módulo-agregar_usuario)
7. [Módulo global_exchange](#7-módulo-global_exchange)
8. [Cómo generar la documentación automáticamente](#8-cómo-generar-la-documentación-automáticamente)

---

## 1. Configuración del sistema de documentación

### Herramienta principal: `pydoc` (stdlib de Python)

El proyecto utiliza **pydoc**, incluido en la biblioteca estándar de Python, para generar documentación HTML a partir de los docstrings del código fuente. No requiere instalación de dependencias adicionales.

#### Generar documentación HTML

```bash
# Con el venv activo, desde la raíz del proyecto:
python -m pydoc -w authentication.backends
python -m pydoc -w authentication.middleware
python -m pydoc -w authentication.decorators
python -m pydoc -w usuarios.models
python -m pydoc -w usuarios.views
python -m pydoc -w usuarios.services.keycloak_service
python -m pydoc -w usuarios.services.email_service
python -m pydoc -w clientes.models
python -m pydoc -w clientes.views
python -m pydoc -w agregar_usuario.models
python -m pydoc -w agregar_usuario.views
```

#### Ver documentación en el navegador (servidor local)

```bash
python -m pydoc -p 9999
# Abrir en: http://localhost:9999
```

#### Herramienta alternativa: `pdoc`

```bash
pip install pdoc
pdoc --output-dir docs/html authentication usuarios clientes agregar_usuario
```

### Convención de docstrings (PEP 257)

```python
def mi_funcion(param1, param2):
    """
    Descripción breve de la función.

    Args:
        param1: Descripción del primer parámetro.
        param2: Descripción del segundo parámetro.

    Returns:
        Descripción del valor de retorno.
    """
```

---

## 2. Arquitectura general del proyecto

```
is2-proyecto/
├── global_exchange/       # Configuración central (settings, urls, wsgi)
├── authentication/        # SSO con Keycloak, middleware, decoradores de rol
├── usuarios/              # Autoregistro, verificación por correo, perfiles
│   └── services/          # Servicios: Keycloak Admin API, Email
├── clientes/              # CRUD de clientes, segmentación, API REST
├── agregar_usuario/       # Asignación M2M usuario-cliente
├── templates/             # Templates HTML globales y por módulo
├── static/                # Archivos estáticos (CSS, JS, imágenes)
├── docs/                  # Documentación del proyecto
├── keycloak/              # Configuración y realm-export.json de Keycloak
├── Dockerfile             # Imagen Docker de desarrollo
├── docker-compose.yml     # Orquestación de servicios (dev)
└── requirements.txt       # Dependencias Python
```

| Componente | Tecnología |
|---|---|
| Framework web | Django 5.1 |
| Base de datos | PostgreSQL 16 |
| Autenticación SSO | Keycloak 26 (OIDC) |
| Librería OIDC | mozilla-django-oidc 4.0 |
| Email de prueba | MailHog |
| Contenedores | Docker + Docker Compose |
| Variables de entorno | python-decouple |

---

## 3. Módulo `authentication`

**Responsabilidad:** Integración SSO con Keycloak, control de acceso basado en roles, redirecciones canónicas y selección de cliente activo.

### `authentication/backends.py`

#### Clase `KeycloakOIDCBackend`

**Hereda de:** `mozilla_django_oidc.auth.OIDCAuthenticationBackend`

Backend de autenticación que integra Django con Keycloak vía OIDC. Identifica o crea usuarios por email y sincroniza sus roles desde el claim `realm_access.roles` de Keycloak como `Group` de Django.

| Método | Descripción |
|---|---|
| `filter_users_by_claims(claims)` | Busca usuarios existentes por email (case-insensitive). |
| `create_user(claims)` | Crea un nuevo usuario Django a partir del token OIDC y sincroniza sus roles. |
| `update_user(user, claims)` | Actualiza nombre/apellido y re-sincroniza roles en cada login. |
| `_sync_roles(user, claims)` | Refleja los grupos del claim `realm_access.roles` en Django. Solo procesa roles definidos en `ROLES_KEYCLOAK`. |

### `authentication/decorators.py`

#### Constante `ROLES_KEYCLOAK`

```python
ROLES_KEYCLOAK = ['admin', 'operador', 'supervisor', 'empleado', 'cliente']
```

#### Decorador `rol_requerido(*roles_permitidos)`

Combina `@login_required` con la verificación de rol. Si el usuario no tiene el rol → HTTP 403.

**Uso:**
```python
@rol_requerido('admin', 'supervisor')
def mi_vista(request):
    ...
```

### `authentication/middleware.py`

| Clase | Descripción |
|---|---|
| `RolesMiddleware` | Agrega `request.roles` (set) con los grupos del usuario autenticado. |
| `CanonicalHostMiddleware` | Redirige `127.0.0.1` → `localhost` para compatibilidad con Keycloak OIDC. |
| `ClientSelectionMiddleware` | Fuerza selección de cliente activo para usuarios con múltiples clientes asignados. |

### `authentication/views.py`

| Vista | Descripción |
|---|---|
| `login_view(request)` | Landing page con opciones de Login y Registro. |
| `logout_view(request)` | Cierra sesión Django y redirige al logout endpoint de Keycloak. |
| `menu(request)` | Menú principal post-login con contexto según rol y cliente activo. |
| `solo_admin(request)` | Vista demo restringida al rol `admin`. |

---

## 4. Módulo `usuarios`

**Responsabilidad:** Autoregistro, verificación por correo, perfiles y sincronización con Keycloak.

### `usuarios/models.py`

#### Enum `EstadoUsuario`

| Valor | Etiqueta |
|---|---|
| `PENDIENTE_VERIFICACION` | Pendiente de verificación |
| `ACTIVO` | Activo |
| `INACTIVO` | Inactivo |
| `BLOQUEADO` | Bloqueado |

#### Clase `PerfilUsuario`

Perfil extendido del usuario con ciclo de vida de verificación de cuenta.

| Campo | Tipo | Descripción |
|---|---|---|
| `user` | OneToOneField(User) | Referencia al usuario Django base |
| `keycloak_id` | CharField(128) | UUID asignado por Keycloak |
| `estado` | CharField (choices) | Estado actual (ver EstadoUsuario) |
| `email_verificado` | BooleanField | Si el correo fue verificado |
| `token_verificacion` | CharField(128) | Token de verificación (indexado) |
| `token_expiracion` | DateTimeField | Expiración del token |
| `creado_en` / `actualizado_en` | DateTimeField | Auditoría (auto) |

| Método | Descripción |
|---|---|
| `generar_token_verificacion()` | Genera token URL-safe de 32 bytes con expiración configurable. |
| `is_token_valido(token)` | Valida coincidencia y expiración del token. Retorna `bool`. |
| `activar_cuenta()` | Activa la cuenta: `estado=ACTIVO`, limpia token, activa usuario Django. |
| `esta_activo` (property) | `True` si estado, verificación y usuario Django están activos. |

### `usuarios/views.py`

#### Vistas HTML

| Vista | URL | Descripción |
|---|---|---|
| `RegistroView` | `/usuarios/registro/` | Autoregistro público con creación en Keycloak y envío de correo. |
| `RegistroExitosoView` | `/usuarios/registro/exitoso/` | Pantalla informativa post-registro. |
| `VerificarCorreoView` | `/usuarios/verificar/<token>/` | Activación de cuenta por token. |
| `ReenviarCorreoVerificacionView` | `/usuarios/reenviar-verificacion/` | Reenvío de link de verificación. |
| `EstadoCuentaView` | `/usuarios/estado/` | Consulta de estado por email/username. |
| `listar_usuarios` | `/usuarios/` | Listado de usuarios. |
| `modificar_usuario` | `/usuarios/<id>/modificar/` | Edición de datos de usuario. |

#### API REST (JSON)

| Endpoint | Método | URL |
|---|---|---|
| `APIRegistroView` | POST | `/usuarios/api/registro/` |
| `APIVerificarCorreoView` | POST | `/usuarios/api/verificar-correo/` |
| `APIReenviarVerificacionView` | POST | `/usuarios/api/reenviar-verificacion/` |
| `APIEstadoUsuarioView` | GET | `/usuarios/api/estado/?q=<email>` |

### `usuarios/services/keycloak_service.py`

#### Clase `KeycloakAdminService`

Integración con la Admin REST API de Keycloak. Soporta modo fallback/simulación.

| Método | Descripción |
|---|---|
| `get_admin_token()` | Obtiene token OAuth2 (password grant o client_credentials). |
| `crear_usuario(...)` | Crea usuario en Keycloak con `emailVerified=False` y acción `VERIFY_EMAIL`. |
| `enviar_correo_verificacion(keycloak_id)` | Dispara email de verificación desde Keycloak. |
| `marcar_email_verificado(keycloak_id)` | Actualiza `emailVerified=True` en Keycloak. |
| `obtener_usuario(keycloak_id)` | Retorna datos del usuario en Keycloak. |
| `obtener_id_por_username(username)` | Busca UUID de Keycloak por nombre de usuario. |

### `usuarios/services/email_service.py`

#### Función `enviar_correo_activacion(user, perfil, request=None)`

Genera token → construye URL → renderiza template HTML → envía email vía `send_mail` → dispara trigger opcional de Keycloak. Retorna la URL de verificación.

---

## 5. Módulo `clientes`

**Responsabilidad:** CRUD de clientes con segmentación, baja lógica y API REST.

### `clientes/models.py`

#### Clase `Cliente`

| Enums | Valores |
|---|---|
| `TipoPersona` | `FISICA`, `JURIDICA` |
| `Segmento` | `MINORISTA`, `CORPORATIVO`, `VIP` |

| Campo clave | Descripción |
|---|---|
| `documento` | CI o RUC (único) |
| `tipo_persona` | Tipo de persona |
| `segmento` | Segmento de mercado |
| `nombre` / `apellido` | Para personas físicas |
| `razon_social` | Para personas jurídicas |
| `activo` | Baja lógica |

### `clientes/views.py`

#### Vistas HTML

| Vista | URL | Descripción |
|---|---|---|
| `elegir_cliente` | `/clientes/seleccionarCliente/` | Selector de cliente activo en sesión. |
| `listado_clientes` | `/clientes/` | Listado con filtros y estadísticas. |
| `registrar_cliente` | `/clientes/nuevo/` | Alta de nuevo cliente. |
| `detalle_cliente` | `/clientes/<pk>/` | Detalle de cliente. |
| `editar_cliente` | `/clientes/<pk>/editar/` | Edición de datos. |
| `desactivar_cliente` | `/clientes/<pk>/desactivar/` | Baja lógica. |
| `reactivar_cliente` | `/clientes/<pk>/reactivar/` | Reactivación de cliente. |

#### API REST

| Endpoint | Métodos | URL |
|---|---|---|
| `api_clientes` | GET, POST | `/clientes/api/` |
| `api_cliente_detalle` | GET, PUT, DELETE | `/clientes/api/<pk>/` |

---

## 6. Módulo `agregar_usuario`

**Responsabilidad:** Relación M2M usuario ↔ cliente. Solo accesible para `admin`, `supervisor`, `operador`.

### `agregar_usuario/models.py`

#### Clase `UsuarioCliente`

| Campo | Descripción |
|---|---|
| `cliente` | FK a Cliente (cascade) |
| `nombre` / `apellido` | Datos del usuario |
| `email` | Identificador del usuario |
| `rol` | Rol en el contexto del cliente |

**Restricción:** `unique_together = ('cliente', 'email')`

### `agregar_usuario/views.py`

#### Función `agregar_usuario(request)`

**Decorador:** `@rol_requerido('admin', 'supervisor', 'operador')`

- **GET:** Muestra formulario con clientes activos y usuarios Django.
- **POST:** Crea `UsuarioCliente` o informa si la asociación ya existe.

---

## 7. Módulo `global_exchange`

**Responsabilidad:** Configuración central del proyecto Django.

### Variables de entorno clave (`settings.py`)

| Variable | Descripción | Default |
|---|---|---|
| `DB_NAME` | Nombre de la base de datos | `global_exchange` |
| `DB_USER` | Usuario PostgreSQL | `postgres` |
| `DB_PASSWORD` | Contraseña PostgreSQL | `123456` |
| `DB_HOST` | Host de PostgreSQL | `127.0.0.1` |
| `DB_PORT` | Puerto PostgreSQL | `5432` |
| `OIDC_RP_CLIENT_ID` | Client ID de Keycloak | `django-app` |
| `OIDC_RP_CLIENT_SECRET` | Client Secret de Keycloak | _(requerido)_ |
| `KEYCLOAK_BASE_URL` | URL del servidor Keycloak | `http://localhost:8080` |
| `KEYCLOAK_REALM` | Nombre del realm | `global-exchange` |
| `EMAIL_BACKEND` | Backend de correo | Console (dev) |
| `APP_BASE_URL` | URL base para links en emails | `http://127.0.0.1:8000` |
| `EMAIL_TOKEN_EXPIRATION_HOURS` | Validez del token de verificación | `24` |

---

## 8. Cómo generar la documentación automáticamente

### Opción A: pydoc (stdlib, sin instalación)

```bash
# Activar entorno virtual
.venv\Scripts\activate

# Generar HTMLs (ejecutar desde la raíz del proyecto)
python -m pydoc -w authentication.backends authentication.middleware authentication.decorators authentication.views
python -m pydoc -w usuarios.models usuarios.views usuarios.services.keycloak_service usuarios.services.email_service
python -m pydoc -w clientes.models clientes.views
python -m pydoc -w agregar_usuario.models agregar_usuario.views

# Mover a docs/html/
mkdir docs\html
move *.html docs\html\

# O visualizar en el navegador en tiempo real:
python -m pydoc -p 9999
```

### Opción B: pdoc (interfaz moderna)

```bash
pip install pdoc
pdoc --output-dir docs/html authentication usuarios clientes agregar_usuario
```

### Opción C: Sphinx (para proyectos grandes)

```bash
pip install sphinx sphinx-rtd-theme
sphinx-quickstart docs/sphinx
# Configurar conf.py con autodoc, luego:
sphinx-build -b html docs/sphinx docs/sphinx/_build
```

> **Convención:** Todo código nuevo debe incluir docstrings PEP 257 para ser capturado automáticamente.
