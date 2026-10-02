#!/bin/bash
# ==============================================================================
# Script de gestión del Ambiente de Producción - Global Exchange (Linux / macOS)
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"

case "$1" in
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
    echo "Levantando ambiente de producción con Docker Compose..."
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build
    echo ""
    echo "Estado de los servicios:"
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
    echo "=============================================================="
    echo " AMBIENTE DE PRODUCCION LEVANTADO CON EXITO"
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
    echo "   up / start        - Construye y levanta la pila de producción"
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
