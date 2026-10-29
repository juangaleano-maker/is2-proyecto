#!/usr/bin/env bash
# =============================================================================
# test_auto_ip.sh — Despliegue en 1 SOLO PASO con Autodetección de IP
# =============================================================================
# Este script:
#   1. Detecta automáticamente la IP de la máquina (LAN / Wi-Fi o Cloud VPS).
#   2. Configura las variables en .env.prod (Django ALLOWED_HOSTS, CSRF y Keycloak).
#   3. Construye y levanta toda la pila de Docker de producción.
#   4. Muestra los enlaces finales listos para ingresar desde cualquier dispositivo.
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

# -----------------------------------------------------------------------------
# 1. VERIFICAR DOCKER
# -----------------------------------------------------------------------------
step "1/4" "Verificando motor de Docker"

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

# Docker Compose base command
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
step "2/4" "Autodetección de la dirección IP del servidor"

detect_ip() {
  local ip=""

  # Prioridad 1: Override manual si el usuario pasó HOST_IP o SERVER_IP
  if [[ -n "${HOST_IP:-}" ]]; then
    echo "$HOST_IP"
    return
  fi
  if [[ -n "${SERVER_IP:-}" ]]; then
    echo "$SERVER_IP"
    return
  fi

  # Prioridad 2: IP local de la interfaz de red principal (LAN / Wi-Fi / Bridged)
  ip=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7}')
  if [[ -z "$ip" ]]; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  fi

  # Prioridad 3: IP pública si es un VPS en la nube (Oracle Cloud, etc.)
  local public_ip=""
  public_ip=$(curl -s --max-time 2 -4 ifconfig.me 2>/dev/null || curl -s --max-time 2 -4 icanhazip.com 2>/dev/null || true)
  if [[ "$public_ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    # Si la IP local es interna de NAT VirtualBox o se pide usar IP pública:
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
step "3/4" "Configurando variables de producción (${ENV_FILE})"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$ENV_EXAMPLE" ]]; then
    log "Creando ${ENV_FILE} a partir de ${ENV_EXAMPLE}..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"
  else
    die "No existe ${ENV_FILE} ni tampoco ${ENV_EXAMPLE}."
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

set_or_replace_env "ALLOWED_HOSTS" "localhost,127.0.0.1,${IP_DETECTADA},*" "$ENV_FILE"
set_or_replace_env "CSRF_TRUSTED_ORIGINS" "http://localhost,http://${IP_DETECTADA},http://${IP_DETECTADA}:8080,http://127.0.0.1" "$ENV_FILE"
set_or_replace_env "APP_BASE_URL" "http://${IP_DETECTADA}" "$ENV_FILE"
set_or_replace_env "KEYCLOAK_BASE_URL" "http://${IP_DETECTADA}:8080" "$ENV_FILE"
set_or_replace_env "KEYCLOAK_HOSTNAME" "${IP_DETECTADA}" "$ENV_FILE"

ok "Variables de red actualizadas en ${ENV_FILE}:"
grep -E '^(ALLOWED_HOSTS|CSRF_TRUSTED_ORIGINS|APP_BASE_URL|KEYCLOAK_BASE_URL|KEYCLOAK_HOSTNAME)=' "$ENV_FILE" | while read -r line; do
  echo "    ${C_BLU}•${C_RESET} $line"
done

# -----------------------------------------------------------------------------
# 4. LEVANTAR DOCKER COMPOSE EN UN SOLO PASO
# -----------------------------------------------------------------------------
step "4/4" "Levantando servicios de producción con Docker Compose"

log "Ejecutando: docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} up -d"
"${DC_BASE[@]}" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

# Refrescar Nginx para evitar 502 Bad Gateway por caché de DNS interna
log "Refrescando proxy inverso (nginx-prod)..."
"${DC_BASE[@]}" -f "$COMPOSE_FILE" restart nginx-prod >/dev/null 2>&1 || true

echo ""
ok "Todos los contenedores fueron iniciados exitosamente."

# Estado de contenedores
echo ""
"${DC_BASE[@]}" -f "$COMPOSE_FILE" ps

# -----------------------------------------------------------------------------
# RESUMEN FINAL DE ACCESO
# -----------------------------------------------------------------------------
echo ""
echo "${C_CYN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
echo "${C_GRN}  🎉 ¡DESPLIEGUE COMPLETADO EN 1 SOLO PASO!${C_RESET}"
echo "${C_CYN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
echo "  Los dispositivos pueden conectarse directamente a:"
echo ""
echo "  🌐 ${C_BLU}Global Exchange Web:${C_RESET}     http://${IP_DETECTADA}"
echo "  🔑 ${C_BLU}Keycloak SSO Admin:${C_RESET}      http://${IP_DETECTADA}:8080"
echo ""
echo "  Usuarios preconfigurados:"
echo "    - Admin:    admin.demo    /  Admin123!"
echo "    - Operador: operador.demo /  Operador123!"
echo "${C_CYN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
echo ""
