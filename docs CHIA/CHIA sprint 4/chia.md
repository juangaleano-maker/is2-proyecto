# CHIA: Conversación Histórica de Inteligencia Artificial

## Sprint 4 - Corrección QA: Tasa Vigente Forzada en Venta de Moneda

**Usuario (Juan):**
Tenemos una observación del QA del sprint anterior: "Ajustar en las pantallas de compra y venta el campo tasa que estire directamente de lo registrado por día como vigente y que la comisión sea calculada".
Yo me encargaré de la parte de Venta. Necesito que modifiques el flujo de venta de divisas para que el campo `tasa_aplicada` tome de forma obligatoria el valor de la cotización vigente del día y no permita que el cliente o el frontend inyecte una tasa manipulada. Además, el cálculo de la comisión debe ejecutarse desde el backend de forma automática para evitar inconsistencias.

**Antigravity:**
Entendido. Esta es una corrección de seguridad y consistencia de datos crítica. Para cumplir con esta directiva de QA, realizaré modificaciones en tres capas de la arquitectura:

1. **Capa de Lógica de Negocio (Views - `venta_moneda_view`):** 
   En el método POST, interceptaré los datos del `VentaMonedaForm`. Independientemente del valor que venga en el payload HTTP para `tasa_aplicada`, invocaré el servicio `obtener_tasa_sugerida(moneda, tipo='VENTA')` para obtener la tasa de compra activa registrada por el analista cambiario. El backend utilizará estrictamente esta tasa para recalcular la comisión mediante `calcular_comision_operacion` y persistir la transacción. Si no hay cotización activa para la divisa, la transacción será rechazada.

2. **Capa de Presentación (Forms - `VentaMonedaForm`):** 
   Configuraré el campo `tasa_aplicada` con el atributo HTML `readonly` y estilos de bloqueo. Además, sobrescribiré el método `clean_tasa_aplicada` para relajar la validación estricta de igualdad, permitiendo que el request pase la barrera del form (validando solo que sea un número positivo), ya que la responsabilidad de imponer la tasa recaerá sobre la vista.

3. **Capa de Interfaz de Usuario (Template - `venta.html`):** 
   Modificaré el DOM mediante JavaScript (`onMonedaChange`). Al seleccionar una moneda, el campo se poblará automáticamente con la tasa vigente pre-cargada en `TASAS_DATA` y se bloqueará su edición. Agregué listeners para revertir cualquier intento de modificación manual. También añadí un indicador visual "● AUTOMÁTICA" para mejorar la experiencia de usuario y clarificar la inmutabilidad del campo.

He procedido con la implementación y he agregado un test unitario `test_tasa_vigente_fuerza_tasa_enviada_por_formulario` en `VentaMonedaTestCase` que inyecta un payload malicioso (`'tasa_aplicada': '9999.00'`) y aserta que el sistema persiste la operación con la tasa vigente correcta de la base de datos, garantizando la integridad de la transacción.

**Usuario:**
Excelente aproximación técnica. Con esta corrección aseguramos que la liquidación se base siempre en las tasas autorizadas del día y blindamos el endpoint. Procederé a revisar las pruebas.
