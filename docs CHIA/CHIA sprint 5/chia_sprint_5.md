# Documentación de Asistencia Técnica y Desarrollo con IA — CHIA Sprint 5

**Proyecto:** Global Exchange - Casa de Cambios  
**Asignatura:** Ingeniería de Software 2 (FPUNA)  
**Semestre / Período:** 7mo Semestre - 2do Período 2026  
**Hito:** Hito 5 - Sprint 5 de Desarrollo de Software  
**Herramienta de Asistencia IA:** Antigravity / Gemini / Claude  

---

## 1. Introducción y Propósito del Sprint 5

Durante el ciclo de desarrollo del **Sprint 5**, las sesiones de *Pair Programming* y asistencia arquitectónica con la Inteligencia Artificial se enfocaron en la preparación, estabilización y automatización integral del **entorno de producción** para la plataforma *Global Exchange*.

Los principales desafíos técnicos abordados durante esta iteración fueron:
1. **Despliegue Automatizado Zero-Touch en Máquina Limpia (Ubuntu Server):** Diseño e implementación de scripts Bash resilientes (`deploy.sh` y `test_auto_ip.sh`) que permitan clonar, configurar, construir, migrar, poblar y verificar toda la plataforma en servidores remotos sin requerir pasos manuales previos.
2. **Autodetección Dinámica de IP de Red y Configuración de SSO:** Solución automatizada para identificar la dirección IP del servidor anfitrión (LAN, Wi-Fi o VPS en la nube) e inyectarla en tiempo de despliegue en las variables de Django (`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `APP_BASE_URL`) y Keycloak (`KEYCLOAK_BASE_URL`, `KEYCLOAK_HOSTNAME`).
3. **Módulo Nuclear de Facturación Electrónica SIFEN / e-Kuatia (IS2-63, IS2-64, IS2-65):** Generación de documentos tributarios electrónicos oficiales (DE) mediante la API ESI de Factura Segura, cálculo del Código Digital de Control (CDC) de 44 dígitos, generación de KuDE imprimible en PDF y arquitectura de fallback para contingencias sin conexión.
4. **Sincronización Automática de Variables de Entorno (`.env.prod`):** Mecanismo automático para propagar nuevas variables añadidas en `.env.prod.example` hacia el archivo `.env.prod` existente del servidor sin sobreescribir secretos o contraseñas generadas.

---

## 2. Registro de Consultas Técnicas y Soluciones de Producción

### 2.1. Arquitectura de Despliegue en 1 Solo Paso (`test_auto_ip.sh`)

#### Contexto y Desafío Técnico
Al desplegar en máquinas virtuales de evaluación (Ubuntu Server sobre VirtualBox o nube), las direcciones IP asignadas por DHCP varían según la red del laboratorio o el hogar. Esto provocaba errores críticos en producción:
- Bloqueo por `CSRF verification failed` en Django al acceder desde otra computadora.
- Bloqueo de redirecciones OAuth 2.0 en Keycloak por falta de coincidencia entre la URL de origen y la de redirección registrada.
- Necesidad de editar manualmente archivos `.env.prod` con `nano` o `vim`, proceso lento y propenso a errores tipográficos.

#### Prompt Formulado a la IA
```text
Necesito crear un script de despliegue en Bash para producción ('test_auto_ip.sh') que permita 
levantar todo el proyecto Global Exchange en una máquina virtual Ubuntu limpia en un solo paso.

Requerimientos específicos:
1. Autodetección de IP:
   - Detectar la IP real de la máquina (interfaz LAN/Wi-Fi mediante 'ip route' o 'hostname -I').
   - Dar prioridad a variables de entorno si el usuario fuerza SERVER_IP o HOST_IP.
   - Detectar IP pública si se trata de un VPS.
2. Configuración dinámica de entorno (.env.prod):
   - Crear .env.prod a partir de .env.prod.example si no existe.
   - Actualizar ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, APP_BASE_URL y KEYCLOAK_BASE_URL con la IP detectada.
   - Si .env.prod ya existe, no sobreescribir contraseñas, pero agregar automáticamente cualquier variable nueva que falte.
3. Orquestación Docker:
   - Detectar si docker necesita 'sudo' y hacer fallback automático.
   - Ejecutar 'docker compose -f docker-compose.prod.yml up -d --build'.
   - Reiniciar nginx-prod para refrescar caché DNS interno.
   - Ejecutar 'python manage.py migrate --noinput'.
   - Ejecutar 'python manage.py seed --idempotent' para cargar monedas, denominaciones y clientes iniciales.
4. Salida clara:
   - Imprimir los enlaces de acceso directo listos para usar desde el navegador de cualquier dispositivo en la red.
```

#### Solución e Implementación
La IA asistió en la creación de [`scripts/test_auto_ip.sh`](../../scripts/test_auto_ip.sh) con funciones estructuradas:
- `detect_ip()`: Identifica la interfaz de enrutamiento principal mediante `ip route get 1.1.1.1` con fallback a `hostname -I`.
- `set_or_replace_env()`: Reemplaza idempotentemente las variables de red en `.env.prod` usando expresiones regulares con `sed`.
- Bucle de sincronización de variables: Lee `.env.prod.example` línea por línea e inserta cualquier variable ausente en `.env.prod`.
- Automatización de migraciones y seed idempotente dentro del contenedor `web-prod`.

---

### 2.2. Configuración del Clúster de Producción (`docker-compose.prod.yml`)

#### Contexto y Desafío Técnico
A diferencia del entorno de desarrollo que utiliza `runserver` y SQLite/Postgres básico, producción requería una topología multicontenedor de alta concurrencia con aislamiento de red, manejo de estáticos y servicios asíncronos.

#### Consulta Técnica y Diseño
Se diseñó la topología compuesta por 6 servicios orquestados:
1. **`nginx-prod` (Nginx 1.25 Alpine):** Servidor de borde, terminación HTTP, compresión gzip y despacho de `/staticfiles/` y `/media/` desde volúmenes compartidos.
2. **`web-prod` (Gunicorn 23.0 WSGI):** 3 workers concurrentes ejecutando Django 5.1 optimizado (`DEBUG=False`).
3. **`db-prod` (PostgreSQL 16):** Base de datos transaccional con volumen persistente `db_prod_data` y healthcheck `pg_isready`.
4. **`redis-prod` (Redis 7 Alpine):** Memoria compartida para caché de Django y broker de mensajería para Celery.
5. **`celery-worker` y `celery-beat`:** Ejecución de tareas asíncronas y periódicas (notificaciones de tasas, alertas cambiarias).
6. **`keycloak-prod` y `keycloak-db-prod`:** Proveedor de identidad y SSO con importación automática del realm (`realm-export.json`).

---

### 2.3. Facturación Electrónica SIFEN / e-Kuatia (IS2-63, IS2-64, IS2-65)

#### Contexto y Desafío Técnico
La plataforma debía emitir facturas electrónicas oficiales ante la DNIT (SET) cumpliendo con las regulaciones de la República del Paraguay:
- Cada operación en estado `PAGADA` debe generar un Documento Electrónico (DE).
- Obtener el Código Digital de Control (CDC) de 44 caracteres numéricos.
- Ofrecer descarga del KuDE en formato PDF oficial y formato XML firmado.
- **Resiliencia obligatoria:** Si la API externa de Factura Segura o el servidor tributario está fuera de línea, el sistema debe activar un modo de simulación local (RNF37: tiempo de respuesta ≤ 5s) para no abortar la venta del cliente.

#### Prompt Formulado a la IA
```text
Diseña el servicio 'FacturaService' en 'pagos/services/factura_service.py' para integrar 
la API ESI de Factura Segura (https://apitest.facturasegura.com.py) con soporte de fallback:

1. Autenticación dinámica:
   - Login contra '/login?include_auth_token' usando EMAIL y PASSWORD configurados en .env.prod.
   - Cachear en memoria el Authentication-Token y renovarlo si devuelve 401.
2. Emisión de Documento Electrónico ('generar_de'):
   - Construir el payload JSON con timbrado, RUC emisor, punto de expedición, datos del cliente y desglose de IVA (10%).
   - Si la API responde con code == 0, almacenar el CDC oficial devuelto y marcar la factura como EMITIDA.
3. Descarga de KuDE PDF ('dwn_kude'):
   - Consumir el endpoint '/dwn_kude/{dRucEm}/{CDC}' para descargar el archivo binario PDF oficial.
   - Si la factura fue emitida en modo simulado o la API no dispone del PDF, redirigir al template HTML de KuDE imprimible.
4. Fallback y simulación:
   - Si no hay credenciales o hay fallo de red, generar un CDC simulado válido de 44 dígitos y marcar simulado=True.
```

#### Resultado Implementado
- Servicio [`pagos/services/factura_service.py`](../../pagos/services/factura_service.py) con patrón Dispatcher / Fallback.
- Pruebas automatizadas de emisión, anulación y visualización web en [`pagos/tests.py`](../../pagos/tests.py).
- Vista de impresión oficial [`pagos/templates/pagos/factura_kude_print.html`](../../pagos/templates/pagos/factura_kude_print.html) con código QR generado en JavaScript y desglose tributario.

---

### 2.4. Resolución de Problemas en Producción (Troubleshooting de Despliegue)

Durante las pruebas de despliegue en la máquina virtual, se registraron y resolvieron interactivamente las siguientes incidencias:

| Problema Identificado | Causa Raíz | Solución Asistida por IA |
|---|---|---|
| `git pull` cancelado con error `Aborting: untracked file test_auto_ip.sh` | El script existía en la MV de forma local sin estar trackeado en Git. | Se instruyó ejecutar `rm scripts/test_auto_ip.sh` y luego `git pull` para sincronizar limpiamente con `develop`. |
| La factura se emitía en "modo simulado" en lugar de llamar a la API | Las variables `FACTURA_SEGURA_*` se habían creado en `.env.prod.example` pero `.env.prod` en la MV no se había actualizado. | Se implementó la auto-sincronización en `test_auto_ip.sh` y se agregaron las variables al archivo `.env` local. |
| Rol `cajero` no aparecía en Keycloak en la MV | Keycloak solo importa `realm-export.json` cuando la base de datos está vacía; si ya tenía volumen anterior, ignora el archivo. | Se documentó el procedimiento de reseteo del volumen de Keycloak y la alternativa de creación vía API REST administrativa. |
| Permisos de ejecución de scripts en Linux | Al editar scripts en Windows, se perdía el bit ejecutable (`chmod +x`). | Se aplicó `git update-index --chmod=+x` en el repositorio para que se preserve el bit ejecutable de forma nativa en Git. |

---

## 3. Matriz de Prompts Representativos del Sprint 5

### Prompt 1: Resiliencia de Docker y Detección de Superusuario
> *"El script de despliegue debe ejecutarse tanto en servidores donde el usuario pertenece al grupo docker como en servidores donde se requiere sudo. Haz que detecte automáticamente si docker info falla y use sudo docker de forma transparente."*

### Prompt 2: Auto-sincronización de variables de entorno
> *"En los servidores remotos, .env.prod ya existe con contraseñas seguras generadas. Modifica test_auto_ip.sh para que lea .env.prod.example y, si detecta variables que no existen en .env.prod (como las de Factura Segura), las agregue al final sin tocar los valores ya existentes."*

### Prompt 3: Descarga binaria de KuDE vs. Vista HTML imprimible
> *"Cuando el usuario presiona Descargar KuDE, si la factura se emitió en Factura Segura real debe retornar el PDF binario con Content-Disposition attachment. Si fue simulada, debe redirigir al template HTML con un mensaje amigable y permitir imprimir con Ctrl+P."*

---

## 4. Conclusiones y Estado del Hito

El Sprint 5 consolidó la madurez DevOps del proyecto *Global Exchange*. Gracias a la asistencia de la IA en la creación de scripts inteligentes y topologías Docker de producción:
- El tiempo de despliegue en un servidor virgen se redujo de **más de 1 hora de pasos manuales a 30 segundos totalmente desatendidos**.
- Se habilitó la conexión real con el ecosistema de Facturación Electrónica SIFEN (e-Kuatia) manteniendo la seguridad y la resiliencia operativa.
- Se verificó la correcta sincronización de roles y autenticación mediante Keycloak SSO sobre redes dinámicas.
