# Sicherheitshinweise für Produktion

1. Setze einen sicheren SECRET_KEY in app/__init__.py:
   import secrets
   app.config['SECRET_KEY'] = secrets.token_hex(32)

2. Debug-Modus deaktivieren:
   Starte Flask NICHT mit debug=True in Produktion.

3. Upload-Ordner absichern:
   - Stelle sicher, dass /static/uploads/ nicht für Ausführung von Skripten freigegeben ist.
   - Nginx-Konfiguration wie oben nutzen.

4. Gunicorn als WSGI-Server nutzen:
   cd /home/michael/projects/cannalog
   /home/michael/projects/cannalog/.venv/bin/gunicorn -c gunicorn_config.py

5. Nginx als Reverse Proxy davor schalten (siehe cannalog_nginx.conf).

6. HTTPS aktivieren (z.B. mit Let's Encrypt/certbot).

7. Datenbank-Backup regelmäßig durchführen.

8. User-Uploads auf erlaubte Dateitypen prüfen (bereits umgesetzt).

Weitere Tipps: https://flask.palletsprojects.com/security/
