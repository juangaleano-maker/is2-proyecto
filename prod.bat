@echo off
setlocal enabledelayedexpansion

REM Script de gestion del Ambiente de Produccion - Global Exchange
cd /d "%~dp0"

if "%1"=="" goto help
if "%1"=="help" goto help
if "%1"=="up" goto up
if "%1"=="start" goto up
if "%1"=="pull" goto pull
if "%1"=="update" goto update
if "%1"=="seed" goto seed
if "%1"=="down" goto down
if "%1"=="stop" goto down
if "%1"=="restart" goto restart
if "%1"=="logs" goto logs
if "%1"=="ps" goto status
if "%1"=="status" goto status
if "%1"=="migrate" goto migrate
if "%1"=="createsuperuser" goto createsuperuser
if "%1"=="keycloak-logs" goto keycloak_logs
if "%1"=="web-logs" goto web_logs

echo Comando desconocido: %1
goto help

:pull
if exist .git (
    echo ==============================================================
    echo  Sincronizando repositorio con la ultima version remota...
    echo ==============================================================
    for /f %%i in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set CURRENT_BRANCH=%%i
    if not defined CURRENT_BRANCH set CURRENT_BRANCH=develop
    echo Rama activa detectada: !CURRENT_BRANCH!
    echo Ejecutando: git pull origin !CURRENT_BRANCH!
    git pull origin !CURRENT_BRANCH!
    if errorlevel 1 (
        echo [AVISO] git pull no se completo limpiamente o no hay conexion.
    )
    for /f "delims=" %%c in ('git log -1 --pretty^=format:"%%h - %%s" 2^>nul') do echo Commit actual: %%c
    echo.
) else (
    echo [AVISO] No se encontro el directorio .git.
)
goto end

:update
call :pull
goto up

:seed
echo ==============================================================
echo  Ejecutando seed idempotente en web-prod...
echo ==============================================================
docker compose -f docker-compose.prod.yml exec web-prod python manage.py seed --idempotent
goto end

:up
docker info >nul 2>&1
if errorlevel 1 goto docker_error

if exist .git (
    echo ==============================================================
    echo  1. Sincronizando repositorio con la ultima version remota...
    echo ==============================================================
    for /f %%i in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set CURRENT_BRANCH=%%i
    if not defined CURRENT_BRANCH set CURRENT_BRANCH=develop
    echo Rama activa detectada: !CURRENT_BRANCH!
    echo Descargando cambios remotos (git pull origin !CURRENT_BRANCH!)...
    git pull origin !CURRENT_BRANCH!
    if errorlevel 1 (
        echo [AVISO] git pull no se pudo completar limpiamente o no hay conexion.
        echo Se continuara con el codigo local actual.
    )
    for /f "delims=" %%c in ('git log -1 --pretty^=format:"%%h - %%s" 2^>nul') do echo Commit actual: %%c
    echo.
)

if not exist .env.prod (
    if exist .env.prod.example (
        echo [AVISO] No se encontro .env.prod. Generando desde .env.prod.example...
        copy .env.prod.example .env.prod >nul
    )
)

echo ==============================================================
echo  2. Construyendo y levantando ambiente de produccion...
echo ==============================================================
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
if errorlevel 1 goto compose_error

echo.
echo ==============================================================
echo  3. Aplicando migraciones y seed de base de datos...
echo ==============================================================
docker compose -f docker-compose.prod.yml exec web-prod python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml exec web-prod python manage.py seed --idempotent

echo.
echo ==============================================================
echo  4. Estado de los servicios:
echo ==============================================================
docker compose -f docker-compose.prod.yml ps
echo.
echo Recargando configuracion de Nginx (resuelve IPs actualizadas)...
docker exec nginx-prod nginx -s reload >nul 2>&1
echo.
echo ==============================================================
echo  AMBIENTE DE PRODUCCION LEVANTADO Y ACTUALIZADO CON EXITO
echo  - Aplicacion Web (Nginx):    http://localhost
echo  - Keycloak SSO:              http://localhost:8080
echo  - Credenciales Admin KC:     admin / admin_prod_password
echo ==============================================================
goto end

:docker_error
echo.
echo ==============================================================
echo  ERROR: Docker Desktop no esta corriendo o no ha iniciado.
echo  Por favor:
echo    1. Abre la aplicacion Docker Desktop desde el menu Inicio.
echo    2. Espera a que el icono de Docker pase a verde.
echo    3. Vuelve a ejecutar: prod.bat up
echo ==============================================================
echo.
goto end

:compose_error
echo.
echo Error al construir o levantar los contenedores de produccion.
goto end

:down
echo Deteniendo ambiente de produccion...
docker compose -f docker-compose.prod.yml down
goto end

:restart
echo Reiniciando ambiente de produccion...
docker compose -f docker-compose.prod.yml restart
goto end

:logs
docker compose -f docker-compose.prod.yml logs -f %2 %3
goto end

:status
docker compose -f docker-compose.prod.yml ps
goto end

:migrate
echo Ejecutando migraciones en web-prod...
docker compose -f docker-compose.prod.yml exec web-prod python manage.py migrate
goto end

:createsuperuser
echo Creando superusuario de Django en web-prod...
docker compose -f docker-compose.prod.yml exec web-prod python manage.py createsuperuser
goto end

:web_logs
docker compose -f docker-compose.prod.yml logs -f web-prod
goto end

:keycloak_logs
docker compose -f docker-compose.prod.yml logs -f keycloak-prod
goto end

:help
echo.
echo ====================================================================
echo  Herramienta de Gestion de Produccion - Global Exchange
echo ====================================================================
echo  Uso: prod.bat [comando]
echo.
echo  Comandos disponibles:
echo    up / start        - Hace git pull, construye y levanta contenedores con migraciones y seed
echo    pull              - Sincroniza la rama actual con el repositorio remoto
echo    update            - Hace git pull y levanta/reconstruye el ambiente de produccion
echo    seed              - Puebla la base de datos de produccion de forma idempotente
echo    down / stop       - Detiene todos los contenedores de produccion
echo    restart           - Reinicia todos los contenedores
echo    status / ps       - Muestra el estado y puertos de los contenedores
echo    logs              - Muestra los logs en vivo de todos los servicios
echo    web-logs          - Muestra los logs en vivo de la aplicacion Django / Gunicorn
echo    keycloak-logs     - Muestra los logs en vivo de Keycloak
echo    migrate           - Ejecuta migraciones de Django dentro del contenedor
echo    createsuperuser   - Ejecuta createsuperuser interactivamente
echo.
goto end

:end
