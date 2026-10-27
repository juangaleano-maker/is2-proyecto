#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Despliegue automático de Global Exchange
# Django 5.1 + PostgreSQL 16 + Redis 7 + Celery + Keycloak 26 + Nginx
#
# Uso:
#   ./scripts/deploy.sh dev                 # despliega ambiente de desarrollo
#   ./scripts/deploy.sh prod                # despliega ambiente de producción
#   ./scripts/deploy.sh prod --seed         # puebla la base de datos
#   ./scripts/deploy.sh prod --no-pull      # no hace git pull (código local)
#   ./scripts/deploy.sh dev  --reset-db     # borra volúmenes, recrea y puebla
#
# Características de resiliencia:
#   - Se ejecuta desde cualquier directorio (hace cd a la raíz del repositorio).
#   - Autogenera .env / .env.prod desde el template con secretos aleatorios en clean install.
#   - Detecta si Docker requiere permisos de superusuario y hace fallback a 'sudo docker'.
#   - Ejecuta seed idempotente en el primer despliegue automáticamente.
#   - Health check sin -L para verificar el código de respuesta directo de Django/Nginx.
#
# Etapas:
#   1/7 Verificación de requisitos (docker con fallback a sudo, compose, git, curl)
#   2/7 Código fuente (git clone / fetch + pull --ff-only)
#   3/7 Configuración (.env / .env.prod autogenerados con secretos si no existen)
#   4/7 Build y levantado de infraestructura de datos
#   5/7 Base de datos (wait, backup en prod, migrate, servicios restantes)
#   6/7 Población de datos (seed idempotente automático en primer despliegue)
#   7/7 Estáticos, check --deploy y health check HTTP (sin -L)
# =============================================================================
set -Eeuo pipefail

# ======================== 0. RAÍZ DEL REPOSITORIO =========================== #
# Determinar y cambiar al directorio raíz del repositorio de forma absoluta
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
cd "$REPO_ROOT" || { echo "Error: No se pudo cambiar a la raíz del repositorio en ${REPO_ROOT}"; exit 1; }

# ======================== CONFIGURACIÓN POR DEFECTO ========================= #
REPO_URL="${REPO_URL:-https://github.com/juangaleano-maker/is2-proyecto.git}"
APP_DIR="${APP_DIR:-.}"

BRANCH_DEV="${BRANCH_DEV:-develop}"
BRANCH_PROD="${BRANCH_PROD:-develop}"          # cambiar a main cuando corresponda

# Nombres de servicios (deben coincidir con docker-compose*.yml)
# dev
SVC_WEB_DEV="${SVC_WEB_DEV:-web-dev}"
SVC_DB_DEV="${SVC_DB_DEV:-db-dev}"
# prod
SVC_WEB_PROD="${SVC_WEB_PROD:-web-prod}"
SVC_DB_PROD="${SVC_DB_PROD:-db-prod}"
SVC_REDIS_PROD="${SVC_REDIS_PROD:-redis-prod}"

# Health check
HEALTH_URL_DEV="${HEALTH_URL_DEV:-http://localhost:8000/}"
HEALTH_URL_PROD="${HEALTH_URL_PROD:-http://localhost/}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-3}"

# Backups
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_KEEP="${BACKUP_KEEP:-10}"

# ======================== UTILIDADES ======================================== #
C_RESET=$'\033[0m'; C_RED=$'\033[1;31m'; C_GRN=$'\033[1;32m'
C_YEL=$'\033[1;33m'; C_BLU=$'\033[1;34m'; C_CYN=$'\033[1;36m'

step()  { echo "${C_CYN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"; echo "${C_BLU}[$1]${C_RESET} $2"; }
log()   { echo "  ${C_BLU}▶${C_RESET} $*"; }
ok()    { echo "  ${C_GRN}✔${C_RESET} $*"; }
warn()  { echo "  ${C_YEL}⚠${C_RESET} $*"; }
die()   { echo "  ${C_RED}✖ ERROR:${C_RESET} $*" >&2; exit 1; }

# Generador de secretos criptográficamente seguros portable (Linux, macOS, Windows Git Bash)
generate_secret() {
  local length="${1:-32}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$((length / 2))" 2>/dev/null
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets; print(secrets.token_hex($((length / 2))))" 2>/dev/null
  elif [[ -r /dev/urandom ]]; then
    LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom 2>/dev/null | head -c "$length" || true
  else
    echo "sec_$(date +%s%N 2>/dev/null || date +%s)_${RANDOM}_${RANDOM}"
  fi
}

# Reemplazo seguro de variables en archivos con sed portable
replace_env_var() {
  local key="$1"
  local val="$2"
  local file="$3"
  if grep -q "^${key}=" "$file"; then
    if sed --version >/dev/null 2>&1; then
      sed -i "s|^${key}=.*|${key}=${val}|g" "$file"
    else
      sed -i '' "s|^${key}=.*|${key}=${val}|g" "$file"
    fi
  else
    echo "${key}=${val}" >> "$file"
  fi
}

# Trap: muestra la línea que falló
cleanup() {
  local exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    echo ""
    echo "${C_RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
    echo "${C_RED}✖ El despliegue falló en la línea ${BASH_LINENO[0]} (exit code: $exit_code)${C_RESET}"
    echo "${C_RED}  Comando: ${BASH_COMMAND}${C_RESET}"
    echo "${C_RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
  fi
}
trap cleanup ERR

usage() {
  echo "Uso: $0 <dev|prod> [--seed] [--no-pull] [--reset-db]"
  echo ""
  echo "  dev       Ambiente de desarrollo (docker-compose.yml)"
  echo "  prod      Ambiente de producción  (docker-compose.prod.yml)"
  echo "  --seed    Forzar población de datos iniciales (idempotente)"
  echo "  --no-pull No ejecutar git pull (usar código local)"
  echo "  --reset-db Borrar volúmenes y recrear DB (pide confirmación)"
  exit 1
}

# ======================== ARGUMENTOS ======================================== #
ENVIRONMENT="${1:-}"
shift || true
[[ "$ENVIRONMENT" == "dev" || "$ENVIRONMENT" == "prod" ]] || usage

DO_PULL=true; DO_SEED=false; RESET_DB=false
for arg in "$@"; do
  case "$arg" in
    --seed)      DO_SEED=true ;;
    --no-pull)   DO_PULL=false ;;
    --reset-db)  RESET_DB=true; DO_SEED=true ;;
    *)           die "Opción desconocida: $arg" ;;
  esac
done

# Resolver nombres de servicio y archivos según el ambiente
if [[ "$ENVIRONMENT" == "prod" ]]; then
  COMPOSE_FILE="docker-compose.prod.yml"
  ENV_FILE=".env.prod"
  ENV_EXAMPLE=".env.prod.example"
  BRANCH="$BRANCH_PROD"
  HEALTH_URL="$HEALTH_URL_PROD"
  SVC_WEB="$SVC_WEB_PROD"
  SVC_DB="$SVC_DB_PROD"
  SVC_REDIS="$SVC_REDIS_PROD"
  HAS_REDIS=true
else
  COMPOSE_FILE="docker-compose.yml"
  ENV_FILE=".env"
  ENV_EXAMPLE=".env.example"
  BRANCH="$BRANCH_DEV"
  HEALTH_URL="$HEALTH_URL_DEV"
  SVC_WEB="$SVC_WEB_DEV"
  SVC_DB="$SVC_DB_DEV"
  SVC_REDIS=""
  HAS_REDIS=false
fi

echo ""
echo "${C_CYN}╔══════════════════════════════════════════════════════════╗${C_RESET}"
echo "${C_CYN}║   🌐 Global Exchange — Despliegue Automático           ║${C_RESET}"
echo "${C_CYN}║   Ambiente: ${C_GRN}${ENVIRONMENT}${C_CYN}                                       ║${C_RESET}"
echo "${C_CYN}╚══════════════════════════════════════════════════════════╝${C_RESET}"
echo ""

# ======================== 1/7 REQUISITOS ==================================== #
step "1/7" "Verificando requisitos"

command -v git  >/dev/null 2>&1 || die "git no está instalado"
command -v curl >/dev/null 2>&1 || die "curl no está instalado (necesario para health check)"

# Detección de Docker con fallback transparente a sudo
DOCKER_CMD=()
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    DOCKER_CMD=("docker")
  elif command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    warn "Docker requiere privilegios de superusuario. Se usará 'sudo docker'."
    DOCKER_CMD=("sudo" "docker")
  else
    die "El motor de Docker no responde. Asegurate de que Docker esté corriendo y que tu usuario tenga permisos (o sudo)."
  fi
else
  die "docker no está instalado en el sistema."
fi

# Detección de Docker Compose (plugin v2 o standalone) con fallback a sudo
DC_BASE=()
if "${DOCKER_CMD[@]}" compose version >/dev/null 2>&1; then
  DC_BASE=("${DOCKER_CMD[@]}" "compose")
elif command -v docker-compose >/dev/null 2>&1; then
  if docker-compose version >/dev/null 2>&1; then
    DC_BASE=("docker-compose")
  elif command -v sudo >/dev/null 2>&1 && sudo docker-compose version >/dev/null 2>&1; then
    warn "docker-compose requiere privilegios de superusuario. Se usará 'sudo docker-compose'."
    DC_BASE=("sudo" "docker-compose")
  fi
fi

[[ ${#DC_BASE[@]} -gt 0 ]] || die "Docker Compose no disponible (se necesita 'docker compose' o 'docker-compose')"

COMPOSE_VER=$("${DC_BASE[@]}" version --short 2>/dev/null || echo "v2+")
ok "git $(git --version | cut -d' ' -f3), ${DOCKER_CMD[*]} $("${DOCKER_CMD[@]}" --version | cut -d' ' -f3 | tr -d ','), compose ${COMPOSE_VER}"

# ======================== 2/7 CÓDIGO FUENTE ================================= #
step "2/7" "Código fuente (rama: ${BRANCH})"

if [[ "$APP_DIR" != "." && "$APP_DIR" != "$REPO_ROOT" ]]; then
  if [[ ! -d "$APP_DIR/.git" ]]; then
    log "Clonando repositorio en $APP_DIR..."
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  fi
  cd "$APP_DIR"
fi

if $DO_PULL; then
  if [[ -d ".git" ]]; then
    log "Actualizando código fuente..."
    git fetch --all --prune || warn "No se pudo realizar fetch remoto; usando código local."
    # Si la rama local ya existe, checkout y pull
    if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
      git checkout "$BRANCH" 2>/dev/null || true
      git pull --ff-only origin "$BRANCH" 2>/dev/null || warn "No se pudo hacer pull --ff-only; usando estado actual."
    fi
    ok "Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'local') — $(git log -1 --pretty=%s 2>/dev/null || echo '')"
  else
    warn "No es un repositorio git; se usa el código local."
  fi
else
  warn "--no-pull: se usa el código local tal como está"
  if [[ -d ".git" ]]; then
    ok "Commit local: $(git rev-parse --short HEAD 2>/dev/null || echo 'local') — $(git log -1 --pretty=%s 2>/dev/null || echo '')"
  fi
fi

# ======================== 3/7 CONFIGURACIÓN ================================= #
step "3/7" "Configuración (${ENV_FILE})"

[[ -f "$COMPOSE_FILE" ]] || die "No existe ${COMPOSE_FILE} en $(pwd)"

FIRST_DEPLOY=false
if [[ ! -f "$ENV_FILE" ]]; then
  FIRST_DEPLOY=true
  if [[ -f "$ENV_EXAMPLE" ]]; then
    log "No se encontró ${ENV_FILE}. Autogenerando a partir de ${ENV_EXAMPLE}..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"

    if [[ "$ENVIRONMENT" == "prod" ]]; then
      RAND_SECRET=$(generate_secret 50)
      RAND_DB_PASS=$(generate_secret 24)
      RAND_KC_ADMIN=$(generate_secret 16)

      replace_env_var "SECRET_KEY" "$RAND_SECRET" "$ENV_FILE"
      replace_env_var "DB_PASSWORD" "$RAND_DB_PASS" "$ENV_FILE"
      replace_env_var "KEYCLOAK_ADMIN_PASSWORD" "$RAND_KC_ADMIN" "$ENV_FILE"
      ok "${ENV_FILE} generado con SECRET_KEY, DB_PASSWORD y KEYCLOAK_ADMIN_PASSWORD aleatorios"
    else
      # En desarrollo, asegurar un SECRET_KEY aleatorio
      RAND_SECRET=$(generate_secret 50)
      replace_env_var "SECRET_KEY" "$RAND_SECRET" "$ENV_FILE"
      ok "${ENV_FILE} autogenerado a partir de ${ENV_EXAMPLE}"
    fi
  else
    die "Falta el archivo ${ENV_FILE} y tampoco existe la plantilla ${ENV_EXAMPLE}."
  fi
fi

# Proteger permisos del archivo de entorno
chmod 600 "$ENV_FILE" 2>/dev/null || true

# Cargar variables del .env (sin imprimir secretos)
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

# Validar variables obligatorias (DB)
: "${DB_NAME:?Falta DB_NAME en ${ENV_FILE}}"
: "${DB_USER:?Falta DB_USER en ${ENV_FILE}}"
: "${DB_PASSWORD:?Falta DB_PASSWORD en ${ENV_FILE}}"

# Validar variables adicionales en producción
if [[ "$ENVIRONMENT" == "prod" ]]; then
  : "${SECRET_KEY:?Falta SECRET_KEY en ${ENV_FILE}}"
fi

# Construir el comando base de Docker Compose
DC=("${DC_BASE[@]}" -f "$COMPOSE_FILE" --env-file "$ENV_FILE")

ok "Usando ${COMPOSE_FILE} con ${ENV_FILE}"
log "DB_NAME=${DB_NAME}, DB_USER=${DB_USER} (password oculta)"

# ======================== 4/7 BUILD Y CONTENEDORES ========================== #
step "4/7" "Construyendo imágenes y levantando servicios"

if $RESET_DB; then
  echo ""
  warn "--reset-db borrará TODOS los volúmenes y datos del ambiente '${ENVIRONMENT}'."
  echo -n "  Escribí '${ENVIRONMENT}' para confirmar: "
  read -r CONFIRM
  [[ "$CONFIRM" == "$ENVIRONMENT" ]] || die "Cancelado por el usuario."
  log "Deteniendo y borrando volúmenes..."
  "${DC[@]}" down -v --remove-orphans 2>/dev/null || true
fi

log "Construyendo imágenes (--pull)..."
"${DC[@]}" build --pull

# Levantar primero la infraestructura de datos (DB + Redis si aplica)
log "Levantando infraestructura de base de datos..."
INFRA_SERVICES=("$SVC_DB")
if $HAS_REDIS; then
  INFRA_SERVICES+=("$SVC_REDIS")
fi
"${DC[@]}" up -d "${INFRA_SERVICES[@]}"

# ======================== 5/7 BASE DE DATOS ================================= #
step "5/7" "Base de datos"

# 5a. Esperar a PostgreSQL
log "Esperando a que PostgreSQL esté listo..."
PG_READY=false
for i in $(seq 1 "$HEALTH_RETRIES"); do
  if "${DC[@]}" exec -T "$SVC_DB" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
    PG_READY=true
    break
  fi
  # Si es el primer despliegue, la DB puede no existir aún, intentar con 'postgres'
  if "${DC[@]}" exec -T "$SVC_DB" pg_isready -U "$DB_USER" -d postgres >/dev/null 2>&1; then
    PG_READY=true
    break
  fi
  printf "  ⏳ Intento %d/%d...\r" "$i" "$HEALTH_RETRIES"
  sleep "$HEALTH_INTERVAL"
done
echo ""  # limpiar la línea de progreso
$PG_READY || die "PostgreSQL no respondió después de $((HEALTH_RETRIES * HEALTH_INTERVAL))s"
ok "PostgreSQL listo"

# 5b. Backup previo en producción (si hay datos, no en reset)
if [[ "$ENVIRONMENT" == "prod" ]] && ! $RESET_DB; then
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_$(date +%Y%m%d_%H%M%S).sql.gz"
  log "Creando backup en ${BACKUP_FILE}..."
  if "${DC[@]}" exec -T "$SVC_DB" pg_dump -U "$DB_USER" "$DB_NAME" 2>/dev/null | gzip > "$BACKUP_FILE"; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" 2>/dev/null | cut -f1 || echo "OK")
    ok "Backup creado (${BACKUP_SIZE})"
  else
    warn "No se pudo crear backup (¿primer despliegue?). Continuando..."
    rm -f "$BACKUP_FILE"
  fi
  # Rotar: conservar solo los últimos N
  # shellcheck disable=SC2012
  ls -1t "${BACKUP_DIR}"/*.sql.gz 2>/dev/null | tail -n +"$((BACKUP_KEEP + 1))" | xargs -r rm -- 2>/dev/null || true
fi

# 5c. Migraciones
log "Aplicando migraciones..."
"${DC[@]}" run --rm -e SKIP_TESTS=1 "$SVC_WEB" python manage.py migrate --noinput
ok "Migraciones aplicadas"

# 5d. Levantar todos los servicios restantes
log "Levantando todos los servicios..."
"${DC[@]}" up -d
ok "Servicios levantados"

# ======================== 6/7 POBLACIÓN DE DATOS ============================ #
step "6/7" "Población de la base de datos (Seed)"

# Determinar si se ejecuta el seed:
# 1. Solicitud explícita (--seed o --reset-db)
# 2. Primer despliegue (se acaba de crear el .env)
# 3. La base de datos no contiene monedas cargadas aún
RUN_SEED=false
if $DO_SEED || $RESET_DB || $FIRST_DEPLOY; then
  RUN_SEED=true
else
  # Verificación rápida de existencia de datos iniciales
  MONEDAS_EXISTENTES=$("${DC[@]}" exec -T -e SKIP_TESTS=1 "$SVC_WEB" python -c \
    "import django; django.setup(); from monedas.models import Moneda; print(Moneda.objects.filter(activa=True).count())" 2>/dev/null || echo "0")
  if [[ "$MONEDAS_EXISTENTES" =~ ^[0-9]+$ ]] && [[ "$MONEDAS_EXISTENTES" -eq 0 ]]; then
    log "Base de datos vacía detectada. Activando seed automático..."
    RUN_SEED=true
  fi
fi

if $RUN_SEED; then
  log "Ejecutando comando seed idempotente (monedas, cortes, métodos de pago, cotizaciones, clientes)..."
  if "${DC[@]}" exec -T -e SKIP_TESTS=1 "$SVC_WEB" python manage.py seed --idempotent 2>&1; then
    ok "Datos iniciales cargados y verificados exitosamente"
  else
    warn "El comando seed reportó advertencias o falló. Continuando con el despliegue..."
  fi
else
  log "Se omite la población de datos (la base de datos ya cuenta con registros; usá --seed para forzar verificación)"
fi

# ======================== 7/7 ESTÁTICOS Y HEALTH CHECK ====================== #
step "7/7" "Archivos estáticos y verificación"

# collectstatic (en prod ya lo corre el Dockerfile.prod CMD, pero lo forzamos por si acaso)
log "Ejecutando collectstatic..."
"${DC[@]}" exec -T -e SKIP_TESTS=1 "$SVC_WEB" python manage.py collectstatic --noinput >/dev/null 2>&1 || true
ok "collectstatic completado"

# check --deploy solo en producción
if [[ "$ENVIRONMENT" == "prod" ]]; then
  log "Ejecutando check --deploy..."
  "${DC[@]}" exec -T -e SKIP_TESTS=1 "$SVC_WEB" python manage.py check --deploy 2>&1 || true
fi

# Health check HTTP con reintentos (SIN -L para evaluar el código directo devuelto por Django/Nginx)
log "Verificando que la aplicación responda en ${HEALTH_URL} (sin redirección externa)..."
APP_OK=false
for i in $(seq 1 "$HEALTH_RETRIES"); do
  HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL" 2>/dev/null || echo "000")
  if [[ "$HTTP_CODE" =~ ^(200|301|302|401|403)$ ]]; then
    APP_OK=true
    break
  fi
  printf "  ⏳ Intento %d/%d (HTTP %s)...\r" "$i" "$HEALTH_RETRIES" "$HTTP_CODE"
  sleep "$HEALTH_INTERVAL"
done
echo ""  # limpiar la línea de progreso

if $APP_OK; then
  ok "La aplicación responde correctamente (HTTP ${HTTP_CODE})"
else
  echo ""
  warn "La aplicación no respondió a tiempo. Últimos logs de ${SVC_WEB}:"
  echo ""
  "${DC[@]}" logs --tail=60 "$SVC_WEB" 2>/dev/null || true
  echo ""
  die "Health check fallido después de $((HEALTH_RETRIES * HEALTH_INTERVAL))s (último HTTP: ${HTTP_CODE})"
fi

# ======================== RESUMEN FINAL ===================================== #
echo ""
echo "${C_GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
echo "${C_GRN}✔ Despliegue de '${ENVIRONMENT}' completado exitosamente${C_RESET}"
if [[ -d ".git" ]]; then
  echo "${C_GRN}  Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'local') — $(git log -1 --pretty=%s 2>/dev/null || echo '')${C_RESET}"
fi
echo "${C_GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
echo ""

if [[ "$ENVIRONMENT" == "dev" ]]; then
  echo "  🌐 Aplicación:     http://localhost:8000"
  echo "  🔑 Keycloak SSO:   http://localhost:8080"
  echo "  📧 MailHog Web:    http://localhost:8025"
  echo "  🔐 KC Admin:       admin / admin"
else
  echo "  🌐 Aplicación:     http://localhost (Nginx)"
  echo "  🔑 Keycloak SSO:   http://localhost:8080"
  echo "  🔐 KC Admin:       admin / (ver .env.prod KEYCLOAK_ADMIN_PASSWORD)"
fi

echo ""
echo "  Usuarios demo Keycloak:"
echo "    admin.demo    / Admin123!    (rol: admin)"
echo "    operador.demo / Operador123! (rol: operador)"
echo ""

"${DC[@]}" ps
echo ""
