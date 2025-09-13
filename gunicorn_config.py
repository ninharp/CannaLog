# Gunicorn-Konfiguration für Cannalog
# Speichern als gunicorn_config.py im Projektverzeichnis

bind = '127.0.0.1:8000'
workers = 3
wsgi_app = 'run:app'
