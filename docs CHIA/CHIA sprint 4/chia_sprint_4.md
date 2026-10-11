# Documentación de Desarrollo - CHIA Sprint 4

## 1. Resumen del Sprint
- **Ramas trabajadas:** `feature/IS2-60`, `feature/IS2-61`
- **Entorno de ejecución:** Docker / Docker Compose
- **Tecnologías:** Python / Django ORM, HTML/Bootstrap, Unittest

---

## 2. Historia de Usuario IS2-60: Apertura y Cierre de Caja

### Criterios de Aceptación
1. **Apertura de Caja:**
   - Ingreso de monto inicial (fondo de caja) al inicio de la jornada.
   - Validación para impedir múltiples cajas abiertas por el mismo cajero/sucursal.
2. **Cierre de Caja:**
   - Opción explícita de "Cerrar Caja" con declaración de monto final físico.
3. **Cálculo de Arqueo y Balance:**
   - Cálculo del saldo esperado vs. monto declarado.
   - Clasificación del balance en: Exacto, Faltante o Sobrante.

### Prompt de Código Utilizado (IS2-60)
```markdown
Estoy trabajando en la rama feature/IS2-60 del proyecto Django, el cual corre dentro de un entorno Docker / Docker Compose.

Necesito implementar la funcionalidad de Apertura y Cierre de Caja para el rol de Cajero. A continuación te detallo la User Story y los Criterios de Aceptación:

---
### Historia de Usuario: Apertura y Cierre de Caja
> Como cajero  
> Quiero poder realizar la apertura y el cierre de mi caja asignada  
> Para llevar un control exacto de los fondos al inicio y final de mi turno.

---
### Criterios de Aceptación:
1. Apertura de Caja:
   - El cajero debe poder aperturar una caja indicando el monto inicial (fondo de caja) al inicio del turno.
   - Si la caja o el cajero ya tiene una sesión/turno de caja abierta, no se debe permitir abrir otra hasta cerrar la actual.

2. Cierre de Caja:
   - Al finalizar el turno, debe existir la opción de "Cerrar Caja".
   - El cajero declara el monto final físico que realmente hay en caja.

3. Cálculo de Arqueo y Balance:
   - El sistema debe calcular automáticamente el saldo esperado del turno (Monto Inicial + Ingresos - Egresos de transacciones confirmadas).
   - El sistema calcula la diferencia (Monto Declarado - Saldo Esperado) y clasifica el resultado:
     * EXACTO: diferencia == 0
     * FALTANTE: diferencia < 0
     * SOBRANTE: diferencia > 0
   - Registro de fecha/hora de apertura y cierre, usuario responsable y observaciones si las hubiera.

Requerimientos técnicos:
- Modelo `SesionCaja` en `cotizaciones` (o app afín).
- Vistas con validaciones de rol Cajero/Admin.
- Formularios de apertura y cierre con validaciones.
- Templates consistentes con el diseño de la plataforma.
- Rutas propias bajo `/caja/`.
- Pruebas unitarias completas.
```

### Implementación Realizada (IS2-60)
- **Modelos (`cotizaciones/models.py`)**:
  - Creación del modelo `SesionCaja` con campos `cajero`, `nombre_caja`, `monto_inicial`, `fecha_apertura`, `fecha_cierre`, `monto_final_declarado`, `saldo_esperado`, `diferencia`, `estado` (`ABIERTA`/`CERRADA`) y `observaciones`.
  - Métodos `calcular_saldo_esperado()`, `cerrar()` y property `tipo_diferencia`.
- **Formularios (`cotizaciones/forms.py`)**:
  - `AperturaCajaForm`: validación de monto inicial no negativo.
  - `CierreCajaForm`: validación de monto físico declarado no negativo y campo opcional de observaciones.
- **Vistas y Controladores (`cotizaciones/views.py`)**:
  - `apertura_caja_view`: validación de una única caja abierta activa por cajero.
  - `caja_dashboard_view`: visualización en tiempo real del estado de caja y saldo actual.
  - `cierre_caja_view`: procesamiento de arqueo, cálculo de diferencias y cierre de sesión.
- **Rutas (`global_exchange/urls.py`)**:
  - `/caja/apertura/`, `/caja/estado/`, `/caja/cierre/`.
- **Templates**:
  - `cotizaciones/templates/cotizaciones/caja/apertura.html`
  - `cotizaciones/templates/cotizaciones/caja/dashboard.html`
  - `cotizaciones/templates/cotizaciones/caja/cierre.html`
- **Migraciones y Pruebas**:
  - Migración `0006_sesioncaja.py`.
  - Pruebas de integración `SesionCajaViewTestCase` en `cotizaciones/tests.py`.

---

## 3. Historia de Usuario IS2-61: Registro de Movimientos de Caja

### Criterios de Aceptación
1. **Registro Automático de Transacciones:**
   - Vinculación automática de compras, ventas y pagos confirmados a la sesión de caja activa (`ABIERTA`) del cajero.
   - Operaciones de tipo compra (ingreso de divisa) clasificadas como `INGRESO` de caja; ventas clasificadas como `EGRESO`.
2. **Actualización de Saldo en Tiempo Real:**
   - Impacto directo e instantáneo de cada transacción sobre el saldo esperado de la caja.
3. **Bloqueo sin Caja Abierta:**
   - Bloqueo de confirmación/procesamiento de pagos si el cajero no cuenta con una sesión de caja abierta, emitiendo una notificación de advertencia y redireccionamiento a apertura.
4. **Historial de Movimientos:**
   - Visualización cronológica de ingresos y egresos. Acceso segmentado para cajero (sus sesiones) y administradores/supervisores (todas las sesiones con filtros avanzados).

### Prompt de Código Utilizado (IS2-61)
```markdown
Estoy trabajando en la rama feature/IS2-61 del proyecto Django, el cual corre dentro de un entorno Docker / Docker Compose.

Esta tarea es la continuación del sistema de cajas. Necesito implementar la funcionalidad de Registro de Movimientos de Caja para vincular las transacciones (compras/ventas/pagos) con la caja activa del cajero.

A continuación te detallo la User Story y los Criterios de Aceptación:

---
### Historia de Usuario: Registro de movimientos de Caja
> Como cajero  
> Quiero que todas las operaciones de compra/venta y pagos confirmados se registren automáticamente en mi caja actual  
> Para que el saldo de la caja se mantenga actualizado en tiempo real.

---
### Criterios de Aceptación:
1. Registro Automático de Transacciones:
   - Cada vez que se confirme una compra, venta o pago en el sistema, debe asociarse a la sesión/turno de caja activa (ABIERTA) del usuario o sucursal correspondiente.
   - Si la operación es un ingreso (ej. venta / cobro), debe sumar al saldo esperado.
   - Si la operación es un egreso (ej. compra / pago al cliente), debe restar del saldo esperado.
   - Si no hay una caja abierta al momento de realizar una transacción que afecte fondos, el sistema debe emitir un mensaje de advertencia claro o impedir la transacción indicando que se debe abrir caja primero.

2. Trazabilidad de Movimientos:
   - Cada movimiento debe registrar: fecha/hora, tipo (INGRESO/EGRESO), monto, concepto/descripción, referencia a la operación asociada (ID de operación) y usuario responsable.

3. Consulta de Movimientos:
   - El cajero debe poder ver en el Dashboard de Caja el listado de movimientos de su turno actual con el saldo acumulado en tiempo real.
   - El administrador o supervisor debe poder consultar el historial de movimientos filtrando por caja, cajero y rango de fechas.

Requerimientos técnicos:
- Modelo `MovimientoCaja` con relación ForeignKey a `SesionCaja` y relación a `Operacion`.
- Señal Django (`post_save` en `Operacion`) o integración en el flujo de confirmación para crear el movimiento de caja automáticamente al pasar a estado PAGADA.
- Actualización de `SesionCaja.calcular_saldo_esperado()` para basarse en los movimientos de caja registrados.
- Vista y template de Historial de Movimientos de Caja con filtros por fecha, tipo y cajero.
- Pruebas unitarias para validar la creación automática de movimientos, actualización de saldos y control sin caja abierta.
```

### Implementación Realizada (IS2-61)
- **Modelos (`cotizaciones/models.py`)**:
  - Modelo `MovimientoCaja` con atributos `sesion` (FK `SesionCaja`), `tipo` (`INGRESO`/`EGRESO`), `monto`, `concepto`, `operacion` (`OneToOneField` a `Operacion`), `fecha` y `registrado_por` (FK `User`).
  - Refactorización de `SesionCaja.calcular_ingresos_turno()` para totalizar mediante `Sum` sobre `self.movimientos.all()`.
- **Señales Automatizadas (`cotizaciones/signals.py` y `apps.py`)**:
  - Señal `post_save` sobre el modelo `Operacion`: detecta transición a estado `PAGADA`, resuelve la sesión `ABIERTA` del cajero y persiste el `MovimientoCaja` evitando duplicados.
  - Registro de señales en `CotizacionesConfig.ready()`.
- **Validaciones de Negocio en Vistas (`cotizaciones/views.py`)**:
  - `confirmar_operacion_pago`: validación previa de existencia de sesión de caja activa. Si no existe, se bloquea la confirmación del pago y redirige a `apertura_caja`.
  - Inyección del botón de acción directa `💳 Pagar / Confirmar` en `cotizaciones/templates/cotizaciones/operaciones/lista.html`.
  - `historial_movimientos_view`: soporte de filtros combinados por cajero, tipo de movimiento y fechas con cálculo de balance neto.
- **Rutas (`global_exchange/urls.py`)**:
  - `/caja/movimientos/` enlazada a `historial_movimientos_view`.
- **Interfaces Visuales**:
  - `cotizaciones/templates/cotizaciones/caja/movimientos.html`: panel de filtros, métricas de ingresos/egresos/balance y tabla de movimientos.
  - `cotizaciones/templates/cotizaciones/caja/dashboard.html`: tarjetas métricas de ingresos y egresos del turno y tabla de movimientos en tiempo real.
  - `authentication/templates/authentication/menu.html`: inclusión de la tarjeta `📜 Movimientos de Caja`.
- **Migraciones y Pruebas**:
  - Migración `0007_movimientocaja.py`.
  - Suite de pruebas unitarias `MovimientoCajaTestCase` (7 pruebas unitarias específicas, 76 pruebas totales del módulo ejecutadas exitosamente).
