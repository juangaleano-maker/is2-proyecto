# 🚀 Deploy Script — Global Exchange

Script de despliegue automático para el sistema **Global Exchange** (Django 5.1 + PostgreSQL 16 + Redis 7 + Celery 5.4 + Keycloak 26 + Nginx).

## Requisitos previos

- **Docker** con Docker Compose v2 (`docker compose`)
- **Git**
- **curl** (para health check)
- El motor de Docker debe estar corriendo

## Uso rápido

```bash
# Dar permisos de ejecución (solo la primera vez)
chmod +x scripts/deploy.sh

# Desarrollo
./scripts/deploy.sh dev                 # despliegue normal
./scripts/deploy.sh dev --no-pull       # sin git pull (código local)
./scripts/deploy.sh dev --reset-db      # borra TODO y recrea (pide confirmación)

# Producción
./scripts/deploy.sh prod                # despliegue normal (con backup automático)
./scripts/deploy.sh prod --seed         # además intenta poblar datos iniciales
./scripts/deploy.sh prod --no-pull      # sin git pull
./scripts/deploy.sh prod --reset-db     # PELIGROSO: borra volúmenes y recrea
```

## Etapas del despliegue

| # | Etapa | Qué hace |
|---|---|---|
| 1/7 | Requisitos | Verifica git, docker, compose v2 y permisos |
| 2/7 | Código fuente | `git fetch` + `pull --ff-only` de la rama configurada |
| 3/7 | Configuración | Valida `.env` (dev) o `.env.prod` (prod) con variables obligatorias |
| 4/7 | Build | `docker compose build --pull` + levanta DB/Redis primero |
| 5/7 | Base de datos | Espera PostgreSQL, backup comprimido en prod (últimos 10), migraciones |
| 6/7 | Seed | Carga datos iniciales (cuando existan fixtures/management command) |
| 7/7 | Verificación | `collectstatic`, `check --deploy` (prod), health check HTTP |

## Variables de entorno configurables

Todas tienen valores por defecto razonables. Podés sobreescribirlas:

```bash
# Ejemplo: cambiar rama de producción
BRANCH_PROD=main ./scripts/deploy.sh prod

# Ejemplo: desplegar en otro directorio
APP_DIR=/opt/global-exchange ./scripts/deploy.sh prod
```

| Variable | Default | Descripción |
|---|---|---|
| `REPO_URL` | `https://github.com/juangaleano-maker/is2-proyecto.git` | URL del repositorio |
| `APP_DIR` | `.` (directorio actual) | Directorio de la aplicación |
| `BRANCH_DEV` | `develop` | Rama para dev |
| `BRANCH_PROD` | `develop` | Rama para prod |
| `HEALTH_RETRIES` | `30` | Reintentos del health check |
| `HEALTH_INTERVAL` | `3` | Segundos entre reintentos |
| `BACKUP_DIR` | `./backups` | Directorio de backups (prod) |
| `BACKUP_KEEP` | `10` | Cantidad de backups a conservar |

## Archivos de entorno

- **Dev:** `.env` (copiado de `.env.example` si no existe)
- **Prod:** `.env.prod` (copiado de `.env.prod.example` si no existe)

### Variables obligatorias

| Variable | Ambos ambientes | Solo producción |
|---|---|---|
| `DB_NAME` | ✅ | |
| `DB_USER` | ✅ | |
| `DB_PASSWORD` | ✅ | |
| `SECRET_KEY` | | ✅ |

## Keycloak

La configuración de Keycloak se importa **automáticamente** desde `keycloak/realm-export.json` con `--import-realm`. No requiere configuración manual.

Incluye:
- Realm: `global-exchange`
- Roles: `admin`, `operador`, `supervisor`, `empleado`, `cliente`, `analista_cambiario`
- Client OIDC: `django-app`
- Usuarios demo: `admin.demo` / `Admin123!` (admin), `operador.demo` / `Operador123!` (operador)

## Seed / Datos iniciales

> ⚠️ **Actualmente no existen fixtures ni management command `seed` en el repositorio.**

Cuando se creen, editar la sección `6/7` del script. El orden de carga por dependencias FK es:

1. `monedas` (Moneda, DenominacionMoneda)
2. `clientes` (Cliente, MedioDePago)
3. `cotizaciones` (Cotizacion, Operacion, Caja, etc.)
4. `pagos` (ComprobanteSIPAP, TicketTransaccion)
5. `usuarios` (PerfilUsuario)

## Backups (solo producción)

- Se crean automáticamente antes de cada migración en prod
- Formato: `{DB_NAME}_YYYYMMDD_HHMMSS.sql.gz`
- Se conservan los últimos 10 (configurable con `BACKUP_KEEP`)
- Ubicación: `./backups/` (configurable con `BACKUP_DIR`)
- **No se crean backups con `--reset-db`** (los datos se borran intencionalmente)

## Servicios Docker por ambiente

### Dev (`docker-compose.yml`)
| Servicio | Puerto |
|---|---|
| `web-dev` | 8000 |
| `db-dev` | 5432 |
| `mail-dev` | 1025, 8025 |
| `keycloak` | 8080 |
| `keycloak-db` | — |

### Prod (`docker-compose.prod.yml`)
| Servicio | Puerto |
|---|---|
| `nginx-prod` | 80, 443 |
| `web-prod` | — (interno) |
| `db-prod` | — |
| `redis-prod` | — |
| `celery-worker` | — |
| `celery-beat` | — |
| `keycloak-prod` | 8080 |
| `keycloak-db-prod` | — |
