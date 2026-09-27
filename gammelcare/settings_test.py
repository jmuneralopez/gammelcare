"""Settings para correr la suite de pruebas (pytest-django) sin depender de
Postgres real ni de las credenciales de .env: base de datos SQLite en
memoria y una llave Fernet generada en caliente, exclusiva para cada
corrida (no hay datos previos que descifrar en una base de datos que se
crea y se destruye en el mismo proceso).

Ver claude/plan-salida-produccion.md, Fase 1C item 24: la Compuerta A
exige una suite de pruebas en verde antes de abrir el piloto.

Uso: pytest (ya lo toma de pytest.ini) o
     python manage.py test --settings=gammelcare.settings_test
"""
import os

# Se definen ANTES de importar settings.py para que decouple los use en
# vez de exigir un .env real o las credenciales de producción.
os.environ.setdefault('SECRET_KEY', 'clave-de-pruebas-no-usar-en-produccion')
os.environ.setdefault('DEBUG', 'False')
os.environ.setdefault('DB_NAME', 'gammelcare_test')
os.environ.setdefault('DB_USER', 'test')
os.environ.setdefault('DB_PASSWORD', 'test')
os.environ.setdefault('FERNET_KEY', 'sera-reemplazada-abajo-por-una-real')

from .settings import *  # noqa: F401,F403

from cryptography.fernet import Fernet

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Llave Fernet válida generada para esta corrida — no persiste entre
# corridas, y no hace falta que persista: la base de datos tampoco.
FERNET_KEY = Fernet.generate_key().decode()

# Los tests no necesitan un hash de contraseña costoso.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

DEBUG = False
