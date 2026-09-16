import os
import secrets

from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

APP_VERSION = os.environ.get('CANNALOG_VERSION', 'dev')

# Home Assistant Ingress proxy. Only requests coming from it may set the prefix,
# otherwise anyone reaching the direct port could spoof the header.
INGRESS_PROXY_IP = '172.30.32.2'


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


class IngressMiddleware:
    """Mount the app below the Ingress path when served through Home Assistant.

    Home Assistant passes the public prefix (/api/hassio_ingress/<token>) in the
    X-Ingress-Path header. Setting SCRIPT_NAME makes url_for() and redirects
    produce correct URLs, while direct access over the port stays at "/".
    """

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        prefix = environ.get('HTTP_X_INGRESS_PATH', '').rstrip('/')
        if prefix and environ.get('REMOTE_ADDR') == INGRESS_PROXY_IP:
            environ['SCRIPT_NAME'] = prefix
        return self.wsgi_app(environ, start_response)


def _secret_key(data_dir):
    key = os.environ.get('SECRET_KEY', '').strip()
    if key and key not in ('change-this-secret-key', 'your-secret-key'):
        return key
    # No usable key configured: generate one and persist it, so sessions
    # survive restarts and every installation gets its own key.
    key_file = os.path.join(data_dir, 'secret_key')
    try:
        with open(key_file) as f:
            stored = f.read().strip()
        if stored:
            return stored
    except OSError:
        pass
    key = secrets.token_hex(32)
    try:
        with open(key_file, 'w') as f:
            f.write(key)
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return key


DATA_DIR = os.environ.get('CANNALOG_DATA_DIR', os.path.abspath('instance'))
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
app.wsgi_app = IngressMiddleware(app.wsgi_app)

app.config['SECRET_KEY'] = _secret_key(DATA_DIR)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', f"sqlite:///{os.path.join(DATA_DIR, 'cannalog.db')}"
)
app.config['UPLOAD_FOLDER'] = os.environ.get(
    'UPLOAD_FOLDER', os.path.join(DATA_DIR, 'uploads')
)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

try:
    max_upload_mb = int(os.environ.get('MAX_UPLOAD_MB', 20))
except ValueError:
    max_upload_mb = 20
app.config['MAX_CONTENT_LENGTH'] = max_upload_mb * 1024 * 1024

# All Ingress add-ons share the Home Assistant origin, so use a distinct cookie
# name. Secure cookies only work over HTTPS and would break plain-HTTP port access.
app.config['SESSION_COOKIE_NAME'] = 'cannalog_session'
app.config['REMEMBER_COOKIE_NAME'] = 'cannalog_remember'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = _env_bool('SECURE_COOKIES')
app.config['REMEMBER_COOKIE_SECURE'] = app.config['SESSION_COOKIE_SECURE']
app.config['ALLOW_REGISTRATION'] = _env_bool('ALLOW_REGISTRATION', True)
# CSRF tokens expire after an hour by default, which breaks long open forms.
app.config['WTF_CSRF_TIME_LIMIT'] = None

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Bitte zuerst einloggen.'
login_manager.login_message_category = 'warning'


@app.template_filter('relative_url')
def relative_url_filter(url):
    # Kept for template compatibility: url_for() already honours the Ingress prefix.
    return url


@app.context_processor
def inject_globals():
    return dict(APP_VERSION=APP_VERSION, ALLOW_REGISTRATION=app.config['ALLOW_REGISTRATION'])


from app import routes, models  # noqa: E402,F401  (registers routes)
