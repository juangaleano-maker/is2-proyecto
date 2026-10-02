# Registro CHIA - Sprint 3

## Dependencias de Arquitectura y Flujo de Desarrollo

Durante el inicio del Sprint 3, se realizó una consulta técnica a la IA sobre la estructuración de dependencias entre los componentes a desarrollar para el módulo de transacciones (Compra, Venta, Cancelación e Historial).

### Análisis Técnico y Resolución de Bloqueos

Se identificaron dependencias clave para garantizar la integración continua sin bloqueos entre los desarrolladores:

1. **Definición de Modelo Base (`Operacion`)**:
   - Se estableció como requisito bloqueante la creación y migración del modelo unificado `Operacion` (o `Transaccion`) antes de iniciar el desarrollo individual.
   - **Campos críticos definidos**: Cliente (FK), Moneda (FK), Tipo (Enum: Compra/Venta), Monto (Decimal), Tasa Aplicada (Decimal), Comisión (Decimal), Fecha (DateTime), y Estado (Enum: Pendiente, Completada, Cancelada).

2. **Paralelismo en Operaciones de Compra y Venta**:
   - Los módulos de Compra y Venta no presentan acoplamiento directo entre sí.
   - Ambas implementaciones deben persistir la transacción inicial con el estado transitorio `PENDIENTE` para permitir la inyección de validaciones posteriores.

3. **Inyección de Servicio de Validación de Cotización (Cancelación)**:
   - El módulo de cancelación requiere acoplarse al flujo antes de la confirmación final del pago.
   - Se diseñó el servicio de validación de manera asíncrona: compara la tasa persistida en la transacción `PENDIENTE` contra la tasa vigente actual.
   - Este componente actúa como middleware de validación antes de actualizar el estado a `PAGADA`.

4. **Desacoplamiento del Historial y Generación de Reportes**:
   - El módulo de historial (lectura) y comprobantes (PDF) se desacopló del flujo de escritura.
   - Se instruyó el desarrollo de las vistas e interfaces basándose en los esquemas del modelo, utilizando datos simulados (Mocks) hasta la integración final de los módulos de Compra/Venta.

### Implementación Realizada (Módulo Historial y Comprobantes)

Tras la unificación del modelo `Operacion`, la IA fue instruida para codificar e integrar el módulo de historial. Se realizaron los siguientes aportes técnicos:

- **Views (`cotizaciones/views.py`)**:
  - Implementación de `historial_operaciones` con soporte para queries filtrados por el campo `estado` optimizando las consultas con `select_related('cliente', 'moneda')`.
  - Implementación de `descargar_comprobante_operacion` para la exportación de comprobantes individuales.
- **Routing (`cotizaciones/urls.py`)**: Inclusión de rutas parametrizadas para el consumo de las vistas.
- **Templates**:
  - Desarrollo de `historial_operaciones.html` utilizando el sistema de diseño existente (Bootstrap + Custom CSS).
  - Desarrollo de `comprobante_operacion.html` integrando media queries `@media print` para renderizado y exportación nativa a PDF (sin dependencia de librerías externas como WeasyPrint o ReportLab, minimizando el peso del proyecto).




### 8.4. Módulo de Comprar Moneda (Historia IS2-15)

- **Contexto / Problema:** Se requirió implementar el módulo "Comprar Moneda" asignado a la rama `feature/is2-15`. Los criterios de aceptación establecían: autenticación obligatoria, solicitud de datos específicos (cliente, moneda, monto, tasa aplicada), cálculo automático de la comisión y registro en estado `Pendiente`. Adicionalmente, el frontend no debía permitir valores nulos o negativos, y la tabla de operaciones debía ser visible directamente en la plataforma web (sin depender de Django Admin).
- **Análisis de la IA:**
  1. Se agregó el modelo `Operacion` en `cotizaciones/models.py` relacionando las claves foráneas con las apps de `clientes` y `monedas`.
  2. Se configuró un formulario `ComprarMonedaForm` en `cotizaciones/forms.py` y se implementaron validaciones de integridad de datos (atributos HTML `min="0.01"` y métodos de saneamiento backend `clean_monto`, `clean_tasa_aplicada`) para bloquear transacciones inválidas.
  3. Se programó la vista controladora `comprar_moneda` en `cotizaciones/views.py` gestionando la lógica de negocio subyacente: inyección del estado predeterminado (`PENDIENTE`), tipo de operación (`COMPRA`) y cálculo porcentual paramétrico de la comisión.
  4. Se constató la usabilidad del sistema integrando botones de redirección en el `menu.html` principal.
  5. Tras un `ProgrammingError` ("relation does not exist"), se ejecutaron por consola las migraciones correspondientes `makemigrations` y `migrate` sobre el contenedor del servicio web (`docker compose exec web-dev`).
  6. Para responder a los requerimientos de la interfaz, se construyó una vista pública de historial en `listar_operaciones.html` orquestada por el controlador `listar_operaciones` con soporte para insignias descriptivas, evadiendo la dependencia al backend administrativo de Django.
- **Solución Aplicada:**
  - Código inyectado y estabilizado en `cotizaciones/models.py`, `forms.py`, `urls.py`, y `views.py`.
  - Interfaces visuales desplegadas en `comprar_moneda.html`, `listar_operaciones.html` y actualización del `menu.html`.
  - Migraciones de base de datos sincronizadas sobre contenedores Docker.
