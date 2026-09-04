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


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'global_exchange.settings')
    ensure_db_exists()
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

