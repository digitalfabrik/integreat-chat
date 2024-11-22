"""
Django settings for integreat_chat project.

Generated by 'django-admin startproject' using Django 5.0.6.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

from pathlib import Path

from langsmith import Client
from langchain_huggingface import HuggingFaceEmbeddings

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-u*mc*mu#()r6qdrotm(1=+kuo!2-*76fav*-m*m3e8v+hutfn('

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Django logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'apache': {
            'level': 'DEBUG' if DEBUG else 'INFO',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stderr',  # Logs to Apache's error log
        },
    },
    'loggers': {
        'django': {
            'handlers': ['apache'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': True,
        },
    },
}

ALLOWED_HOSTS = ["127.0.0.1", "igchat-inference.tuerantuer.org"]

INTEGREAT_CMS_DOMAIN = "cms-test.integreat-app.de"

# Configuration Variables for answer service
QUESTION_CLASSIFICATION_MODEL = "llama3.2:3b"

LANGUAGE_CLASSIFICATIONH_MODEL = "llama3.1:70b"

TRANSLATION_MODEL = "llama3.1:8b"

RAG_DISTANCE_THRESHOLD = 1.3
RAG_MAX_PAGES = 3
RAG_MODEL = "llama3.1:8b"
RAG_PROMPT = Client().pull_prompt("rlm/rag-prompt")
RAG_RELEVANCE_CHECK = True
RAG_QUERY_OPTIMIZATION = True
RAG_QUERY_OPTIMIZATION_MODEL = "llama3.1:70b"

# SEARCH_MAX_DOCUMENTS - number of documents retrieved from the VDB
SEARCH_MAX_DOCUMENTS = 15
SEARCH_DISTANCE_THRESHOLD = 1.5
SEARCH_MAX_PAGES = 10

MODEL_EMBEDDINGS = "all-MiniLM-L6-v2"
VDB_HOST = "127.0.0.1"
VDB_PORT = "19530"

EMBEDDINGS = HuggingFaceEmbeddings(model_name=MODEL_EMBEDDINGS, show_progress=False)

OLLAMA_BASE_PATH="http://10.137.0.1:11434"

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'integreat_chat.keywords',
    'integreat_chat.chatanswers',
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

ROOT_URLCONF = 'integreat_chat.core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
