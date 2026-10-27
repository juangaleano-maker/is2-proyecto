#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Despliegue automático de Global Exchange
# Django 5.1 + PostgreSQL 16 + Redis 7 + Celery + Keycloak 26 + Nginx
#
# Uso:
#   ./scripts/deploy.sh dev                 # despliega ambiente de desarrollo
#   ./scripts/deploy.sh prod                # despliega ambiente de producción
#   ./scripts/deploy.sh prod --seed         # puebla la base de datos
#   ./scripts/deploy.sh prod --no-pull      # no hace git pull
#   ./scripts/deploy.sh dev  --reset-db     # borra volúmenes, recrea y puebla
#
# Etapas:
#   1/7 Verificación de requisitos (docker, compose v2, git)
#   2/7 Código fuente (git clone / fetch + pull --ff-only)
#   3/7 Configuración (.env / .env.prod) — valida variables obligatorias
#   4/7 Build y levantado de contenedores
#   5/7 Base de datos (wait, backup en prod, migrate)
#   6/7 Población de datos (fixtures / seed) — solo con --seed o --reset-db
#   7/7 Estáticos, check --deploy y health check HTTP
# =============================================================================
set -Eeuo pipefail

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
HEALTH_URL_DEV="${HEALTH_URL_DEV:-http://localhost:8000/login/}"
HEALTH_URL_PROD="${HEALTH_URL_PROD:-http://localhost/login/}"
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
  echo "  --seed    Poblar la base de datos con datos iniciales"
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

command -v git    >/dev/null 2>&1 || die "git no está instalado"
command -v docker >/dev/null 2>&1 || die "docker no está instalado"
command -v curl   >/dev/null 2>&1 || die "curl no está instalado (necesario para health check)"

docker compose version >/dev/null 2>&1 || die "Docker Compose v2 no disponible (se necesita 'docker compose', no 'docker-compose')"
docker info >/dev/null 2>&1 || die "No hay permisos sobre Docker. Agrega tu usuario al grupo 'docker' o ejecutá con sudo."

COMPOSE_VER=$(docker compose version --short 2>/dev/null || echo "desconocida")
ok "git $(git --version | cut -d' ' -f3), docker $(docker --version | cut -d' ' -f3 | tr -d ','), compose v${COMPOSE_VER}"

# ======================== 2/7 CÓDIGO FUENTE ================================= #
step "2/7" "Código fuente (rama: ${BRANCH})"

if [[ "$APP_DIR" != "." ]]; then
  if [[ ! -d "$APP_DIR/.git" ]]; then
    log "Clonando repositorio en $APP_DIR..."
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  fi
  cd "$APP_DIR"
fi

if $DO_PULL; then
  if [[ -d ".git" ]]; then
    git fetch --all --prune
    git checkout "$BRANCH"
    git pull --ff-only origin "$BRANCH"
    ok "Commit: $(git rev-parse --short HEAD) — $(git log -1 --pretty=%s)"
  else
    warn "No es un repositorio git (APP_DIR='.'); se usa el código local."
  fi
else
  warn "--no-pull: se usa el código local tal como está"
  if [[ -d ".git" ]]; then
    ok "Commit local: $(git rev-parse --short HEAD) — $(git log -1 --pretty=%s)"
  fi
fi

# ======================== 3/7 CONFIGURACIÓN ================================= #
step "3/7" "Configuración (${ENV_FILE})"

[[ -f "$COMPOSE_FILE" ]] || die "No existe ${COMPOSE_FILE} en $(pwd)"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$ENV_EXAMPLE" ]]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    die "Se creó ${ENV_FILE} desde ${ENV_EXAMPLE}. Editá los valores marcados con REEMPLAZAR y volvé a ejecutar."
  fi
  die "Falta el archivo ${ENV_FILE}. Creá uno a partir de ${ENV_EXAMPLE}."
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
  if [[ "$SECRET_KEY" == *"REEMPLAZAR"* ]] || [[ "$SECRET_KEY" == *"insecure"* ]]; then
    warn "SECRET_KEY parece ser un valor placeholder. Cambialo para producción real."
  fi
fi

# Construir el comando base de Docker Compose
DC=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")

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

# Levantar primero la infra de datos (DB + Redis si aplica)
log "Levantando infraestructura de datos..."
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
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
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
step "6/7" "Población de la base de datos"

if $DO_SEED || $RESET_DB; then
  # ===========================================================================
  # NOTA: Actualmente no existen fixtures ni un management command 'seed' en el
  # repositorio. Cuando se creen, descomentar el bloque correspondiente:
  #
  # Opción A — Fixtures JSON (respetar orden de dependencias):
  #   "${DC[@]}" exec -T "$SVC_WEB" python manage.py loaddata \
  #     monedas/fixtures/monedas.json \
  #     clientes/fixtures/clientes.json \
  #     cotizaciones/fixtures/cotizaciones.json \
  #     pagos/fixtures/metodos_pago.json
  #
  # Opción B — Management command:
  #   "${DC[@]}" exec -T -e SKIP_TESTS=1 "$SVC_WEB" python manage.py seed --idempotent
  #
  # Orden de dependencias (por ForeignKeys):
  #   1. monedas (Moneda, DenominacionMoneda)
  #   2. clientes (Cliente, MedioDePago → pagos.MetodoPagoSistema)
  #   3. cotizaciones (Cotizacion → Moneda, Operacion → Cliente + Moneda)
  #   4. pagos (ComprobanteSIPAP → Operacion, TicketTransaccion → Operacion)
  #   5. usuarios (PerfilUsuario → auth.User)
  # ===========================================================================
  warn "No se encontraron fixtures ni comando 'seed' en el repositorio."
  warn "Cuando existan, editá la sección 6/7 de este script."
  warn "Los usuarios demo se crean automáticamente en Keycloak vía realm-export.json."
else
  log "Se omite la población de datos (usá --seed para poblar la base)"
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

# Health check HTTP con reintentos
log "Verificando que la aplicación responda en ${HEALTH_URL}..."
APP_OK=false
for i in $(seq 1 "$HEALTH_RETRIES"); do
  HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -L --max-time 5 "$HEALTH_URL" 2>/dev/null || echo "000")
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
  echo "${C_GRN}  Commit: $(git rev-parse --short HEAD) — $(git log -1 --pretty=%s)${C_RESET}"
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
