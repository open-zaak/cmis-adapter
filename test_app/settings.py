import os

PROJECT_DIR = os.path.dirname(__file__)
BASE_DIR = PROJECT_DIR  # setting present in new startproject

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

SITE_ID = 1

IS_HTTPS = False

USE_TZ = True
TIME_ZONE = "UTC"

INSTALLED_APPS = [
    "vng_api_common",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "drc_cmis",
    "test_app.app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "test_app.urls"

DEBUG = True
SECRET_KEY = "this-is-really-not-a-secret"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

STATIC_URL = "/static/"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(PROJECT_DIR, "database.db"),
    },
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "DIRS": [os.path.join(PROJECT_DIR, "templates"),],
        "OPTIONS": {
            "debug": DEBUG,
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.media",
            ],
        },
    },
]

CMIS_MAPPER_FILE = os.path.join(PROJECT_DIR, "cmis_mapper.json")
