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
