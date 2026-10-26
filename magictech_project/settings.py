"""
Django settings for magictech_project project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Локальные секреты берутся из .env (файл не попадает в git), боевые значения — из окружения процесса.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BASE_DIR / '.env')

# Обязательные переменные окружения: секреты не должны иметь значений по умолчанию в коде.
for _env_var in ('DJANGO_SECRET_KEY', 'DB_NAME', 'DB_USER', 'DB_PASSWORD', 'YOOKASSA_WEBHOOK_SECRET'):
    if not os.environ.get(_env_var):
        raise RuntimeError(
            f'Установите переменную окружения {_env_var} '
            f'(локально — скопируйте .env.example в .env и заполните значения)'
        )

SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'

_ALLOWED_HOSTS_RAW = os.environ.get('DJANGO_ALLOWED_HOSTS', '').strip()
ALLOWED_HOSTS = [h.strip() for h in _ALLOWED_HOSTS_RAW.split(',') if h.strip()] if _ALLOWED_HOSTS_RAW else (['127.0.0.1'] if DEBUG else [])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'rest_framework',
    'drf_spectacular',
    'users',
    'shop',
    'panel',
    'store',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'magictech_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'panel.context_processors.panel_user',
                'store.context_processors.store_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'magictech_project.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'],
        'USER': os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 60,
        'OPTIONS': {'sslmode': os.environ.get('DB_SSL_MODE', 'prefer')},
    }
}

# Пароли — только Argon2 / bcrypt
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

# Кеш каталога
if os.environ.get('REDIS_URL'):
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': os.environ['REDIS_URL'],
            'TIMEOUT': 300,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'magictech',
            'TIMEOUT': 300,
        }
    }

# Сессии
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
CSRF_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

MAGTECH_PANEL_LOGIN_URL = '/panel/login/'

# Бизнес-параметры
MAGTECH_CART_RESERVATION_MINUTES = 20
MAGTECH_ORDER_PAYMENT_TIMEOUT_MINUTES = 30
MAGTECH_MIN_ORDER_TOTAL = 300
MAGTECH_CATALOG_PAGE_SIZE = 50
MAGTECH_CATALOG_CACHE_TTL = 300
MAGTECH_STOCK_CACHE_TTL = 0
MAGTECH_YOOKASSA_COMMISSION_PCT = 2.8
MAGTECH_YOOKASSA_WEBHOOK_SECRET = os.environ['YOOKASSA_WEBHOOK_SECRET']
MAGTECH_BACKUP_DIR = Path(os.environ.get('MAGTECH_BACKUP_DIR', BASE_DIR / 'backups'))
MAGTECH_ARCHIVE_AFTER_DAYS = 365

# Защита от перебора пароля: сколько неудачных входов с одного IP и по одному
# адресу до временной блокировки. Панель (доступ к администрированию) жёстче.
MAGTECH_LOGIN_FAIL_WINDOW_SECONDS = 900
MAGTECH_LOGIN_MAX_IP = int(os.environ.get('MAGTECH_LOGIN_MAX_IP', 20))
MAGTECH_PANEL_LOGIN_MAX_ATTEMPTS = int(os.environ.get('MAGTECH_PANEL_LOGIN_MAX_ATTEMPTS', 5))
MAGTECH_STORE_LOGIN_MAX_ATTEMPTS = int(os.environ.get('MAGTECH_STORE_LOGIN_MAX_ATTEMPTS', 10))

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['api.auth.ApiTokenAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'EXCEPTION_HANDLER': 'api.errors.audited_exception_handler',
    'UNAUTHENTICATED_USER': None,
    'DEFAULT_THROTTLE_RATES': {'anon': '30/min'},
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'MagicTech API',
    'DESCRIPTION': (
        'REST API интернет-магазина MagicTech: маркетплейсы, мобильное приложение, '
        'платёжный шлюз ЮKassa (callback), внутренняя автоматизация заказов и склада. '
        'Авторизация: заголовок `Authorization: Token <ключ>`.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'magictech': {'handlers': ['console'], 'level': 'INFO'}},
}