import os
from pathlib import Path

import dj_database_url
from django.templatetags.static import static

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes")


SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])
CSRF_TRUSTED_ORIGINS = [f"https://*{h}" if h.startswith(".") else f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]

INSTALLED_APPS = [
    "unfold",  # admin panel theme; must come before django.contrib.admin
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600
    )
}

LANGUAGE_CODE = "uz"
# Uzbek labels for the admin theme, which ships without them.
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Telegram bot
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# Hour (local time) when the day closes and daily PDFs are sent.
DAY_CLOSE_HOUR = int(os.environ.get("DAY_CLOSE_HOUR", "21"))
# Hour when workers who have not entered anything get a reminder.
REMINDER_HOUR = int(os.environ.get("REMINDER_HOUR", "18"))
MAX_QUANTITY = int(os.environ.get("MAX_QUANTITY", "5000"))

# Print errors (with tracebacks) to the console so they show up in the host's logs.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# Managers sign in to their own pages under /sardor/; the boss uses /admin/.
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"

# Admin panel look (django-unfold). Colours are indigo; labels are in Uzbek.
UNFOLD = {
    "SITE_TITLE": "Ishxona",
    "SITE_HEADER": "Ishxona",
    "SITE_SUBHEADER": "Tikuv ishxonasi boshqaruvi",
    "SITE_SYMBOL": "content_cut",
    "SITE_URL": "/sardor/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "DASHBOARD_CALLBACK": "core.dashboard.dashboard_callback",
    "LOGIN": {"image": lambda request: static("ishxona/login.svg")},
    "COLORS": {
        "primary": {
            "50": "oklch(96.2% .018 272.314)",
            "100": "oklch(93% .034 272.788)",
            "200": "oklch(87% .065 274.039)",
            "300": "oklch(78.5% .115 274.713)",
            "400": "oklch(67.3% .182 276.935)",
            "500": "oklch(58.5% .233 277.117)",
            "600": "oklch(51.1% .262 276.966)",
            "700": "oklch(45.7% .24 277.023)",
            "800": "oklch(39.8% .195 277.366)",
            "900": "oklch(35.9% .144 278.697)",
            "950": "oklch(25.7% .09 281.288)",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "items": [
                    {"title": "Bosh sahifa", "icon": "space_dashboard", "link": "/admin/"},
                ],
            },
            {
                "title": "Ishlab chiqarish",
                "separator": True,
                "items": [
                    {
                        "title": "Zakazlar",
                        "icon": "assignment",
                        "link": "/admin/core/order/",
                        "badge": "core.dashboard.open_orders_badge",
                    },
                    {
                        "title": "Ish yozuvlari",
                        "icon": "fact_check",
                        "link": "/admin/core/workentry/",
                        "badge": "core.dashboard.pending_badge",
                    },
                    {"title": "Tahrirlar jurnali", "icon": "edit_note", "link": "/admin/core/entryedit/"},
                ],
            },
            {
                "title": "Odamlar",
                "separator": True,
                "items": [
                    {"title": "Xodimlar", "icon": "badge", "link": "/admin/core/employee/"},
                    {"title": "Guruhlar", "icon": "groups", "link": "/admin/core/team/"},
                    {"title": "Ishchi turlari", "icon": "engineering", "link": "/admin/core/workertype/"},
                ],
            },
            {
                "title": "Mahsulotlar",
                "separator": True,
                "items": [
                    {"title": "Mahsulotlar", "icon": "checkroom", "link": "/admin/core/product/"},
                    {"title": "Qismlar", "icon": "content_cut", "link": "/admin/core/operation/"},
                    {"title": "Narx tarixi", "icon": "history", "link": "/admin/core/pricehistory/"},
                ],
            },
        ],
    },
}
