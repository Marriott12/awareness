"""
Production settings example - keep secrets and host configuration out of source control.

This file is intended as a template. In production set the following environment variables:
- AWARENESS_SECRET_KEY
- AWARENESS_ALLOWED_HOSTS (comma separated)
- DATABASE_URL (optional, e.g. postgres://...)

Do NOT commit secrets to the repository. Use environment vars or a secrets manager.
"""
from .settings import *  # import base settings
import os

# Security
DEBUG = False
SECRET_KEY = os.environ.get('AWARENESS_SECRET_KEY', SECRET_KEY)
ALLOWED_HOSTS = os.environ.get('AWARENESS_ALLOWED_HOSTS', 'localhost').split(',')

# Static files should be served by the webserver (nginx). Collect static during build.
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Example database override - default to existing sqlite for local testing
DATABASES['default'] = {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': os.environ.get('POSTGRES_DB', 'awareness'),
    'USER': os.environ.get('POSTGRES_USER', 'awareness'),
    'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
    'HOST': os.environ.get('POSTGRES_HOST', 'db'),
    'PORT': os.environ.get('POSTGRES_PORT', '5432'),
}

# Use a secure email backend in production
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
