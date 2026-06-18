# backend/config/asgi.py
"""
ASGI config for the API Connector project.
Phase 1 decision point: confirm whether async views require ASGI hosting.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_asgi_application()