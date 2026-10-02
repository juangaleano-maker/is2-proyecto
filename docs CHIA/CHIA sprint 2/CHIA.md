# CHIA - Documentación de Conversaciones y Asistencia de Inteligencia Artificial

**Proyecto:** Global Exchange - Casa de Cambios  
**Asignatura:** Ingeniería de Software 2 (FPUNA)  
**Semestre / Período:** 7mo Semestre - 2do Período 2026  
**Hito:** Hito 4 - Sprint 2 del Desarrollo de Software  
**Herramienta de IA utilizada:** Antigravity IDE (Claude Sonnet 4.6 / Gemini)

---

## 1. Introducción y Propósito

El presente documento recopila y sintetiza las interacciones, solicitudes (*prompts*), análisis arquitectónicos, decisiones técnicas y resoluciones de código generadas en conjunto con el Asistente de Inteligencia Artificial durante el ciclo de vida del **Sprint 2 (Hito 4)** del proyecto *Global Exchange*.

El objetivo es evidenciar el uso de la IA como herramienta de apoyo al desarrollo (*Pair Programming*), asegurando la trazabilidad de los requerimientos, la calidad del código y el cumplimiento de los criterios de aceptación definidos por las historias de usuario.

---

## 2. Resumen de Temas y Alcance Abordados con la IA

| Módulo / Área | Tareas e Iteraciones con la IA | Resultado Implementado |
| :--- | :--- | :--- |
| **CRUD de Medios de Pago** | Implementación completa de las cuatro historias de usuario: Agregar, Modificar, Consultar y Eliminar medios de pago, con validaciones de negocio. | Módulo integrado en `clientes/` con modelo `MedioDePago`, formularios, vistas, URLs y templates. |
| **Validación de Transacciones Pendientes** | Diseño de la lógica de bloqueo/advertencia ante transacciones pendientes, con implementación simulada desacoplada del módulo de transacciones. | Función de simulación `random.choice([True, False])` preparada para ser reemplazada en el siguiente sprint. |
| **Integración de Navegación** | Conexión del módulo de medios de pago al sistema de navegación global: navbar, menú principal, ficha de cliente. | `base.html`, `menu.html` y `detalle.html` actualizados con accesos contextuales al cliente activo. |
| **Gestión de Ramas Git** | Resolución de problema de rama sin tracking remoto (`feature/IS2-40`) al intentar hacer `git pull`. | Rama linkeada a `origin/feature/IS2-40` y actualizada via fast-forward. |

---

## 3. Registro Cronológico de Prompts y Resoluciones

### 3.1. HU — Agregar Medio de Pago (IS2-47)

- **Historia de Usuario:**  
  *Como cliente, quiero registrar un medio de pago para usarlo en mis transacciones.*

- **Criterios de Aceptación implementados:**
  - **CA1:** Dado que hay un cliente activo en sesión y los datos son completos y válidos, cuando el usuario confirma, el medio de pago queda registrado con `activo=True`.
  - **CA2:** Dado que no hay un `cliente_activo_id` en `request.session`, el sistema deniega el acceso con un mensaje de error y redirige al menú.
  - **CA3:** Dado que el formulario contiene datos incompletos o inválidos (ej. falta `entidad` para Tarjeta de Crédito), el sistema renderiza el formulario con los errores de validación.

- **Decisiones de Diseño tomadas con la IA:**
  - Se definieron tres tipos de medio de pago: `TARJETA_CREDITO`, `TRANSFERENCIA` y `EFECTIVO`, modelados como `TextChoices` en el propio modelo.
  - Los campos `entidad`, `numero` y `titular` son opcionales en el modelo (`blank=True, null=True`), pero el formulario `MedioDePagoForm` los requiere condicionalmente si el tipo es distinto de `EFECTIVO`, mediante validación en el método `clean()`.
  - La asociación al cliente se realiza en la vista (`medio_pago.cliente = cliente`) y no en el formulario, para mantener el formulario desacoplado del contexto de sesión.

- **Artefactos Generados:**

  | Archivo | Cambio |
  |---|---|
  | `clientes/models.py` | Nuevo modelo `MedioDePago` con FK a `Cliente`, `TipoMedio.choices`, campos opcionales y `__str__` contextual. |
  | `clientes/forms.py` | Nuevo formulario `MedioDePagoForm` con validación condicional según tipo. |
  | `clientes/views.py` | Nueva vista `agregar_medio_pago`. Verifica sesión, instancia el formulario y persiste. |
  | `clientes/urls.py` | Ruta `medios-pago/agregar/` → name `agregar_medio_pago`. |
  | `clientes/templates/clientes/medio_pago_form.html` | Formulario con ocultamiento dinámico de campos mediante JavaScript nativo según tipo seleccionado. |
  | `clientes/migrations/0003_mediodepago.py` | Migración generada y aplicada (`python manage.py makemigrations && migrate`). |

---

### 3.2. HU — Modificar Medio de Pago (IS2-48)

- **Historia de Usuario:**  
  *Como cliente, quiero editar los datos de un medio de pago registrado.*

- **Criterios de Aceptación implementados:**
  - **CA1:** Dado que el usuario edita un medio de pago del cliente activo y los datos son válidos, cuando confirma, los cambios se persisten correctamente.
  - **CA2:** Dado que el medio de pago tiene transacciones pendientes asociadas (simulado), cuando el usuario intenta guardar, el sistema renderiza el formulario con una alerta de advertencia y requiere confirmación explícita mediante checkbox antes de persistir el cambio.

- **Decisiones de Diseño tomadas con la IA:**
  - El formulario `medio_pago_form.html` fue refactorizado para ser **reutilizable** tanto en alta como en modificación. El atributo `action=""` del `<form>` delega la URL al contexto de la solicitud actual, eliminando la necesidad de un template separado.
  - La verificación de pertenencia del medio de pago al cliente activo se realiza mediante `get_object_or_404(MedioDePago, pk=pk, cliente_id=cliente_activo_id)`, garantizando que un cliente no pueda editar medios de pago de terceros.
  - La validación de transacciones pendientes se implementó como una función simulada (`random.choice([True, False])`) con comentario explícito de sustitución futura.
  - El flujo de confirmación opera en dos pasos en el mismo endpoint POST: 1) si el formulario es válido pero hay transacciones y no hay `confirmacion_transacciones=true` en el POST, se recarga con `advertencia_transacciones=True`; 2) si la confirmación está presente, se persisten los cambios.

- **Artefactos Generados:**

  | Archivo | Cambio |
  |---|---|
  | `clientes/views.py` | Nueva vista `editar_medio_pago`. Lógica de verificación de pertenencia, simulación de transacciones y confirmación en dos fases. |
  | `clientes/urls.py` | Ruta `medios-pago/<int:pk>/editar/` → name `editar_medio_pago`. |
  | `clientes/templates/clientes/medio_pago_form.html` | Bloque `{% if advertencia_transacciones %}` con alerta Bootstrap y checkbox de confirmación obligatorio. |

---

### 3.3. HU — Consultar Medios de Pago (IS2-49)

- **Historia de Usuario:**  
  *Como cliente, quiero ver todos mis medios de pago registrados.*

- **Criterios de Aceptación implementados:**
  - **CA1:** Dado que el cliente activo tiene medios de pago registrados, cuando accede a `/clientes/medios-pago/`, el sistema lista todas las instancias mostrando: tipo, entidad, número, titular y estado (`activo`/`inactivo`).
  - **CA2 (implícito):** Dado que el cliente no tiene medios registrados, el sistema muestra un estado vacío con un call-to-action para registrar el primero.

- **Decisiones de Diseño tomadas con la IA:**
  - Los medios de pago se filtran exclusivamente por el `cliente_activo_id` de sesión, sin exposición de registros de otros clientes.
  - El template utiliza tarjetas (`card`) con codificación de color por tipo de medio: celeste para Tarjeta de Crédito (`bg-info`), azul para Transferencia (`bg-primary`), gris para Efectivo (`bg-secondary`).
  - Los campos `entidad`, `numero` y `titular` se omiten en la vista de tipo `EFECTIVO`, mostrando un placeholder textual.
  - Las acciones **Editar** y **Eliminar** se incluyen inline en cada tarjeta, con el botón de Eliminar condicionado a `mp.activo`.

- **Artefactos Generados:**

  | Archivo | Cambio |
  |---|---|
  | `clientes/views.py` | Nueva vista `listar_medios_pago`. Filtra por `cliente_activo_id`. |
  | `clientes/urls.py` | Ruta `medios-pago/` → name `listar_medios_pago`. |
  | `clientes/templates/clientes/medio_pago_list.html` | Template de listado con grid de tarjetas, indicadores de estado y acciones inline. |

---

### 3.4. HU — Eliminar Medio de Pago (IS2-48)

- **Historia de Usuario:**  
  *Como cliente, quiero eliminar/inactivar un medio de pago que ya no utilizo.*

- **Criterios de Aceptación implementados:**
  - **CA1:** Dado que el medio de pago **no** tiene transacciones pendientes, cuando el usuario confirma la eliminación en la pantalla de confirmación (POST), el sistema realiza una **baja lógica** (`activo=False`) y redirige al listado.
  - **CA2:** Dado que el medio de pago **sí** tiene transacciones pendientes (simulado), cuando el usuario accede a la pantalla de confirmación, el sistema muestra el **bloqueo total** de la operación: no se presenta botón de confirmación y se muestra el motivo del impedimento.

- **Decisiones de Diseño tomadas con la IA:**
  - Se implementó **baja lógica** (en consistencia con el modelo `Cliente`) en lugar de eliminación física, preservando la integridad del historial.
  - La diferenciación entre los dos criterios de aceptación se resuelve en el template `medio_pago_eliminar.html` con un bloque `{% if tiene_transacciones %}`: si es verdadero, se renderiza solo el mensaje de bloqueo; si es falso, se renderiza el formulario de confirmación.
  - La vista evalúa el estado `activo` antes de procesar: si el medio ya está inactivo, redirige con un aviso (`messages.warning`), evitando doble procesamiento.

- **Artefactos Generados:**

  | Archivo | Cambio |
  |---|---|
  | `clientes/views.py` | Nueva vista `eliminar_medio_pago`. Verifica pertenencia, simula transacciones, ejecuta baja lógica en POST. |
  | `clientes/urls.py` | Ruta `medios-pago/<int:pk>/eliminar/` → name `eliminar_medio_pago`. |
  | `clientes/templates/clientes/medio_pago_eliminar.html` | Pantalla de confirmación con bifurcación según `tiene_transacciones`: bloqueo total o formulario de baja. |
  | `clientes/templates/clientes/medio_pago_list.html` | Botón "Eliminar" agregado a cada tarjeta activa con enlace a la ruta `eliminar_medio_pago`. |

---

### 3.5. Integración de Navegación Global del Módulo

- **Contexto / Problema:** Las cuatro HU de medios de pago estaban implementadas a nivel de lógica y rutas, pero no conectadas al sistema de navegación existente (navbar, menú principal, ficha del cliente).

- **Prompt del Usuario:**  
  > *"ahora quiero que conectes todo (panel, endpoints, redirecciones, etc) para que funcione de forma integra y simple"*

- **Análisis de la IA:**  
  Se auditó la estructura existente de templates (`base.html`, `menu.html`, `detalle.html`, `seleccionar.html`) y las vistas relacionadas para identificar todos los puntos de entrada que debían exponer acceso al módulo de medios de pago.

- **Cambios de Integración Aplicados:**

  | Punto de Integración | Cambio Aplicado |
  |---|---|
  | **Navbar (`base.html`)** | Se agregó el enlace "💳 Medios de Pago" → `clientes:listar_medios_pago`, visible condicionalmente solo cuando `request.session.cliente_activo_nombre` está definido. |
  | **Menú Principal (`menu.html`)** | Se agregó una card "Mis Medios de Pago" en la sección de "Operaciones Disponibles", protegida por el bloque `{% if tiene_cliente %}`, con enlace directo al listado. |
  | **Ficha del Cliente (`detalle.html`)** | Se agregó una sección inline con el listado resumido de medios de pago del cliente activo, incluyendo botones de acción Editar y Eliminar por ítem. |
  | **Vista `detalle_cliente` (`views.py`)** | Se modificó para inyectar `medios_pago` al contexto cuando el `pk` del cliente solicitado coincide con el `cliente_activo_id` de la sesión; caso contrario pasa `None` y la sección no se renderiza. |

- **Verificación:**  
  Se ejecutó `python manage.py check` con resultado **0 errores**. Los warnings reportados (`AutoField` y namespace de usuarios) son preexistentes y no críticos.

---

### 3.6. Resolución de Problema de Tracking en Rama Git

- **Contexto / Problema:** Al intentar hacer checkout a `feature/IS2-40` para obtener los últimos cambios del remoto, el comando falló en dos fases: primero `git checkout feature/IS2-40` reportó `pathspec did not match`, y tras crear la rama localmente con `git branch feature/IS2-40`, el `git pull` falló con `There is no tracking information for the current branch`.

- **Prompt del Usuario:**  
  > *(Compartió el buffer del terminal con los errores de git)*

- **Análisis de la IA:**  
  La rama `feature/IS2-40` fue creada localmente desde `develop` sin haber hecho `git fetch` previo (la referencia remota `origin/feature/IS2-40` no existía localmente). Al ejecutar `git pull` sin upstream definido, Git no sabe a qué rama remota apuntar.

- **Solución Aplicada:**
  ```bash
  git branch --set-upstream-to=origin/feature/IS2-40 feature/IS2-40
  git pull
  ```
  El pull completó exitosamente en modo **fast-forward** (de `1aafe94` a `424144c`), incorporando 16 nuevos archivos del módulo `monedas` desarrollado por otro integrante del equipo.

---

## 4. Buenas Prácticas y Metodología Aplicada

1. **Separación de Responsabilidades:** La lógica de autorización (verificación de cliente activo en sesión) se centraliza en cada vista, manteniendo los formularios desacoplados del contexto de sesión.
2. **Baja Lógica Consistente:** El modelo `MedioDePago` implementa el mismo patrón de `activo=BooleanField` que el modelo `Cliente`, preservando la integridad histórica del sistema.
3. **Extensibilidad Planificada:** La simulación de transacciones pendientes está explícitamente marcada en el código como provisional, facilitando su sustitución con la lógica real en el sprint siguiente sin necesidad de refactorización mayor.
4. **Reutilización de Templates:** El formulario `medio_pago_form.html` sirve tanto para alta como para modificación, reduciendo la duplicación de código de presentación.
5. **GitFlow con Feature Branches:** Cada historia de usuario fue implementada en su rama feature correspondiente (`feature/IS2-47`, `feature/IS2-48`, `feature/IS2-49`) con commits atómicos y push al remoto.

---

## 5. Distribución del Trabajo por Integrante

**Módulo CRUD Medios de Pago (IS2-47, IS2-48, IS2-49)**

- Modelado del `MedioDePago` con tipos de medio (`TARJETA_CREDITO`, `TRANSFERENCIA`, `EFECTIVO`).
- Implementación de las cuatro vistas CRUD con validación de sesión y reglas de negocio.
- Formulario con validación condicional por tipo de medio.
- Templates con interacción dinámica (JavaScript nativo).
- Integración de navegación global en navbar, menú y ficha de cliente.
- Simulación de validación de transacciones pendientes preparada para sustitución futura.

**Transversal (para todos)**

- Pruebas unitarias (PUN) de su módulo.
- Documentación automática de código (PDO) con Sphinx.
- Feature branches con GitFlow y PR correspondientes.
- Registro de conversaciones con IA (CHIA) en `/docs CHIA/`.

---

## 6. Documentación de Funcionalidades — Módulo `MedioDePago`

### 6.1. Modelo `MedioDePago`

**Ubicación:** `clientes/models.py`

**Funcionalidad:** Representa un instrumento financiero registrado a nombre de un cliente. Implementa baja lógica con el campo `activo`.

**Campos:**

| Campo | Tipo | Restricciones |
|---|---|---|
| `cliente` | `ForeignKey(Cliente)` | `on_delete=CASCADE`, `related_name='medios_de_pago'` |
| `tipo` | `CharField` | `choices=TipoMedio.choices` — `TARJETA_CREDITO`, `TRANSFERENCIA`, `EFECTIVO` |
| `entidad` | `CharField(100)` | `blank=True, null=True` |
| `numero` | `CharField(50)` | `blank=True, null=True` |
| `titular` | `CharField(150)` | `blank=True, null=True` |
| `activo` | `BooleanField` | `default=True` |
| `creado_en` | `DateTimeField` | `auto_now_add=True` |
| `actualizado_en` | `DateTimeField` | `auto_now=True` |

**`__str__`:** Retorna `"Efectivo - <cliente>"` para tipo EFECTIVO, o `"<tipo_display> - <entidad> - <numero>"` para los demás.

---

### 6.2. Formulario `MedioDePagoForm`

**Ubicación:** `clientes/forms.py`

**Validación condicional en `clean()`:** Si `tipo` es `TARJETA_CREDITO` o `TRANSFERENCIA`, los campos `entidad`, `numero` y `titular` son obligatorios. Para `EFECTIVO`, no se validan.

---

### 6.3. Vistas del Módulo

| Vista | URL | Descripción |
|---|---|---|
| `agregar_medio_pago` | `GET/POST medios-pago/agregar/` | Alta de nuevo medio de pago asociado al cliente activo en sesión. |
| `editar_medio_pago` | `GET/POST medios-pago/<pk>/editar/` | Edición de medio de pago propio. Incluye flujo de confirmación ante transacciones pendientes. |
| `listar_medios_pago` | `GET medios-pago/` | Listado de todos los medios de pago del cliente activo con estado e información principal. |
| `eliminar_medio_pago` | `GET/POST medios-pago/<pk>/eliminar/` | Baja lógica con pantalla de confirmación. Bloqueo total si hay transacciones pendientes. |

**Control de acceso común:** Todas las vistas verifican `request.session.get('cliente_activo_id')`. Si no existe, redirigen a `menu` con `messages.error`.

---

## 7. Herramientas y Recursos Utilizados

| Recurso | Uso en el proyecto |
|---|---|
| Antigravity IDE (IA) | Pair programming para arquitectura de modelo, validaciones de formulario, lógica de vistas, templates y resolución de problemas Git |
| Django Documentation | Referencia de modelos, vistas basadas en funciones, sistema de mensajes y sesiones |
| Bootstrap 5 | Componentes UI: cards, alerts, badges, botones en los templates de medios de pago |

---
