from datetime import timedelta
from pathlib import Path
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='', cast=Csv())


# Application definition
# django_tenants requiere que aparezca primero y que el orden se preserve.

SHARED_APPS = [
    'django_tenants',
    'tenant_users.permissions',
    'tenant_users.tenants',

    'contenedor',
    'seguridad',

    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.admin',

    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'corsheaders',
]

# django.contrib.contenttypes NO va acá: debe existir una sola django_content_type,
# la del schema público. Si cada tenant tiene la suya, sus ids no coinciden con los
# de public.auth_permission (que es compartida) y el JOIN que resuelve los permisos
# cruza filas equivocadas, perdiendo permisos sin dar ningún error.
TENANT_APPS = [
    'tenant_users.permissions',
    'general',
    'contabilidad',
    'turno',
    'humano',
    'inventario',
]

INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

TENANT_MODEL = 'contenedor.CtnCliente'
TENANT_DOMAIN_MODEL = 'contenedor.CtnDominio'

DATABASE_ROUTERS = ['django_tenants.routers.TenantSyncRouter']

AUTH_USER_MODEL = 'seguridad.SegUsuario'

# TenantHeaderMiddleware DEBE ir primero para resolver el schema por header X-Tenant.
#
# La vigencia de la suscripción NO se valida acá: los middlewares corren antes de
# que DRF autentique, así que un anónimo podía leer el estado de suscripción de
# cualquier contenedor con solo mandar su nombre en X-Tenant. La comprobación
# vive en `seguridad.permissions.SuscripcionVigente`, que va en
# DEFAULT_PERMISSION_CLASSES y ya corre con el usuario resuelto.
MIDDLEWARE = [
    'seguridad.middleware.TenantHeaderMiddleware',
    'seguridad.middleware.UsuarioActualMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'torioapp.urls_tenant'
PUBLIC_SCHEMA_URLCONF = 'torioapp.urls_public'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'torioapp.wsgi.application'
ASGI_APPLICATION = 'torioapp.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': config('DATABASE_NAME'),
        'USER': config('DATABASE_USER'),
        'PASSWORD': config('DATABASE_CLAVE'),
        'HOST': config('DATABASE_HOST'),
        'PORT': config('DATABASE_PORT'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'seguridad.authentication.SegCookieJWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'seguridad.permissions.EsMiembroDelTenant',
        'seguridad.permissions.SuscripcionVigente',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '1000/min',
        'login': '5/min',
        'refresh': '20/min',
        'registro': '5/hour',
        'recuperar_clave': '3/min',
        'restablecer_clave': '5/min',
        'importar': '10/hour',
        'mfa_verificar': '10/min',
        'mfa_gestion': '10/hour',
        'mfa_envio_codigo': '3/min',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}


# Hay dos schemas, uno por urlconf: el público (login, MFA, contenedor) y el de
# tenant. Se montan en `urls_public.py` y `urls_tenant.py` pasando `urlconf`
# explícito, porque el generador lee `ROOT_URLCONF` e ignora el `request.urlconf`
# que pone TenantHeaderMiddleware: sin eso ambas URLs servían el mismo schema de
# tenant y el login quedaba sin documentar.
SPECTACULAR_SETTINGS = {
    'TITLE': 'Torio API',
    'DESCRIPTION': 'API multi-tenant del ERP Torio',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    },
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.hooks.postprocess_schema_enums',
        'utilidades.openapi.agregar_header_tenant',
        'utilidades.openapi.agrupar_tags_por_app',
    ],
}


# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': config('LOG_LEVEL', default='INFO'),
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': config('DJANGO_LOG_LEVEL', default='INFO'),
            'propagate': False,
        },
    },
}


SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# Tope absoluto de la sesión, contado desde el login y no desde el último uso.
# REFRESH_TOKEN_LIFETIME no lo cubre: la rotación llama a `set_exp()` y corre el
# vencimiento, así que una sesión en uso continuo no caducaría nunca. Cada 30 días toda
# sesión vuelve a pasar por /login/, que es el único punto donde se verifica el MFA.
# Alineado con la cookie de dispositivo recordado, para que al usuario legítimo ese
# re-login no le pida código.
SESION_MAXIMA = timedelta(days=config('SESION_MAXIMA_DIAS', default=30, cast=int))

from corsheaders.defaults import default_headers

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    'https://reddoc.uk',
    'https://www.reddoc.uk',
    'http://localhost:4200',
    'http://127.0.0.1:4200',
]
CORS_ALLOW_HEADERS = list(default_headers) + ['x-tenant']

BACKEND_URL = config('BACKEND_URL', default='http://localhost:8000')
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:4200')
FRONTEND_CUENTA_URL = config('FRONTEND_CUENTA_URL', default='http://localhost:4200')
ZINC_URL = config('ZINC_URL', default='http://localhost:3000')
TENANT_BASE_DOMAIN = config('TENANT_BASE_DOMAIN', default='localhost')
AUTH_COOKIE_DOMAIN = config('AUTH_COOKIE_DOMAIN', default=None)
AUTH_COOKIE_SECURE = config('AUTH_COOKIE_SECURE', default=not DEBUG, cast=bool)
ENABLE_API_DOCS = config('ENABLE_API_DOCS', default=False, cast=bool)

# Solo en True si hay un proxy inverso adelante (nginx, Cloudflare) que reescriba
# X-Forwarded-For. Expuesto directo, ese header lo pone el cliente y permitiría
# falsear la IP que queda en la bitácora de accesos y en los desafíos MFA.
CONFIAR_EN_PROXY = config('CONFIAR_EN_PROXY', default=False, cast=bool)

TURNSTILE_SECRET_KEY = config('TURNSTILE_SECRET_KEY', default='')
TURNSTILE_ENABLED = config('TURNSTILE_ENABLED', default=True, cast=bool)

# MFA. Clave Fernet propia, deliberadamente separada de SECRET_KEY: así se puede rotar
# la firma de los JWT sin invalidar el segundo factor de todos los usuarios. Generarla
# con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
MFA_ENCRYPTION_KEY = config('MFA_ENCRYPTION_KEY', default='')

# Wompi
WOMPI_EVENTS_SECRET = config('WOMPI_EVENTS_SECRET', default='')
WOMPI_INTEGRITY_SECRET = config('WOMPI_INTEGRITY_SECRET', default='')

# RedEDoc (servicio Nobelio, api.rededoc.uk). La llave se lee de KEY_REDEDOC,
# que es como quedó nombrada la variable en los .env ya desplegados.
REDEDOC_URL = config('REDEDOC_URL', default='https://api.rededoc.uk')
REDEDOC_KEY = config('KEY_REDEDOC', default='')

# Backblaze B2
B2_KEY_ID = config('B2_KEY_ID', default='')
B2_APP_KEY = config('B2_APP_KEY', default='')
# El bucket público tiene su propia application key: cada una está restringida
# a su bucket, así que no son intercambiables.
B2_KEY_ID_PUBLICO = config('B2_KEY_ID_PUBLICO', default='')
B2_APP_KEY_PUBLICO = config('B2_APP_KEY_PUBLICO', default='')
B2_ENDPOINT_URL = config('B2_ENDPOINT_URL', default='')
B2_BUCKET_PUBLICO = config('B2_BUCKET_PUBLICO', default='')
B2_BUCKET_PRIVADO = config('B2_BUCKET_PRIVADO', default='')
B2_CDN_URL_PUBLICO = config('B2_CDN_URL_PUBLICO', default='')


# Sentry (control de errores).
# Solo se activa si SENTRY_DSN está definido, así dev queda intacto y se enciende
# en prod/staging con solo setear la variable. La integración con Django se
# auto-activa. El schema del tenant se etiqueta por request en TenantHeaderMiddleware.
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=config('SENTRY_ENVIRONMENT', default=config('ENV', default='production')),
        release=config('SENTRY_RELEASE', default=None) or None,
        # Performance: 0.0 = solo errores (sin coste de trazas). Subir gradualmente.
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.0, cast=float),
        profiles_sample_rate=config('SENTRY_PROFILES_SAMPLE_RATE', default=0.0, cast=float),
        # PII desactivada por defecto: no envía cookies (JWT), headers ni datos de usuario.
        send_default_pii=config('SENTRY_SEND_PII', default=False, cast=bool),
    )
