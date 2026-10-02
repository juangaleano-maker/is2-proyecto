# Global Exchange - Setup & Pruebas Unitarias

## Configuración del Entorno Local

Para el desarrollo local y la ejecución de las pruebas unitarias (tests) del proyecto, es **estrictamente necesario utilizar Python 3.12 o Python 3.13**. 
Actualmente, Django 5.1 presenta incompatibilidades con **Python 3.14** (específicamente un error `AttributeError: 'super' object has no attribute 'dicts'` en `django/template/context.py` relacionado con el método `copy()`).

### Pasos para configurar el entorno local:

1. **Instalar Python 3.12 o 3.13**:
   Asegúrate de tener instalada una de estas versiones en tu sistema. Puedes descargarlas desde [python.org](https://www.python.org/downloads/).

2. **Crear un entorno virtual**:
   Utiliza la versión correcta de Python para crear tu entorno virtual.
   ```bash
   # En Windows
   py -3.12 -m venv .venv312
   
   # Activar el entorno
   .venv312\Scripts\activate
   ```

3. **Instalar las dependencias**:
   Con el entorno virtual activado, instala los requerimientos del proyecto:
   ```bash
   pip install -r requirements.txt
   ```

4. **Ejecutar las Pruebas Unitarias**:
   Ahora puedes ejecutar los tests localmente sin problemas de incompatibilidad:
   ```bash
   python manage.py test
   ```

**Nota sobre Docker:**
El entorno contenerizado (`docker-compose.yml`) utiliza la imagen oficial `python:3.12-slim-bullseye`, por lo que los comandos ejecutados dentro del contenedor (incluyendo los tests) ya operan bajo Python 3.12 de forma segura.
