#!/bin/bash
# ==============================================================================
# Script de gestión del Ambiente de Producción - Global Exchange (Linux / macOS)
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"

sync_git() {
  if [ -d ".git" ]; then
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "develop")
    echo "=============================================================="
    echo " 1. Sincronizando repositorio con la última versión de GitHub..."
    echo " Rama activa detectada: $CURRENT_BRANCH"
    echo "=============================================================="
    git pull origin "$CURRENT_BRANCH" || echo "Aviso: No se pudo hacer pull; continuando con versión local."
    echo "Commit actual: $(git log -1 --pretty=format:"%h - %s" 2>/dev/null || echo '')"
    echo ""
  fi
}

case "$1" in
  pull)
    sync_git
    ;;
  update)
    sync_git
    exec "$0" up
    ;;
  seed)
    echo "Ejecutando seed idempotente en web-prod..."
    docker compose -f "$COMPOSE_FILE" exec web-prod python manage.py seed --idempotent
    ;;
  up|start)
    if ! docker info >/dev/null 2>&1; then
      echo ""
      echo "=============================================================="
      echo " ERROR: El motor de Docker no está corriendo."
      echo " Asegúrate de iniciar Docker / Docker Desktop primero."
      echo "=============================================================="
      echo ""
      exit 1
    fi
    sync_git
    if [ ! -f "$ENV_FILE" ]; then
      echo "Aviso: No se encontró $ENV_FILE. Creándolo automáticamente desde $ENV_FILE.example..."
      cp "$ENV_FILE.example" "$ENV_FILE"
    fi
    echo "=============================================================="
    echo " 2. Levantando ambiente de producción con Docker Compose..."
    echo "=============================================================="
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build
    echo ""
    echo "=============================================================="
    echo " 3. Aplicando migraciones y seed de base de datos..."
    echo "=============================================================="
    docker compose -f "$COMPOSE_FILE" exec web-prod python manage.py migrate --noinput
    docker compose -f "$COMPOSE_FILE" exec web-prod python manage.py seed --idempotent
    echo ""
    echo "Estado de los servicios:"
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
    echo "Recargando configuración de Nginx..."
    docker exec nginx-prod nginx -s reload >/dev/null 2>&1 || true
    echo ""
    echo "=============================================================="
    echo " AMBIENTE DE PRODUCCION LEVANTADO Y ACTUALIZADO CON EXITO"
    echo " - Aplicación Web (Nginx):    http://localhost"
    echo " - Keycloak SSO:              http://localhost:8080"
    echo " - Credenciales Admin KC:     admin / admin_prod_password"
    echo "=============================================================="
    ;;
  down|stop)
    echo "Deteniendo ambiente de producción..."
    docker compose -f "$COMPOSE_FILE" down
    ;;
  restart)
    echo "Reiniciando contenedores de producción..."
    docker compose -f "$COMPOSE_FILE" restart
    ;;
  status|ps)
    docker compose -f "$COMPOSE_FILE" ps
    ;;
  logs)
    shift
    docker compose -f "$COMPOSE_FILE" logs -f "$@"
    ;;
  web-logs)
    docker compose -f "$COMPOSE_FILE" logs -f web-prod
    ;;
  keycloak-logs)
    docker compose -f "$COMPOSE_FILE" logs -f keycloak-prod
    ;;
  migrate)
    echo "Ejecutando migraciones en web-prod..."
    docker compose -f "$COMPOSE_FILE" exec web-prod python manage.py migrate
    ;;
  createsuperuser)
    echo "Creando superusuario en web-prod..."
    docker compose -f "$COMPOSE_FILE" exec web-prod python manage.py createsuperuser
    ;;
  *)
    echo "===================================================================="
    echo " Herramienta de Gestión de Producción - Global Exchange"
    echo "===================================================================="
    echo " Uso: ./prod.sh [comando]"
    echo ""
    echo " Comandos disponibles:"
    echo "   up / start        - Hace git pull, construye y levanta contenedores con migraciones y seed"
    echo "   pull              - Sincroniza la rama actual con el repositorio remoto"
    echo "   update            - Hace git pull y reconstruye la pila de producción"
    echo "   seed              - Puebla la base de datos de producción (idempotente)"
    echo "   down / stop       - Detiene todos los contenedores"
    echo "   restart           - Reinicia todos los contenedores"
    echo "   status / ps       - Muestra el estado de los contenedores"
    echo "   logs              - Muestra los logs en tiempo real"
    echo "   web-logs          - Muestra logs de Django / Gunicorn"
    echo "   keycloak-logs     - Muestra logs de Keycloak"
    echo "   migrate           - Ejecuta migraciones de base de datos"
    echo "   createsuperuser   - Ejecuta createsuperuser interactivamente"
    echo ""
    exit 1
    ;;
esac
