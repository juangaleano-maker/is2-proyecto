# 🚀 Guía del Ambiente de Producción — Global Exchange

Este documento describe la arquitectura, configuración, levantamiento y operación del **Ambiente de Producción** para el sistema **Global Exchange**.

---

## 🏛️ 1. Arquitectura de Producción

El entorno de producción se orquesta mediante **Docker Compose** (`docker-compose.prod.yml`) con 7 servicios desacoplados bajo estándares de alta disponibilidad, seguridad y rendimiento:

```
                      [ CLIENTE / NAVEGADOR ]
                                 │
                   Puerto 80/443 │ (HTTP/HTTPS)
                                 ▼
                     ┌───────────────────────┐
                     │   nginx-prod (Edge)   │
                     └──────────┬────────────┘
         ┌──────────────────────┴──────────────────────┐
         │ (Archivos /static/ y /media/)               │ (Peticiones Dinámicas)
         ▼                                             ▼
┌──────────────────┐                         ┌──────────────────┐
│ static_volume &  │                         │ web-prod (Django │
│  media_volume    │                         │    + Gunicorn)   │
└──────────────────┘                         └────────┬─────────┘
                                                      │
         ┌───────────────────┬────────────────────────┼────────────────────────┐
         │                   │                        │                        │
         ▼                   ▼                        ▼                        ▼
┌──────────────────┐ ┌───────────────┐ ┌───────────────────────┐    ┌───────────────────────┐
│ db-prod (Postgres│ │  redis-prod   │ │ keycloak-prod (SSO)   │    │ celery-worker & beat  │
│  16 Persistente) │ │ (Cache/Broker)│ │ (Puerto 8080)         │    │ (Tareas en Background)│
└──────────────────┘ └───────┬───────┘ └──────────┬────────────┘    └───────────────────────┘
                             │                    │
                             └────────────────────┼────────────────────────────┘
                                                  ▼
                                       ┌───────────────────────┐
                                       │ keycloak-db-prod      │
                                       │ (PostgreSQL 16)       │
                                       └───────────────────────┘
```

### Componentes y Roles:

1. **`nginx-prod` (Servidor de Borde / Reverse Proxy)**:
   - Expuesto en el puerto `80` (HTTP) y `443` (preparado para SSL).
   - Sirve directamente archivos estáticos recolectados (`/static/`) y archivos multimedia (`/media/`) con caché HTTP optimizada (`Cache-Control: max-age`).
   - Enruta todas las peticiones dinámicas al backend Gunicorn (`web-prod:8000`), reenviando las cabeceras `Host`, `X-Real-IP`, `X-Forwarded-For` y `X-Forwarded-Proto`.

2. **`web-prod` (Servidor de Aplicación Django)**:
   - Construido con `Dockerfile.prod` (Python 3.12-slim optimizado, sin herramientas de compilación en la imagen final).
   - Ejecuta **Gunicorn WSGI** con 3 workers concurrentes y timeout de 60s.
   - Corre con un usuario sin privilegios root (`django:1000`).
   - En cada arranque ejecuta automáticamente `collectstatic` y `migrate` asegurando que la base de datos y los recursos estáticos queden actualizados.
   - `DEBUG=False` estricto, con protección CSRF configurada para orígenes de producción.

3. **`db-prod` (Base de Datos Principal)**:
   - PostgreSQL 16 con volumen persistente (`db_prod_data`).
   - Dispone de *Healthcheck* con `pg_isready` para que `web-prod` y los workers no arranquen hasta que la base de datos esté lista y aceptando conexiones.

4. **`redis-prod` (Servidor de Caché y Broker de Mensajes)**:
   - Redis 7 Alpine.
   - Base de datos 0: Broker y backend de resultados de Celery.
   - Base de datos 1: Motor de caché Redis para sesiones/vistas de Django.

5. **`celery-worker` y `celery-beat` (Procesamiento Asíncrono)**:
   - Procesan tareas en background (envío de notificaciones por email, verificación de operaciones cambiarias, etc.).
   - Esperan a que PostgreSQL y Redis estén totalmente operativos mediante `condition: service_healthy`.

6. **`keycloak-prod` y `keycloak-db-prod` (Identidad y SSO)**:
   - Servidor Keycloak 26.0 con base de datos PostgreSQL dedicada (`keycloak-db-prod`).
   - Importa automáticamente el realm `global-exchange` desde `keycloak/realm-export.json`.
   - Incluye clientes OIDC configurados para redirigir tanto al puerto 80 (producción) como 8000 (desarrollo).

---

## ⚙️ 2. Archivos del Entorno de Producción

| Archivo | Propósito |
| :--- | :--- |
| `docker-compose.prod.yml` | Orquestación completa de los 7 contenedores de producción. |
| `Dockerfile.prod` | Imagen multi-etapa/limpia para Gunicorn, Django y Celery. |
| `.dockerignore` | Excluye `.venv`, `.git`, `__pycache__` y archivos temporales para un build ligero y rápido. |
| `.env.prod` | Variables de entorno activas para producción (DB, contraseñas, secretos, Keycloak). |
| `.env.prod.example` | Plantilla de referencia para replicar el entorno en nuevos servidores. |
| `nginx/default.conf` | Configuración de proxy inverso y caché de estáticos. |
| `keycloak/realm-export.json` | Definición de usuarios demo, roles y cliente OpenID Connect. |
| `prod.bat` | Script de comandos rápidos para Windows (CMD / PowerShell). |
| `prod.sh` | Script de comandos rápidos para Linux / WSL / macOS. |

---

## 🏁 3. Cómo Levantar el Ambiente de Producción

### Paso 1: Asegurarse de que Docker esté corriendo
- Abre **Docker Desktop** en tu equipo y verifica que el motor esté iniciado.

### Paso 2: Ejecutar el levantamiento
Tienes dos formas equivalentes:

#### Opción A — Usando los scripts de gestión (Recomendado):
- **En Windows (PowerShell o CMD):**
  ```powershell
  .\prod.bat up
  ```
- **En Linux o WSL:**
  ```bash
  chmod +x prod.sh
  ./prod.sh up
  ```

#### Opción B — Usando Docker Compose directamente:
```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

---

## 🌐 4. Acceso al Sistema

Una vez levantado:

| Servicio | URL | Credenciales por defecto |
| :--- | :--- | :--- |
| **Global Exchange (Web App)** | [http://localhost](http://localhost) | Acceso general / Login OIDC |
| **Keycloak Admin Console** | [http://localhost:8080](http://localhost:8080) | `admin` / `admin_prod_password` |

### Usuarios de Prueba Preconfigurados (Realm `global-exchange`):
- **Administrador:** `admin.demo` / Contraseña: `Admin123!` (Rol: `admin`)
- **Operador:** `operador.demo` / Contraseña: `Operador123!` (Rol: `operador`)

---

## 🛠️ 5. Comandos de Operación y Mantenimiento

Utilizando el script `prod.bat` (o `./prod.sh` en Linux):

| Acción | Comando con Script | Comando Docker equivalente |
| :--- | :--- | :--- |
| **Ver estado de contenedores** | `.\prod.bat status` | `docker compose -f docker-compose.prod.yml ps` |
| **Ver logs en tiempo real** | `.\prod.bat logs` | `docker compose -f docker-compose.prod.yml logs -f` |
| **Ver logs de Django (Gunicorn)** | `.\prod.bat web-logs` | `docker compose -f docker-compose.prod.yml logs -f web-prod` |
| **Ver logs de Keycloak** | `.\prod.bat keycloak-logs` | `docker compose -f docker-compose.prod.yml logs -f keycloak-prod` |
| **Ejecutar migraciones** | `.\prod.bat migrate` | `docker compose -f docker-compose.prod.yml exec web-prod python manage.py migrate` |
| **Crear superusuario Django** | `.\prod.bat createsuperuser`| `docker compose -f docker-compose.prod.yml exec web-prod python manage.py createsuperuser` |
| **Reiniciar servicios** | `.\prod.bat restart` | `docker compose -f docker-compose.prod.yml restart` |
| **Detener producción** | `.\prod.bat down` | `docker compose -f docker-compose.prod.yml down` |

---

## 🔍 6. Funcionamiento Detallado: Paso a Paso

1. **Recepción de tráfico**:
   - Todo request a `http://localhost` entra al contenedor `nginx-prod`.
   - Si la ruta coincide con `/static/...` o `/media/...`, Nginx la despacha directamente desde los volúmenes compartidos (`static_volume` o `media_volume`) sin consumir recursos de Python.
   - El resto de rutas son derivadas a `web-prod:8000` donde Gunicorn recibe la petición y la entrega a Django.

2. **Autenticación con Keycloak**:
   - Cuando el usuario hace clic en "Iniciar Sesión", Django (`mozilla-django-oidc`) genera la URL de autorización hacia `http://localhost:8080/realms/global-exchange/protocol/openid-connect/auth` con `redirect_uri=http://localhost/oidc/callback/`.
   - El navegador navega a Keycloak, el usuario introduce sus credenciales y Keycloak lo redirige a `http://localhost/oidc/callback/?code=...`.
   - Django recibe el código y, de servidor a servidor (red interna Docker), contacta a `http://keycloak-prod:8080` para canjear el token, verificar los roles (`realm_access.roles`) y sincronizar el usuario en la sesión de Django.

3. **Caché y Tareas Asíncronas**:
   - Django utiliza `redis-prod` para almacenar sesiones y tasas de cambio en caché.
   - Procesos que requieren desacoplamiento (como notificaciones masivas o sincronizaciones externas) son delegados a Celery, que los consume de las colas de Redis y los procesa en background sin bloquear la interfaz de usuario.
