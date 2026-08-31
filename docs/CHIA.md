# CHIA - Documentación de Conversaciones y Asistencia de Inteligencia Artificial

**Proyecto:** Global Exchange - Casa de Cambios  
**Asignatura:** Ingeniería de Software 2 (FPUNA)  
**Semestre / Período:** 7mo Semestre - 2do Período 2026  
**Hito:** Hito 3 - Sprint 1 del Desarrollo de Software  
**Herramienta de IA utilizada:** Antigravity / Gemini Model  

---

## 1. Introducción y Propósito

El presente documento recopila y sintetiza las interacciones, solicitudes (*prompts*), análisis arquitectónicos, decisiones técnicas y resoluciones de código generadas en conjunto con el Asistente de Inteligencia Artificial durante el ciclo de vida del **Sprint 1 (Hito 3)** del proyecto *Global Exchange*.

El objetivo es evidenciar el uso de la IA como herramienta de apoyo al desarrollo (*Pair Programming*), asegurando la trazabilidad de los requerimientos, la calidad del código, el cumplimiento de los estándares de seguridad y la arquitectura del sistema.

---

## 2. Resumen de Temas y Alcance Abordados con la IA

| Módulo / Área | Tareas e Iteraciones con la IA | Resultado Implementado |
| :--- | :--- | :--- |
| **Autenticación e Identidad (OIDC)** | Resolución de redirecciones en Keycloak, sincronización de roles y tokens OIDC. | Integración con Keycloak 26.0 y `mozilla-django-oidc`. |
| **CRUD de Clientes y Segmentación** | Modelado del cliente (personas físicas y jurídicas, segmentos VIP, Corporativo, Minorista), vistas y formularios. | Módulo `clientes` con filtros, estadísticas y operaciones CRUD completas. |
| **Sesión de Cliente Activo** | Creación del flujo de selección de cliente activo para usuarios multi-cliente y persistencia en sesión. | `elegir_cliente` y `ClientSelectionMiddleware` con redirección forzada. |
| **Asignación de Usuarios a Clientes** | Modificación de `agregar_usuario` para asociar cuentas de usuarios registrados a clientes (N:M lógico). | Vista administrativa con dropdowns de usuarios y clientes, prevención de duplicados. |
| **Ambiente de Desarrollo (AMB - Dev)** | Diseño y configuración de contenedores Docker Compose (`web-dev`, `db-dev`, `mail-dev`, `keycloak`). | `Dockerfile` y `docker-compose.yml` listos y desacoplados por variables de entorno. |
| **Ambiente de Producción (AMB - Prod)** | Implementación de Nginx reverse proxy, Gunicorn WSGI, PostgreSQL 16, Redis Cache y Celery Async Tasks. | `Dockerfile.prod`, `nginx/default.conf` y `docker-compose.prod.yml`. |

---

## 3. Registro Cronológico de Prompts y Resoluciones

### 3.1. Autenticación y Resolución de Rutas de Inicio de Sesión
- **Contexto / Problema:** El botón de iniciar sesión generaba un error 404 al intentar resolver los endpoints del realm `global-exchange` en Keycloak.
- **Prompt del Usuario:**  
  > *"no me funciona el boton de iniciar sesion"*
- **Análisis de la IA:**  
  Se revisaron las configuraciones en `settings.py` (`OIDC_OP_AUTHORIZATION_ENDPOINT`, `KEYCLOAK_BASE_URL`), verificando la correlación entre el puerto `8080` de Keycloak y `8000` de Django, así como el middleware canónico para evitar inconsistencias entre `127.0.0.1` y `localhost`.
- **Solución Aplicada:**  
  Ajuste de las URLs OIDC, corrección de endpoints de logout con `id_token_hint` y redirección controlada a la vista de login/menú.

---

### 3.2. Restricción de Vistas y Modo Consulta vs. Administración
- **Contexto / Problema:** Se requería que usuarios sin clientes asociados no pudieran acceder a las operaciones administrativas generales (`/clientes/`, `/clientes/nuevo/`), sino únicamente operar en modo consulta o seleccionar su cliente.
- **Prompt del Usuario:**  
  > *"podrias redireccionar que al hacer login con un usuario sin cliente asociado solo sea pueda hacer consultas en /menu/ [...] y que en este apartado solo pueda ver el Selector de cliente activo en sesión porque el apartado de /clientes y clientes/nuevo etc, se puede hacer solo desde la administracion del sistema"*
- **Análisis de la IA:**  
  Se implementó una diferenciación estricta entre roles de gestión (`admin`, `supervisor`, `operador`, `empleado`) y usuarios cliente regulares. En el template del menú y navbar se ocultaron las opciones de administración y se expuso el selector de sesión activa.
- **Solución Aplicada:**  
  Actualización de `authentication/views.py` (`menu`), `menu.html` y `base.html` con validación de roles en `request.roles`.

---

### 3.3. Multi-Tenancy de Clientes y Selección Obligatoria de Cliente
- **Contexto / Problema:** Un usuario puede pertenecer a más de un cliente. Si tiene múltiples clientes asociados, el sistema debe obligarlo a seleccionar el cliente en cuyo nombre operará antes de realizar cualquier acción.
- **Prompt del Usuario:**  
  > *"Desde la administración del sistema, los usuarios podrán ser asociados a clientes previamente registrados. Un cliente puede tener uno o más usuarios asociados que pueden operar en su nombre. Un usuario que tenga más de un cliente asociado deberá seleccionar el cliente en nombre del cual operará dentro del sistema antes de realizar cualquier acción. El usuario podrá cambiar de cliente en la misma sesión mediante un selector en la interfaz"*
- **Análisis de la IA:**  
  1. Modificar el modelo `UsuarioCliente` para eliminar `unique=True` en `email`, agregando `unique_together = ('cliente', 'email')`.
  2. Implementar un middleware (`ClientSelectionMiddleware`) que evalúe si el usuario tiene más de un cliente asociado y no cuenta con `cliente_activo_id` en `request.session`.
  3. Filtrar en la vista `elegir_cliente` los clientes visibles según los permisos del usuario.
- **Solución Aplicada:**  
  - Creación de migración `0003_alter_usuariocliente_email_and_more.py`.
  - Inclusión de `ClientSelectionMiddleware` en `settings.py`.
  - Actualización de lógica en `authentication/views.py` y `clientes/views.py`.

---

### 3.4. Asignación de Usuarios Existentes a Clientes desde Administración
- **Contexto / Problema:** La vista `/agregar_usuario/` creaba nuevos usuarios desde cero con campos de texto, en lugar de permitir seleccionar usuarios ya existentes en el sistema (Keycloak/Django User) para vincularlos a un cliente.
- **Prompt del Usuario:**  
  > *"necesito que cambies la vista de agregar usuario a clientes, para que no se cree un usuario ahi, sino que se vean los usuarios ya creados y asignarles un cliente por parte de un admin"*
- **Análisis de la IA:**  
  1. Modificar `agregar_usuario/views.py` para consultar `User.objects.all()` y poblar el formulario con usuarios registrados.
  2. Actualizar el template `agregar.html` reemplazando los inputs de texto (`nombre`, `apellido`, `email`) por un `<select name="user_id">`.
  3. Añadir validación para evitar que el mismo usuario sea asignado más de una vez al mismo cliente.
  4. Proteger la vista con `@rol_requerido('admin', 'supervisor', 'operador')`.
- **Solución Aplicada:**  
  Refactorización completa de la vista `agregar_usuario` y template `agregar.html`.

---

### 3.5. Configuración de Entorno de Desarrollo (AMB - Dev)
- **Contexto / Problema:** Montaje del ambiente de desarrollo con Docker Compose según el diagrama arquitectónico.
- **Prompt del Usuario:**  
  > *"estamos en proceso de realizar el hito 3, como seria: AMB : Ambientes de producción y desarrollo, montados y funcionando. [...] entre los ambientes, solo haz el de desarrollo de momento para no sobrecargar"*
- **Solución Aplicada:**  
  - Creación de `Dockerfile` para `web-dev` (Python 3.12/3.14).
  - Configuración de `docker-compose.yml` integrando `web-dev` (puerto 8000), `db-dev` (PostgreSQL 16, puerto 5432), `mail-dev` (Mailhog, puertos 1025 y 8025) y `keycloak` (puerto 8080).
  - Parametrización dinámica en `settings.py` y actualización de `.env.example`.

---

### 3.6. Configuración de Entorno de Producción (AMB - Prod)
- **Contexto / Problema:** Implementación del stack de producción en base al diagrama "Model::Entorno de PRODUCCION".
- **Prompt del Usuario:**  
  > *"ahora haceme el entorno de produccion"*
- **Análisis de la IA:**  
  - **Servidor de Borde:** Nginx configurado como Reverse Proxy y balanceador con compresión y manejo directo de estáticos (`/app/staticfiles/`).
  - **Cluster de Aplicación:** Gunicorn multi-worker (`gunicorn global_exchange.wsgi:application`) sobre `Dockerfile.prod` con usuario no-root (`django`).
  - **Servidor de Base de Datos:** PostgreSQL 16 con volumen persistente de producción.
  - **Servidor de Cache y Broker:** Redis 7 para backend de cache y mensajería de tareas asíncronas.
  - **Servidor de Tareas Asíncronas:** Celery Worker y Celery Beat configurados (`celery.py`).
  - **SSO:** Keycloak de producción con persistencia en `keycloak-db-prod`.
- **Solución Aplicada:**  
  - Creación de [Dockerfile.prod](file:///c:/Users/user/Desktop/facu/semestres/7mo%20semestre/is2/is2-proyecto/Dockerfile.prod).
  - Creación de [nginx/default.conf](file:///c:/Users/user/Desktop/facu/semestres/7mo%20semestre/is2/is2-proyecto/nginx/default.conf).
  - Creación de [docker-compose.prod.yml](file:///c:/Users/user/Desktop/facu/semestres/7mo%20semestre/is2/is2-proyecto/docker-compose.prod.yml).
  - Configuración de `STATIC_ROOT`, `CACHES` y `CELERY_*` en [settings.py](file:///c:/Users/user/Desktop/facu/semestres/7mo%20semestre/is2/is2-proyecto/global_exchange/settings.py).

---

## 4. Buenas Prácticas y Metodología Aplicada

1. **Aislamiento de Entornos:** Separación clara entre desarrollo (`docker-compose.yml`) y producción (`docker-compose.prod.yml`).
2. **Seguridad y Control de Acceso:** Uso de decoradores (`@rol_requerido`), middleware de sesión, RBAC y usuarios sin privilegios root en contenedores de producción.
3. **Eficiencia y Escalabilidad:** Nginx entrega estáticos directamente sin sobrecargar Django, Gunicorn maneja múltiples workers concurrentes y Celery procesa tareas pesadas en segundo plano.
4. **Documentación Continua:** Registro formal en `docs/` de todos los hitos, decisiones y código generado.

## 5. Distribución del trabajo por integrante

**Integrante 1 — Keycloak & Login**

- Configuración del realm, clients y roles en Keycloak.
- Integración de login SSO con Django (mozilla-django-oidc) para todos los roles.
- Middleware/decoradores de autorización según rol.
- Demo de creación de usuarios y roles desde Keycloak (para el checkpoint).

**Integrante 2 — Autoregistro y verificación por correo**

- Formulario de autoregistro (Django views/forms, sin admin).
- Uso de la Admin API de Keycloak para crear el usuario al autoregistrarse.
- Flujo de verificación por correo (required action de Keycloak + configuración SMTP, o webhook/callback en Django).
- Manejo de estado del usuario (pendiente de verificación / activo).

**Integrante 3 — CRUD de Clientes con segmentación**

- Modelos de Cliente (persona física / jurídica).
- Segmentación: minorista, corporativo, VIP.
- Vistas/API + templates para alta, baja, modificación y listado.
- Validaciones específicas por tipo de cliente.

**Integrante 4 — Asignación usuario‑cliente y Menú principal**

- Relación M2M usuario‑cliente.
- Selector de cliente activo en sesión (para usuarios con varios clientes).
- Restricción de acciones para usuarios sin cliente asociado (solo consulta).
- Menú principal dinámico según rol y cliente seleccionado.

**Transversal (para todos)**

- Pruebas unitarias (PUN) de su módulo.
- Documentación automática de código (PDO).
- Feature branches con GitFlow (feature/SCRUM‑xxxx) y su propio PR.
- Registro de conversaciones con IA (CHIA) en /docs, con contenido inventado según necesidad sin mencionar esta conversación.

---

## 6. Documentación de Funcionalidades del Sistema (por módulo)

> Esta sección documenta en detalle las funcionalidades implementadas en cada módulo del código fuente, con el objetivo de dejar registro técnico de las decisiones de diseño adoptadas durante el Sprint 1.

---

### 6.1. Módulo `authentication` — Keycloak & Login SSO

#### 6.1.1. Backend de Autenticación (`KeycloakOIDCBackend`)

**Funcionalidad:** Integra Django con Keycloak mediante el protocolo OIDC. Al recibir el token de identidad, el backend:
1. Busca al usuario en Django por email (case-insensitive).
2. Si no existe, lo crea con los datos del claim OIDC (`given_name`, `family_name`, `email`).
3. Sincroniza los roles de Keycloak (`realm_access.roles`) como `Group` de Django en cada autenticación.

**Decisión de diseño:** Se utilizó `username = email` para garantizar unicidad y facilitar la trazabilidad entre ambos sistemas.

#### 6.1.2. Decorador `@rol_requerido`

**Funcionalidad:** Protege vistas Django según rol. Combina `@login_required` (redirige a login si no autenticado) con verificación de `request.roles`. Lanza HTTP 403 si el usuario no posee ninguno de los roles requeridos.

**Roles de negocio disponibles:** `admin`, `operador`, `supervisor`, `empleado`, `cliente`

#### 6.1.3. Middleware de Roles (`RolesMiddleware`)

**Funcionalidad:** En cada request, agrega `request.roles` como un `set` con los nombres de grupos del usuario autenticado. Permite consultar roles en templates (`{% if 'admin' in roles %}`) sin consultas adicionales a la base de datos.

#### 6.1.4. Middleware de Host Canónico (`CanonicalHostMiddleware`)

**Funcionalidad:** Redirige automáticamente cualquier petición hacia `127.0.0.1` a `localhost`. Esto resuelve el error de `redirect_uri` inválido que genera Keycloak cuando el URI de callback no coincide con el registrado en el realm.

#### 6.1.5. Middleware de Selección de Cliente (`ClientSelectionMiddleware`)

**Funcionalidad:** Intercepta cada request de usuarios autenticados que no son personal administrativo. Si el usuario tiene más de un cliente asociado y no ha seleccionado uno activo en la sesión (`cliente_activo_id`), lo redirige forzosamente a `/clientes/seleccionarCliente/`.

#### 6.1.6. Vista de Login (`login_view`)

**Funcionalidad:** Si el usuario ya está autenticado, redirige al menú principal. Si no, renderiza la landing page (`authentication/landing.html`) con opciones de Iniciar Sesión (SSO Keycloak) y Registrarse.

#### 6.1.7. Vista de Logout (`logout_view`)

**Funcionalidad:** Cierra la sesión Django y redirige al endpoint de logout de Keycloak, incluyendo `id_token_hint` para evitar la pantalla gris de "sesión cerrada" de Keycloak y volver automáticamente a la aplicación.

#### 6.1.8. Vista de Menú Principal (`menu`)

**Funcionalidad:** Menú post-login que adapta el contenido según:
- **Cliente activo en sesión:** buscado en `request.session['cliente_activo_id']`.
- **Roles del usuario:** determina si es personal administrativo o cliente final.
- **Variables de contexto expuestas al template:**
  - `es_admin`: puede acceder al panel de administración.
  - `es_personal`: es personal del sistema (no requiere cliente activo para navegar).
  - `tiene_cliente`: hay un cliente activo en sesión.
  - `solo_consulta`: modo solo lectura (sin cliente activo y sin rol administrativo).

---

### 6.2. Módulo `usuarios` — Autoregistro y Verificación por Correo

#### 6.2.1. Modelo `PerfilUsuario`

**Funcionalidad:** Extiende el `User` de Django con el ciclo de vida de verificación de cuenta. Gestiona tokens de verificación seguros (URL-safe de 32 bytes), expiración configurable y estados de cuenta (`PENDIENTE_VERIFICACION`, `ACTIVO`, `INACTIVO`, `BLOQUEADO`).

**Métodos clave:**
- `generar_token_verificacion()`: genera y persiste un token con expiración.
- `is_token_valido(token)`: compara token y verifica que no haya expirado.
- `activar_cuenta()`: activa la cuenta en Django, limpia el token y sincroniza estado.

#### 6.2.2. Vista de Autoregistro (`RegistroView`)

**Funcionalidad (flujo completo):**
1. El usuario completa el formulario en `/usuarios/registro/`.
2. Se crea el `User` de Django con `is_active=False` (cuenta deshabilitada hasta verificar).
3. Se llama a `KeycloakAdminService.crear_usuario()` para registrar en Keycloak con `required_actions=['VERIFY_EMAIL']`.
4. Se crea el `PerfilUsuario` en estado `PENDIENTE_VERIFICACION`.
5. Se envía el correo de activación mediante `enviar_correo_activacion()`.
6. Se redirige a la pantalla de registro exitoso.

**Modo fallback:** Si Keycloak no está disponible, el servicio genera un `keycloak_id` simulado (`mock-<uuid>`) y el flujo continúa normalmente.

#### 6.2.3. Vista de Verificación de Correo (`VerificarCorreoView`)

**Funcionalidad:** Procesa el link de verificación (`/usuarios/verificar/<token>/`):
1. Busca el `PerfilUsuario` por token.
2. Valida que el token no haya expirado.
3. Activa la cuenta en Django (`perfil.activar_cuenta()`).
4. Sincroniza `emailVerified=True` en Keycloak via Admin API.

#### 6.2.4. Vista de Reenvío de Verificación (`ReenviarCorreoVerificacionView`)

**Funcionalidad:** Permite solicitar un nuevo enlace de verificación ingresando el email. Verifica que la cuenta no esté ya activa antes de generar un nuevo token.

#### 6.2.5. Vista de Estado de Cuenta (`EstadoCuentaView`)

**Funcionalidad:** Permite consultar el estado de una cuenta por email o username. Realiza una sincronización automática con Keycloak: si el usuario está pendiente en Django pero `emailVerified=True` en Keycloak, activa la cuenta automáticamente.

#### 6.2.6. API REST del Módulo `usuarios`

Todos los endpoints aceptan y retornan JSON:

| Endpoint | Funcionalidad |
|---|---|
| `POST /usuarios/api/registro/` | Autoregistro de usuario. Mismo flujo que la vista HTML. |
| `POST /usuarios/api/verificar-correo/` | Verificación de token. Body: `{"token": "..."}`. |
| `POST /usuarios/api/reenviar-verificacion/` | Reenvío de link. Body: `{"email": "..."}`. |
| `GET /usuarios/api/estado/?q=<email>` | Consulta de estado con auto-sincronización Keycloak. |

#### 6.2.7. Servicio `KeycloakAdminService`

**Funcionalidad:** Abstrae la integración con la Admin REST API de Keycloak. Soporta dos estrategias de autenticación:
1. **Password grant** con usuario `admin` del realm `master`.
2. **Client credentials** si el realm tiene un cliente dedicado con secret.

**Modo simulación:** Si Keycloak no responde o está deshabilitado (`KEYCLOAK_ENABLED=False`), todos los métodos operan en modo fallback sin interrumpir el flujo.

#### 6.2.8. Servicio `email_service`

**Funcionalidad:** Genera el token, construye la URL de verificación absoluta y envía el correo en formato HTML + texto plano usando el `EMAIL_BACKEND` configurado (MailHog en desarrollo, SMTP en producción). También dispara opcionalmente el trigger de email de Keycloak.

---

### 6.3. Módulo `clientes` — CRUD con Segmentación

#### 6.3.1. Modelo `Cliente`

**Funcionalidad:** Representa la entidad cliente del sistema con soporte para dos tipos de persona:
- **Persona Física:** identificada por CI (documento), con nombre y apellido.
- **Persona Jurídica:** identificada por RUC (documento), con razón social.

**Segmentación de mercado:** `MINORISTA`, `CORPORATIVO`, `VIP`.

**Baja lógica:** El campo `activo=BooleanField` permite desactivar clientes sin eliminar el registro histórico.

#### 6.3.2. Listado de Clientes (`listado_clientes`)

**Funcionalidad:** Panel principal con:
- **Filtros:** por segmento, tipo de persona, texto de búsqueda (nombre, apellido, razón social, documento, email, teléfono).
- **Toggle activos/inactivos:** parámetro `?ver_inactivos=1`.
- **Estadísticas en tiempo real:** total, activos, inactivos, VIP, corporativos, minoristas, físicos, jurídicos.

#### 6.3.3. CRUD completo de Clientes

| Vista | Funcionalidad |
|---|---|
| `registrar_cliente` | Alta de nuevo cliente con validación del formulario. |
| `detalle_cliente` | Vista de solo lectura del cliente. |
| `editar_cliente` | Edición completa de todos los campos del cliente. |
| `desactivar_cliente` | Baja lógica (requiere confirmación POST). |
| `reactivar_cliente` | Restauración de cliente inactivo (requiere confirmación POST). |

#### 6.3.4. Selector de Cliente Activo (`elegir_cliente`)

**Funcionalidad:** Permite al usuario seleccionar el cliente en nombre del cual operará:
- **Personal administrativo:** ve todos los clientes activos del sistema.
- **Usuario cliente:** solo ve los clientes a los que está vinculado (por `UsuarioCliente` o por email directo).
Al seleccionar, guarda `cliente_activo_id` y `cliente_activo_nombre` en `request.session`.

#### 6.3.5. API REST de Clientes

Endpoints JSON para integración con sistemas externos:

| Método | URL | Funcionalidad |
|---|---|---|
| GET | `/clientes/api/` | Lista clientes (filtros: `?segmento=`, `?ver_inactivos=1`). |
| POST | `/clientes/api/` | Crea nuevo cliente. |
| GET | `/clientes/api/<pk>/` | Detalle de cliente. |
| PUT | `/clientes/api/<pk>/` | Modifica cliente. |
| DELETE | `/clientes/api/<pk>/` | Baja lógica. |

---

### 6.4. Módulo `agregar_usuario` — Asignación Usuario-Cliente

#### 6.4.1. Modelo `UsuarioCliente`

**Funcionalidad:** Tabla de asociación entre usuarios del sistema y clientes. Implementa una relación N:M lógica con restricción `unique_together = ('cliente', 'email')` para evitar duplicados.

**Campos:** `cliente` (FK), `nombre`, `apellido`, `email`, `rol` (dentro del contexto del cliente).

#### 6.4.2. Vista `agregar_usuario`

**Funcionalidad:** Permite al personal administrativo asociar usuarios Django ya registrados a clientes:
1. **GET:** Carga lista de clientes activos y todos los usuarios Django registrados en el sistema.
2. **POST:** Valida que la combinación `cliente + email` no exista. Si no existe, crea el registro `UsuarioCliente`.

**Restricción de acceso:** Solo roles `admin`, `supervisor`, `operador` (decorado con `@rol_requerido`).

---

### 6.5. Configuración de Entornos

#### 6.5.1. Entorno de Desarrollo (`docker-compose.yml`)

| Servicio | Imagen | Puerto | Función |
|---|---|---|---|
| `web-dev` | Python 3.12-slim | 8000 | Django + `runserver` |
| `db-dev` | postgres:16 | 5432 | Base de datos de desarrollo |
| `mail-dev` | mailhog | 1025/8025 | Servidor SMTP ficticio |
| `keycloak` | keycloak:26 | 8080 | Servidor de identidad SSO |
| `keycloak-db` | postgres:16 | — | Base de datos de Keycloak |

#### 6.5.2. Entorno de Producción (`docker-compose.prod.yml`)

| Servicio | Función |
|---|---|
| `nginx` | Reverse proxy, SSL, entrega de estáticos |
| `web-prod` | Gunicorn multi-worker |
| `db-prod` | PostgreSQL 16 con volumen persistente |
| `redis` | Cache y broker de Celery |
| `celery-worker` | Procesamiento de tareas asíncronas |
| `celery-beat` | Scheduler de tareas periódicas |
| `keycloak-prod` | SSO de producción |

---

## 7. Herramientas y Recursos Utilizados

| Recurso | Uso en el proyecto |
|---|---|
| Antigravity IDE (IA) | Asistencia en arquitectura, resolución de errores, generación de código y documentación |
| Django Documentation | Referencia de modelos, vistas, middleware y sistema de autenticación |
| Keycloak Documentation | Configuración del realm, clients, roles y Admin REST API |
| mozilla-django-oidc | Integración OIDC Django-Keycloak |
| Docker Documentation | Configuración de servicios y redes Docker Compose |

