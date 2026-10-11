# Sprint 4 — IS2-55: Confirmación del Estado de Pagos (Stripe & SIPAP)

## Historia de Usuario
> **Como cajero o administrador quiero recibir una confirmación del estado de los pagos realizados por los clientes para poder aprobar y procesar las operaciones de forma segura.**

---

## 1. Arquitectura y Componentes Implementados

### 1.1. Patrón de Diseño: Strategy / Adapter
Para aislar la lógica de pagos y facilitar la incorporación de futuras pasarelas, se diseñó la jerarquía:
- `PasarelaPago` (clase base abstracta en [pagos/services/base.py](file:///c:/Users/marap/OneDrive/Escritorio/is2code/is2-proyecto/pagos/services/base.py)).
- `StripePasarela` (implementación PaymentIntent en [pagos/services/stripe_service.py](file:///c:/Users/marap/OneDrive/Escritorio/is2code/is2-proyecto/pagos/services/stripe_service.py)).
- `SIPAPPasarela` (flujo manual con comprobante bancario en [pagos/services/sipap_service.py](file:///c:/Users/marap/OneDrive/Escritorio/is2code/is2-proyecto/pagos/services/sipap_service.py)).
- `TicketService` (generación y consulta del ticket de transacción inmutable en [pagos/services/ticket_service.py](file:///c:/Users/marap/OneDrive/Escritorio/is2code/is2-proyecto/pagos/services/ticket_service.py)).

### 1.2. Modelos de Datos (`pagos/models.py`)
1. **`ComprobanteSIPAP`**:
   - `operacion`: OneToOne con `cotizaciones.Operacion`.
   - `archivo`: Valida extensiones (`.jpg`, `.jpeg`, `.png`, `.pdf`) y tamaño máximo (5 MB).
   - `estado`: `PENDIENTE`, `APROBADO`, `RECHAZADO`.
   - Auditoría: `subido_por`, `revisado_por`, `fecha_subida`, `fecha_revision`, `motivo_rechazo`.
2. **`StripeEventoProcesado`**:
   - `event_id`: Unique index para garantizar idempotencia en recepciones repetidas de webhooks.
   - `tipo_evento`, `procesado_en`, `datos_resumen`.
3. **`TicketTransaccion`**:
   - Inmutable una vez generado.
   - `numero_ticket`: Identificador legible único con prefijo `TKT-XXXXXXXX`.
   - Snapshot de datos: `cliente_nombre`, `cliente_documento`, `monto`, `moneda_siglas`, `tasa_aplicada`, `comision`, `total_neto`.
   - `metodo_pago`: `STRIPE` o `SIPAP`.
   - `referencia_externa`: ID de PaymentIntent o código de operación bancaria.
   - `cajero`: Usuario operador/admin que aprobó manualmente (si aplica).

### 1.3. Ciclo de Vida y Estados de la Operación

```
                        ┌──────────────────────────────┐
                        │          PENDIENTE           │
                        └──────────────┬───────────────┘
                                       │
            ┌──────────────────────────┼─────────────────────────┐
            │                          │                         │
            ▼ (Adjuntar SIPAP)         ▼ (Stripe Succeeded)      ▼ (Stripe Failed)
┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
│PENDIENTE_CONFIRMACION │   │        PAGADA         │   │     PAGO_FALLIDO      │
└───────────┬───────────┘   │  + Emisión de Ticket  │   └───────────────────────┘
            │               └───────────────────────┘
    ┌───────┴───────┐
    ▼ (Aprobar)     ▼ (Rechazar con motivo)
┌───────┐       ┌───────────┐
│PAGADA │       │ RECHAZADA │
└───────┘       └───────────┘
```

---

## 2. Variables de Entorno Requeridas

En tu archivo `.env` (guíate por `.env.example`):

```bash
# --- Stripe (modo test / sandbox) ---
# Clave secreta (Dashboard > Developers > API keys)
STRIPE_SECRET_KEY=sk_test_51...

# Secreto del webhook obtenido con Stripe CLI o Dashboard
STRIPE_WEBHOOK_SECRET=whsec_...
```

> **Seguridad:** Nunca hardcodees estas claves en el código fuente. Se leen dinámicamente con `python-decouple`.

---

## 3. Pruebas Locales con Stripe CLI

### Paso 1: Instalar y autenticar Stripe CLI
Descarga Stripe CLI desde [stripe.com/docs/stripe-cli](https://stripe.com/docs/stripe-cli) o vía winget/scoop:
```powershell
scoop install stripe
# o
winget install Stripe.StripeCLI
```
Inicia sesión en modo test:
```powershell
stripe login
```

### Paso 2: Escuchar y reenviar webhooks
Ejecuta en una terminal el listener apuntando al endpoint de la app:
```powershell
stripe listen --forward-to localhost:8000/pagos/webhooks/stripe/
```
Stripe CLI te mostrará en consola tu webhook secret local:
```
> Ready! Your webhook signing secret is whsec_xxxxxxxxxxxx (^C to quit)
```
Copia ese valor en `STRIPE_WEBHOOK_SECRET` en tu archivo `.env`.

### Paso 3: Disparar eventos de prueba
En otra terminal, dispara eventos de simulación:

1. **Pago exitoso:**
   ```powershell
   stripe trigger payment_intent.succeeded
   ```
2. **Pago fallido:**
   ```powershell
   stripe trigger payment_intent.payment_failed
   ```

El servidor responderá con HTTP 200 de forma inmediata y verificará la firma cruda (`raw body`) contra el header `HTTP_STRIPE_SIGNATURE`.

---

## 4. Flujo Manual SIPAP (Para Cajeros y Clientes)

### 4.1. Flujo del Cliente
1. El cliente genera una operación de cambio de divisa (queda en estado `PENDIENTE`).
2. En la pantalla de detalle de operación ([/cotizaciones/operaciones/\<id\>/](file:///c:/Users/marap/OneDrive/Escritorio/is2code/is2-proyecto/cotizaciones/templates/cotizaciones/operaciones/detalle.html)), hace clic en **"Adjuntar Comprobante SIPAP"**.
3. Sube un archivo en formato JPG, PNG o PDF (máx. 5 MB) con drag-and-drop.
4. La operación pasa automáticamente al estado `PENDIENTE_CONFIRMACION`.

### 4.2. Flujo del Cajero / Administrador
1. Usuarios con rol `admin`, `operador` (cajero) o `supervisor` acceden al menú superior **"🏦 Comprobantes SIPAP"** (`/pagos/comprobantes/pendientes/`).
2. La vista muestra la lista de comprobantes pendientes con información del cliente, monto y moneda.
3. Al ingresar a **"Revisar Comprobante"**:
   - Visualiza la imagen o PDF adjunto y el resumen de la liquidación.
   - **Confirmar Pago:** Marca el comprobante como `APROBADO`, la operación como `PAGADA`, registra al cajero auditor y genera el ticket oficial.
   - **Rechazar Comprobante:** Despliega formulario de motivo obligatorio; al confirmar marca como `RECHAZADO` y la operación como `RECHAZADA`.

---

## 5. Ejecución de Pruebas Automatizadas

```powershell
# Pruebas exclusivas del módulo pagos (17 tests)
.venv\Scripts\python.exe manage.py test pagos --verbosity=2

# Pruebas integradas de cotizaciones y pagos (71 tests)
.venv\Scripts\python.exe manage.py test cotizaciones pagos --verbosity=2

# Suite completa del proyecto
.venv\Scripts\python.exe manage.py test
```

### Casos de prueba incluidos:
- **Webhook Stripe:**
  - Firma HMAC válida e inválida (400).
  - Transición a `PAGADA` y creación de ticket en `payment_intent.succeeded` y `checkout.session.completed`.
  - Transición a `PAGO_FALLIDO` en `payment_intent.payment_failed`.
  - Idempotencia: envío duplicado del mismo `event_id` no duplica tickets ni altera estado.
  - Validación de seguridad: discrepancia de monto entre Stripe y la orden impide el cambio de estado.
- **SIPAP:**
  - Carga de archivos válidos e invalidación de extensiones peligrosas (.exe/.txt).
  - Aprobación por cajero con registro de usuario auditor y fecha.
  - Rechazo con motivo obligatorio.
  - Bloqueo de re-confirmación de comprobantes ya aprobados.
  - Control de acceso: usuarios con rol cliente no pueden acceder a las vistas de cajero (403).
- **Ticket de Transacción:**
  - Formato de identificador único `TKT-XXXXXXXX`.
  - Inmutabilidad y snapshot completo de cliente y liquidación financiera.
  - Idempotencia de `TicketService.generar_ticket()`.
  - Restricción de acceso para usuarios no propietarios ni administrativos.
