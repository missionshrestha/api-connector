# backend/config/wsgi.py
"""
WSGI config for the API Connector project.
Both wsgi.py and asgi.py are created here. Phase 1 confirms whether async views
require ASGI hosting. Dev server uses WSGI (manage.py runserver).
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()