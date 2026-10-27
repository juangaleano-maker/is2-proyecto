# 🚀 Deploy Script — Global Exchange

Script de despliegue automático **Zero-Touch** para el sistema **Global Exchange** (Django 5.1 + PostgreSQL 16 + Redis 7 + Celery 5.4 + Keycloak 26 + Nginx).

Diseñado para ejecutarse en una máquina limpia **sin ningún paso manual previo**.

---

## ⚡ Comando exacto en máquina limpia

En cualquier servidor o máquina limpia con Git y Docker instalados, basta con ejecutar:

```bash
git clone https://github.com/juangaleano-maker/is2-proyecto.git
cd is2-proyecto
./scripts/deploy.sh dev
```

> **¿Qué hace de forma 100% automática sin intervención?**
> 1. Se ubica en la raíz del repositorio sin importar desde dónde se invoque.
> 2. Detecta si Docker necesita permisos de superusuario y hace fallback a `sudo docker` automáticamente.
> 3. Autogenera el archivo `.env` (o `.env.prod`) desde `.env.example` con secretos aleatorios criptográficamente seguros.
> 4. Construye las imágenes y levanta la base de datos PostgreSQL.
> 5. Aplica todas las migraciones de Django (`migrate`).
> 6. Ejecuta automáticamente el **seed inicial idempotente** (monedas PYG, USD, BRL, EUR, ARS, cortes de billetes, catálogo de métodos de pago, cotizaciones iniciales y clientes demo).
> 7. Ejecuta `collectstatic` y realiza el **health check HTTP directo** (sin `-L`, aceptando la respuesta inmediata de Django).
> 8. Imprime los enlaces de acceso y credenciales de prueba de Keycloak.

---

## 💻 Uso general

El script ya cuenta con permisos de ejecución en Git (`chmod +x` trackeado en el repositorio) y fin de línea LF forzado en `.gitattributes`.

```bash
# Desarrollo (docker-compose.yml)
./scripts/deploy.sh dev

# Producción (docker-compose.prod.yml con Nginx, Redis y Gunicorn)
./scripts/deploy.sh prod

# Opciones adicionales
./scripts/deploy.sh dev --no-pull       # no hace git pull (útil si estás editando localmente)
./scripts/deploy.sh dev --seed          # fuerza verificación y población de datos iniciales
./scripts/deploy.sh dev --reset-db      # borra volúmenes docker, recrea todo y repuebla
```

---

## 📋 Etapas del despliegue

| # | Etapa | Qué hace |
|---|---|---|
| **1/7** | **Requisitos** | Valida `git`, `curl`, `docker` (con fallback transparente a `sudo docker`) y compose v2. |
| **2/7** | **Código fuente** | `git fetch` y `git pull --ff-only` de la rama de trabajo (`develop`). |
| **3/7** | **Configuración** | Si `.env` o `.env.prod` no existen, los autogenera desde `.env.example` o `.env.prod.example` generando `SECRET_KEY`, `DB_PASSWORD` y `KEYCLOAK_ADMIN_PASSWORD` aleatorios con permisos seguros (`600`). |
| **4/7** | **Build e Infra** | `docker compose build --pull` y levantado prioritario del motor de base de datos (`db-dev` o `db-prod`). |
| **5/7** | **Base de datos** | Espera activa a PostgreSQL (`pg_isready`), backup comprimido automático en producción (`.sql.gz`), migraciones Django (`migrate --noinput`) y levantado de todos los servicios. |
| **6/7** | **Población (Seed)** | Ejecuta el comando Django `python manage.py seed --idempotent` de forma automática en el primer despliegue o al detectar base vacía (no duplica registros). |
| **7/7** | **Verificación** | `collectstatic`, `check --deploy` (en prod) y health check HTTP directo (sin flag `-L` para evaluar directamente `200` o redirección `302`). |

---

## ⚙️ Variables de entorno configurables

Todas tienen valores por defecto listos para usar. Podés sobreescribirlas anteponiéndolas al comando:

```bash
# Ejemplo: cambiar la rama a desplegar
BRANCH_PROD=main ./scripts/deploy.sh prod

# Ejemplo: cambiar reintentos o intervalo de health check
HEALTH_RETRIES=40 HEALTH_INTERVAL=5 ./scripts/deploy.sh dev
```

| Variable | Default | Descripción |
|---|---|---|
| `REPO_URL` | `https://github.com/juangaleano-maker/is2-proyecto.git` | URL del repositorio Git |
| `APP_DIR` | `.` (directorio actual) | Directorio donde reside o se clonará la app |
| `BRANCH_DEV` | `develop` | Rama para ambiente de desarrollo |
| `BRANCH_PROD` | `develop` | Rama para ambiente de producción |
| `HEALTH_URL_DEV` | `http://localhost:8000/` | URL para verificar que Django responda en dev |
| `HEALTH_URL_PROD` | `http://localhost/` | URL para verificar que Nginx/Django responda en prod |
| `HEALTH_RETRIES` | `30` | Cantidad de reintentos del health check |
| `HEALTH_INTERVAL` | `3` | Segundos entre cada intento de health check |
| `BACKUP_DIR` | `./backups` | Directorio local donde se guardan los backups de producción |
| `BACKUP_KEEP` | `10` | Cantidad de backups históricos a conservar |

---

## 🔑 Cuentas demo preconfiguradas

Keycloak incluye el realm `global-exchange` con usuarios listos para autenticarse:

| Usuario | Contraseña | Rol | Acceso |
|---|---|---|---|
| `admin.demo` | `Admin123!` | Administrador | Completo a todas las funcionalidades |
| `operador.demo` | `Operador123!` | Operador de Caja | Cajas, cotizaciones, operaciones y pagos |
| `admin` (Keycloak) | `admin` (dev) / *aleatoria* (prod) | Master Admin | Consola Keycloak en `:8080` |
