#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def ensure_db_exists():
    """Ensure the target PostgreSQL database exists before executing commands."""
    try:
        from global_exchange.settings import DATABASES
        db = DATABASES.get('default', {})
        if db.get('ENGINE') == 'django.db.backends.postgresql':
            db_name = db.get('NAME')
            user = db.get('USER', 'postgres')
            password = db.get('PASSWORD', '')
            host = db.get('HOST', '127.0.0.1')
            port = db.get('PORT', '5432')

            if not db_name:
                return

            try:
                import psycopg2
                from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
                try:
                    conn = psycopg2.connect(dbname=db_name, user=user, password=password, host=host, port=port, connect_timeout=3)
                    conn.close()
                except Exception:
                    try:
                        conn = psycopg2.connect(dbname='postgres', user=user, password=password, host=host, port=port, connect_timeout=3)
                        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                        cur = conn.cursor()
                        cur.execute(f'CREATE DATABASE "{db_name}";')
                        cur.close()
                        conn.close()
                    except Exception:
                        pass
            except ImportError:
                try:
                    # pyrefly: ignore [missing-import]
                    import psycopg
                    try:
                        conn = psycopg.connect(dbname=db_name, user=user, password=password, host=host, port=port, connect_timeout=3)
                        conn.close()
                    except Exception:
                        try:
                            conn = psycopg.connect(dbname='postgres', user=user, password=password, host=host, port=port, autocommit=True, connect_timeout=3)
                            cur = conn.cursor()
                            cur.execute(f'CREATE DATABASE "{db_name}";')
                            cur.close()
                            conn.close()
                        except Exception:
                            pass
                except ImportError:
                    pass
    except Exception:
        pass


def ejecutar_tests_previos():
    """
    Ejecuta las pruebas unitarias de todas las aplicaciones antes de iniciar runserver (estilo Maven).
    Solo se ejecuta una vez al inicio del comando y no en cada recarga automática de archivos.
    """
    import subprocess
    print("\n" + "=" * 72)
    print(">>> [BUILD] Ejecutando suite de pruebas unitarias antes de levantar el servidor...")
    print("=" * 72)

    apps_to_test = ['authentication', 'clientes', 'cotizaciones', 'monedas', 'pagos', 'usuarios', 'agregar_usuario']
    cmd = [sys.executable, 'manage.py', 'test'] + apps_to_test
    resultado = subprocess.run(cmd)

    if resultado.returncode != 0:
        print("\n" + "=" * 72)
        print(">>> [BUILD FAILURE] Las pruebas unitarias no pasaron. El servidor no se iniciara.")
        print("=" * 72 + "\n")
        sys.exit(resultado.returncode)

    print("\n" + "=" * 72)
    print(">>> [BUILD SUCCESS] Todos los tests pasaron exitosamente. Iniciando servidor...")
    print("=" * 72 + "\n")


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'global_exchange.settings')
    ensure_db_exists()

    # Opciones para omitir pruebas si se requiere inicio inmediato (--no-test o SKIP_TESTS=1 o --help)
    skip_tests = any(h in sys.argv for h in ['-h', '--help'])
    for flag in ['--no-test', '--no-tests', '--skip-test', '--skip-tests']:
        if flag in sys.argv:
            sys.argv.remove(flag)
            skip_tests = True

    if os.environ.get('SKIP_TESTS') == '1':
        skip_tests = True

    # Estilo Maven: ejecutar tests antes de runserver (únicamente en el arranque inicial, no en cada recarga de archivos)
    if 'runserver' in sys.argv and not skip_tests and os.environ.get('RUN_MAIN') != 'true':
        ejecutar_tests_previos()

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()

