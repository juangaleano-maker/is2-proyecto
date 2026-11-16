# Documentación de Asistencia Técnica y Desarrollo con IA — CHIA Sprint 6

**Proyecto:** Global Exchange - Casa de Cambios  
**Asignatura:** Ingeniería de Software 2 (FPUNA)  
**Semestre / Período:** 7mo Semestre - 2do Período 2026  
**Hito:** Hito 6 - Sprint 6 de Desarrollo de Software  
**Herramienta de Asistencia IA:** Antigravity / Gemini  

---

## 1. Introducción y Propósito del Sprint

Durante el ciclo de desarrollo del **Sprint 6**, las sesiones de *Pair Programming* y asistencia arquitectónica con la Inteligencia Artificial se enfocaron en la consolidación del subsistema financiero, analítico y gerencial de la plataforma *Global Exchange*.

Los esfuerzos técnicos se concentraron en dos áreas principales:
1. **Módulo de Auditoría y Reportería Financiera de Transacciones:** Motor de consulta multidimensional y generación de reportes consolidados de comisiones y transacciones con capacidades de exportación directa a formatos de hoja de cálculo (`CSV`).
2. **Tablero Analítico de Rendimiento y Ganancias en Tiempo Real:** Dashboard gerencial interactivo con cálculo automatizado de variaciones periódicas (día actual, semana y mes), series temporales para análisis visual con *Chart.js*, descomposición por par cambiario/divisa y flujo transaccional (compras vs. ventas), operando bajo políticas estrictas de control de acceso basadas en roles (RBAC).

---

## 2. Registro de Consultas Técnicas e Implementación

### 2.1. Arquitectura y Motor de Reportería de Transacciones Consolidadas

#### Contexto y Desafío Técnico
La plataforma requería una herramienta de reportería unificada que permitiera auditar y evaluar el rendimiento financiero generado a partir del spread cambiario y las comisiones recaudadas. La complejidad radicaba en permitir un filtrado dinámico multidimensional (por rango temporal de fechas, estado del ciclo de vida de la transacción, divisa negociada y tipo de flujo financiero) asegurando que el total de ganancias refleje con exactitud la suma de comisiones de transacciones formalizadas y confirmadas, desacopladas de estados transitorios.

#### Consulta Técnica Formulada (Prompt Refinado)
```text
Se requiere diseñar e implementar el módulo de reportería financiera y auditoría de transacciones 
para la plataforma Global Exchange en Django.

Requerimientos técnicos específicos:
1. Controlador de Reportería Dinámica:
   - Capacidad de filtrado por rango de fechas (fecha_desde y fecha_hasta con validación de formato),
     tipo de operación (COMPRA/VENTA), moneda asociada y estado de la operación (con valor por defecto en PAGADA).
   - Agregación ORM en base de datos para computar en un solo round-trip: suma total de comisiones recaudadas,
     conteo total de transacciones, desglose volumétrico de compras versus ventas y sus respectivas comisiones.
2. Mecanismo de Exportación a CSV:
   - Endpoint dedicado que preserve idénticamente los parámetros de consulta activos del usuario.
   - Generación de archivo bajo estándar RFC 4180 con BOM UTF-8 (utf-8-sig) para compatibilidad nativa con Microsoft Excel.
   - Inclusión de metadatos completos: ID, fecha/hora, cliente, documento, tipo, divisa, monto, tasa, subtotal, comisión, total neto, canal y operador.
3. Seguridad y Control de Acceso:
   - Restricción estricta de acceso mediante decorador de autorización RBAC para roles autorizados ('admin', 'supervisor', 'operador').
4. Interfaz de Usuario:
   - Vista standalone con diseño dark (#0f172a / #1e293b), tarjetas métricas superiores con indicadores clave,
     formulario de filtros con persistencia de estado y tabla con badges semánticos de estado y tipo.
```

#### Solución Arquitectónica e Implementación
- **Capa de Controladores (`cotizaciones/views.py`):**
  - Se estructuró la vista `reporte_transacciones` aplicando agregaciones eficientes con `django.db.models.aggregate(Sum, Count, Q)` sobre el queryset filtrado de `Operacion`, optimizando la consulta a través de `select_related('cliente', 'moneda', 'registrado_por')`.
  - Se implementó la vista `descargar_reporte_transacciones` configurada con `HttpResponse(content_type='text/csv; charset=utf-8-sig')`, permitiendo la descarga streaming de datos con nomenclatura temporal parametrizada.
- **Capa de Enrutamiento (`cotizaciones/urls.py`):**
  - Registro de las rutas `reportes/transacciones/` y `reportes/transacciones/descargar/`.
- **Capa de Presentación (`cotizaciones/templates/cotizaciones/reporte_transacciones.html`):**
  - Desarrollo de plantilla responsiva de alta fidelidad visual en paleta oscura con 4 tarjetas de métricas en cabecera, tabla de desglose transaccional, formulario de búsqueda avanzada y botón de descarga directa que propaga los filtros mediante query strings.

---

### 2.2. Tablero de Control Gerencial y Métricas de Ganancias

#### Contexto y Desafío Técnico
Para la toma de decisiones financieras y operativas, la administración requería un tablero centralizado y conciso capaz de consolidar el desempeño económico del negocio. La solución debía reflejar con claridad el total de ganancias acumuladas (comisiones de transacciones formalizadas), calcular comparativas por período (día actual, semana y mes con sus respectivas variaciones), y desglosar la procedencia del ingreso tanto por tipo de operación (compras vs. ventas) como por divisa negociada, actualizándose de forma transparente al recargar la página y bajo control de acceso reservado exclusivamente al rol de Administrador.

#### Consulta Técnica Formulada (Prompt Refinado)
```text
Diseñar la arquitectura de un Tablero de Control de Ganancias para la administración
financiera de Global Exchange en Django.

Requerimientos técnicos y funcionales:
1. Capa de Servicios y Métricas Financieras:
   - Procesamiento de operaciones confirmadas con estado PAGADA.
   - Total de Ganancias Acumuladas: suma global de comisiones y volumen transaccional histórico.
   - Comparativas por Período:
     * Día actual (hoy) vs día anterior (ayer) con cálculo de variación porcentual.
     * Semana actual (lunes a hoy) vs semana previa con variación porcentual.
     * Mes actual (mes calendario) vs mes anterior con variación porcentual.
   - Desglose por Tipo de Transacción: proporción volumétrica y recaudación entre Compras y Ventas.
   - Desglose por Moneda: tabla consolidada por divisa extranjera con comisiones totales, porcentaje de contribución, desglose de compras/ventas y volumen operado.
   - Serie Temporal: arreglo histórico de los últimos 14 días para gráfico de evolución.
2. Modo de Actualización:
   - Carga server-side directa que actualiza y computa los indicadores al recargar la página.
   - Botón directo de recarga en cabecera.
3. Control de Acceso Riguroso (RBAC):
   - Acceso exclusivo restringido a usuarios con rol 'admin'. Bloqueo con HTTP 403 para otros roles.
4. Visualización Frontend:
   - Interfaz simplificada y moderna en dark theme.
   - Gráfico de evolución temporal y gráfico donut de distribución Compras vs Ventas mediante Chart.js.
   - Enlaces contextuales (deep-linking) hacia el reporte de transacciones y ficha de operaciones.
```

#### Solución Arquitectónica e Implementación
- **Capa de Servicios de Negocio (`cotizaciones/services.py`):**
  - Implementación de la función `obtener_metricas_tablero_ganancias(dias_serie=14)`, encargada de ejecutar las agregaciones ORM, gestión de deltas de tiempo con `timezone.now()`, control de división por cero y formateo con precisión `Decimal`.
- **Capa de Controladores (`cotizaciones/views.py`):**
  - Implementación de `tablero_ganancias_view` protegida con `@rol_requerido('admin')`, serializando los conjuntos de datos requeridos por los gráficos para renderizado server-side sin latencia.
- **Capa de Enrutamiento (`cotizaciones/urls.py`):**
  - Registro de la ruta `tablero-ganancias/`.
- **Capa de Presentación (`cotizaciones/templates/cotizaciones/tablero_ganancias.html`):**
  - Plantilla limpia y sin sobrecarga: Hero card con total de ganancias acumuladas, tarjetas comparativas de períodos (Día, Semana, Mes), gráfico de evolución, gráfico donut de compras vs ventas y tabla de rendimiento por divisa, con botón de recarga rápida.
- **Navegación e Integración de Menú (`authentication/templates/authentication/menu.html`):**
  - Incorporación de la tarjeta **"Tablero de Ganancias"** en el panel de administración, habilitada para el rol `admin`.
- **Navegación Global (`templates/base.html`):**
  - Enlace **"Tablero"** en la barra superior para usuarios con rol `admin`.

---

## 3. Aseguramiento de Calidad y Pruebas Automatizadas (QA)

Para certificar la integridad de las implementaciones, se procedió a la elaboración de un conjunto de pruebas unitarias y de integración en `cotizaciones/tests.py` mediante la clase `TableroControlGananciasTestCase`.

### Aspectos Validados en la Suite de Pruebas:
1. **Verificación de Políticas RBAC:**
   - Comprobación de redirección a login ante peticiones anónimas.
   - Comprobación de rechazo con código `403 Forbidden` ante solicitudes emitidas por usuarios con rol `cliente`, `operador` o `supervisor`.
   - Comprobación de respuesta exitosa `200 OK` exclusivamente para usuarios autenticados con rol `admin`.
2. **Consistencia en el Cómputo Financiero:**
   - Validación del cálculo exacto del total de ganancias acumuladas y de las comisiones del día actual, considerando únicamente transacciones formalizadas (`PAGADA`).
   - Comprobación de métricas de semana y mes.
3. **Desglose de Tipo y Moneda:**
   - Verificación de la segregación de comisiones entre compras y ventas.
   - Verificación de la agregación de ganancias por código de divisa (`USD`, `EUR`).
4. **Actualización al Recargar la Página:**
   - Comprobación de que una nueva operación registrada impacta de forma inmediata al emitir una nueva petición GET (recarga de página).

### Resultado de Ejecución:
```text
python manage.py test cotizaciones.tests.TableroControlGananciasTestCase
Ran 4 tests in 12.492s
OK
```

---

## 4. Síntesis de Archivos Afectados

```text
cotizaciones/
├── services.py                                       # Función obtener_metricas_tablero_ganancias()
├── views.py                                          # Vistas reporte_transacciones, descargar_reporte_transacciones,
│                                                     # tablero_ganancias_view y api_tablero_ganancias
├── urls.py                                           # Enrutamiento de reportes y dashboard
├── tests.py                                          # Suite TableroControlGananciasTestCase
└── templates/cotizaciones/
    ├── reporte_transacciones.html                    # Interfaz dark del reporte y descarga CSV
    └── tablero_ganancias.html                        # Dashboard ejecutivo con Chart.js y auto-refresco
authentication/templates/authentication/
└── menu.html                                         # Enlaces de navegación con restricción RBAC
```
