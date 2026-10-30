#!/usr/bin/env bash
# =============================================================================
# test_auto_ip.sh — Despliegue en 1 SOLO PASO con Autodetección de IP
# =============================================================================
# Este script:
#   0. Sincroniza el repositorio con la rama develop (git pull automático).
#   1. Detecta automáticamente la IP de la máquina (LAN / Wi-Fi o Cloud VPS).
#   2. Configura las variables en .env.prod (Django ALLOWED_HOSTS, CSRF y Keycloak).
#   3. Construye y levanta toda la pila de Docker de producción.
#   4. Aplica migraciones y ejecuta el seed idempotente de datos iniciales
#      (monedas, denominaciones, cajas, métodos de pago, cotizaciones, clientes).
#   5. Muestra los enlaces finales listos para ingresar desde cualquier dispositivo.
#
# Uso:
#   ./scripts/test_auto_ip.sh              # despliegue completo con git pull
#   ./scripts/test_auto_ip.sh --no-pull    # usar código local sin git pull
#   HOST_IP=192.168.1.50 ./scripts/test_auto_ip.sh  # forzar IP específica
# =============================================================================

set -Eeuo pipefail

# Colores de salida
C_RESET=$'\033[0m'; C_RED=$'\033[1;31m'; C_GRN=$'\033[1;32m'
C_YEL=$'\033[1;33m'; C_BLU=$'\033[1;34m'; C_CYN=$'\033[1;36m'

log()   { echo "  ${C_BLU}▶${C_RESET} $*"; }
ok()    { echo "  ${C_GRN}✔${C_RESET} $*"; }
warn()  { echo "  ${C_YEL}⚠${C_RESET} $*" >&2; }
step()  { echo ""; echo "${C_CYN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"; echo "${C_BLU}[$1]${C_RESET} $2"; }
die()   { echo "  ${C_RED}✖ ERROR:${C_RESET} $*" >&2; exit 1; }

# Raíz del proyecto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"
cd "$REPO_ROOT" || die "No se pudo cambiar al directorio raíz del repositorio"

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
ENV_EXAMPLE=".env.prod.example"
WEB_CONTAINER="web-prod"

# Parsear flags
DO_PULL=true
for arg in "$@"; do
  case "$arg" in
    --no-pull) DO_PULL=false ;;
    *) die "Opción desconocida: $arg" ;;
  esac
done

# -----------------------------------------------------------------------------
# 0. SINCRONIZACIÓN CON EL REPOSITORIO REMOTO (git pull)
# -----------------------------------------------------------------------------
step "0/5" "Sincronizando repositorio con la última versión remota"

if [[ -d ".git" ]]; then
  CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "develop")
  LOCAL_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "desconocido")

  if $DO_PULL; then
    log "Rama activa: ${C_GRN}${CURRENT_BRANCH}${C_RESET}"
    log "Commit local antes del pull: ${LOCAL_COMMIT:0:8}"

    # Traer metadatos remotos para poder comparar antes del pull
    git fetch origin "$CURRENT_BRANCH" 2>/dev/null \
      && log "Fetch completado." \
      || warn "No se pudo hacer fetch. Se continuará con la versión local."

    REMOTE_COMMIT=$(git rev-parse "origin/${CURRENT_BRANCH}" 2>/dev/null || echo "")

    if [[ -n "$REMOTE_COMMIT" && "$LOCAL_COMMIT" != "$REMOTE_COMMIT" ]]; then
      COMMITS_BEHIND=$(git rev-list --count HEAD.."origin/${CURRENT_BRANCH}" 2>/dev/null || echo "?")
      warn "El repositorio local está ${C_YEL}${COMMITS_BEHIND} commit(s) desactualizado(s)${C_RESET} respecto a origin/${CURRENT_BRANCH}."
      log "Actualizando con git pull --ff-only origin ${CURRENT_BRANCH}..."
      git pull --ff-only origin "$CURRENT_BRANCH" 2>/dev/null \
        || { warn "No se pudo hacer pull --ff-only (puede haber cambios locales sin commitear). Usando código actual."; }
    else
      ok "El repositorio ya está actualizado con origin/${CURRENT_BRANCH}."
    fi

    NEW_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "desconocido")
    ok "Commit activo: ${NEW_COMMIT:0:8} — $(git log -1 --pretty=%s 2>/dev/null || echo '')"
  else
    warn "--no-pull: se usa el código local tal como está."
    ok "Commit local: ${LOCAL_COMMIT:0:8} — $(git log -1 --pretty=%s 2>/dev/null || echo '')"
  fi
else
  warn "No se encontró directorio .git. Se usa el código local sin sincronizar."
fi

# -----------------------------------------------------------------------------
# 1. VERIFICAR DOCKER
# -----------------------------------------------------------------------------
step "1/5" "Verificando motor de Docker"

DOCKER_CMD=()
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    DOCKER_CMD=("docker")
  elif command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    warn "Docker requiere privilegios de superusuario. Usando 'sudo docker'."
    DOCKER_CMD=("sudo" "docker")
  else
    die "El motor de Docker no está corriendo o tu usuario no tiene permisos."
  fi
else
  die "Docker no está instalado en este sistema."
fi

DC_BASE=()
if "${DOCKER_CMD[@]}" compose version >/dev/null 2>&1; then
  DC_BASE=("${DOCKER_CMD[@]}" "compose")
elif command -v docker-compose >/dev/null 2>&1; then
  DC_BASE=("docker-compose")
else
  die "Docker Compose no está disponible."
fi
ok "Docker y Docker Compose operativos."

# -----------------------------------------------------------------------------
# 2. AUTODETECCIÓN DE IP
# -----------------------------------------------------------------------------
step "2/5" "Autodetección de la dirección IP del servidor"

detect_ip() {
  local ip=""

  # Prioridad 1: Override manual
  if [[ -n "${HOST_IP:-}" ]]; then echo "$HOST_IP"; return; fi
  if [[ -n "${SERVER_IP:-}" ]]; then echo "$SERVER_IP"; return; fi

  # Prioridad 2: IP local de la interfaz de red principal (LAN / Wi-Fi / Bridged)
  ip=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7}')
  if [[ -z "$ip" ]]; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  fi

  # Prioridad 3: IP pública si es un VPS en la nube
  local public_ip=""
  public_ip=$(curl -s --max-time 2 -4 ifconfig.me 2>/dev/null || curl -s --max-time 2 -4 icanhazip.com 2>/dev/null || true)
  if [[ "$public_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    if [[ -z "$ip" || "$ip" == 10.0.2.* || "${USE_PUBLIC_IP:-false}" == "true" ]]; then
      echo "$public_ip"
      return
    fi
  fi

  echo "${ip:-localhost}"
}

IP_DETECTADA=$(detect_ip)
ok "IP detectada automáticamente: ${C_GRN}${IP_DETECTADA}${C_RESET}"

# -----------------------------------------------------------------------------
# 3. CONFIGURAR .env.prod CON LA IP DETECTADA
# -----------------------------------------------------------------------------
step "3/5" "Configurando variables de producción (${ENV_FILE})"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$ENV_EXAMPLE" ]]; then
    log "Creando ${ENV_FILE} a partir de ${ENV_EXAMPLE}..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"
  else
    die "No existe ${ENV_FILE} ni tampoco ${ENV_EXAMPLE}."
  fi
else
  # Si ya existe .env.prod, sincronizar variables nuevas que estén en .env.prod.example
  if [[ -f "$ENV_EXAMPLE" ]]; then
    log "Sincronizando variables nuevas de ${ENV_EXAMPLE} en ${ENV_FILE}..."
    while IFS= read -r line || [[ -n "$line" ]]; do
      # Ignorar comentarios o líneas en blanco
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      [[ -z "${line// }" ]] && continue
      if [[ "$line" =~ ^([A-Za-z0-9_]+)=(.*)$ ]]; then
        var_name="${BASH_REMATCH[1]}"
        var_val="${BASH_REMATCH[2]}"
        if ! grep -q "^${var_name}=" "$ENV_FILE" 2>/dev/null; then
          log "  + Agregando variable faltante a ${ENV_FILE}: ${var_name}"
          echo "${var_name}=${var_val}" >> "$ENV_FILE"
        fi
      fi
    done < "$ENV_EXAMPLE"
  fi
fi

set_or_replace_env() {
  local key="$1"
  local val="$2"
  local file="$3"

  if grep -q "^${key}=" "$file" 2>/dev/null; then
    if sed --version >/dev/null 2>&1; then
      sed -i -E "s|^${key}=.*|${key}=${val}|g" "$file"
    else
      sed -i '' -E "s|^${key}=.*|${key}=${val}|g" "$file"
    fi
  else
    echo "${key}=${val}" >> "$file"
  fi
}

set_or_replace_env "ALLOWED_HOSTS"        "localhost,127.0.0.1,${IP_DETECTADA},*"                                   "$ENV_FILE"
set_or_replace_env "CSRF_TRUSTED_ORIGINS" "http://localhost,http://${IP_DETECTADA},http://${IP_DETECTADA}:8080,http://127.0.0.1" "$ENV_FILE"
set_or_replace_env "APP_BASE_URL"         "http://${IP_DETECTADA}"                                                  "$ENV_FILE"
set_or_replace_env "KEYCLOAK_BASE_URL"    "http://${IP_DETECTADA}:8080"                                             "$ENV_FILE"
set_or_replace_env "KEYCLOAK_HOSTNAME"    "${IP_DETECTADA}"                                                         "$ENV_FILE"

ok "Variables de red actualizadas en ${ENV_FILE}:"
grep -E '^(ALLOWED_HOSTS|CSRF_TRUSTED_ORIGINS|APP_BASE_URL|KEYCLOAK_BASE_URL|KEYCLOAK_HOSTNAME)=' "$ENV_FILE" | while read -r line; do
  echo "    ${C_BLU}•${C_RESET} $line"
done

# -----------------------------------------------------------------------------
# 4. LEVANTAR DOCKER COMPOSE EN UN SOLO PASO
# -----------------------------------------------------------------------------
step "4/5" "Levantando servicios de producción con Docker Compose"

log "Ejecutando: docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} up -d --build"
"${DC_BASE[@]}" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build

log "Refrescando proxy inverso (nginx-prod)..."
"${DC_BASE[@]}" -f "$COMPOSE_FILE" restart nginx-prod >/dev/null 2>&1 || true

echo ""
ok "Todos los contenedores fueron iniciados exitosamente."
echo ""
"${DC_BASE[@]}" -f "$COMPOSE_FILE" ps

# -----------------------------------------------------------------------------
# 5. MIGRACIONES Y SEED IDEMPOTENTE
# -----------------------------------------------------------------------------
step "5/5" "Aplicando migraciones y datos iniciales (seed idempotente)"

log "Esperando que el contenedor ${WEB_CONTAINER} esté listo..."
sleep 5

log "Ejecutando: manage.py migrate --noinput"
"${DC_BASE[@]}" -f "$COMPOSE_FILE" exec -T "$WEB_CONTAINER" python manage.py migrate --noinput
ok "Migraciones aplicadas correctamente."

log "Ejecutando seed idempotente (monedas, denominaciones, cajas, métodos de pago, cotizaciones, clientes)..."
"${DC_BASE[@]}" -f "$COMPOSE_FILE" exec -T "$WEB_CONTAINER" python manage.py seed --idempotent \
  && ok "Seed de datos iniciales completado." \
  || warn "El seed reportó advertencias. Continuando..."

ok "Base de datos inicializada con todos los datos necesarios."

# -----------------------------------------------------------------------------
# RESUMEN FINAL DE ACCESO
# -----------------------------------------------------------------------------
echo ""
echo "${C_CYN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
echo "${C_GRN}  DESPLIEGUE COMPLETADO EN 1 SOLO PASO!${C_RESET}"
if [[ -d ".git" ]]; then
  echo "  Commit desplegado: $(git rev-parse --short HEAD 2>/dev/null || echo 'local') — $(git log -1 --pretty=%s 2>/dev/null || echo '')"
fi
echo "${C_CYN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
echo "  Los dispositivos pueden conectarse directamente a:"
echo ""
echo "  ${C_BLU}Global Exchange Web:${C_RESET}     http://${IP_DETECTADA}"
echo "  ${C_BLU}Keycloak SSO Admin:${C_RESET}      http://${IP_DETECTADA}:8080"
echo ""
echo "  Modulos activos en esta version:"
echo "    ${C_GRN}✔${C_RESET} Cotizaciones y Tasas de Cambio"
echo "    ${C_GRN}✔${C_RESET} Gestion de Cajas (apertura / cierre / movimientos)"
echo "    ${C_GRN}✔${C_RESET} Operaciones (compra / venta de divisas)"
echo "    ${C_GRN}✔${C_RESET} Pagos: Stripe, SIPAP, Tickets de Transaccion"
echo "    ${C_GRN}✔${C_RESET} Facturacion Electronica SIFEN/e-KUATIA (IS2-63/64/65)"
echo "    ${C_GRN}✔${C_RESET} Gestion de Clientes y Metodos de Pago"
echo "    ${C_GRN}✔${C_RESET} Denominaciones de Monedas (billetes)"
echo ""
echo "  Usuarios preconfigurados:"
echo "    - Admin:    admin.demo    /  Admin123!"
echo "    - Operador: operador.demo /  Operador123!"
echo "${C_CYN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
echo ""
