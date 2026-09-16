from flask import Flask
from flask import request
from flask import redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
if os.path.exists('/share/cannalog/database'):
    db_path = '/share/cannalog/database/cannalog.db'
else:
    db_path = 'cannalog.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

app.config['UPLOAD_FOLDER'] = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static', 'uploads'))

max_upload_mb_env = os.environ.get('MAX_UPLOAD_MB')
try:
    max_upload_mb = int(max_upload_mb_env)
except (TypeError, ValueError):
    max_upload_mb = 20
app.config['MAX_CONTENT_LENGTH'] = max_upload_mb * 1024 * 1024  # MB zu Bytes

# app.debug = True if os.environ.get('DEBUG', 'your-secret-key') == 'your-secret-key' else False

if not app.debug:
    app.config['SESSION_COOKIE_SECURE'] = True
else:
    app.config['SESSION_COOKIE_SECURE'] = False
	

# Ingress/Proxy compatibility for Home Assistant
if os.environ.get('HASSIO_TOKEN'):
	ingress_entry = os.environ.get('INGRESS_ENTRY', '/api/hassio_ingress').rstrip('/')
	app.config['APPLICATION_ROOT'] = ingress_entry
	app.config['PREFERRED_URL_SCHEME'] = 'http'
	
app.config['SESSION_COOKIE_PATH'] = app.config.get('APPLICATION_ROOT', '/')

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# URL filter
@app.template_filter('relative_url')
def relative_url_filter(url):
    return url.lstrip('/')

# Ingress-kompatibler Redirect
def ingress_redirect(endpoint, **values):
    path = request.path
    ingress_entry = os.environ.get('INGRESS_ENTRY', '/api/hassio_ingress').rstrip('/')
    # search for ingress entry
    if path.startswith(ingress_entry):
		# Extract the ingress ID
        parts = path[len(ingress_entry):].lstrip('/').split('/', 1)
        if parts and parts[0]:
            ingress_id = parts[0]
            ingress_root = f"{ingress_entry}/{ingress_id}"
            target = url_for(endpoint, **values).lstrip('/')
            return redirect(f"{ingress_root}/{target}")
    # Fallback: Standalone
    return redirect(url_for(endpoint, **values))

# Inject APPLICATION_ROOT into all templates
@app.context_processor
def inject_application_root():
    ingress_entry = os.environ.get('INGRESS_ENTRY', '/api/hassio_ingress').rstrip('/')
    path = request.path
    # search /api/hassio_ingress/<id>/
    if path.startswith(ingress_entry):
        # Extrahiere die Ingress-ID
        parts = path[len(ingress_entry):].lstrip('/').split('/', 1)
        if parts and parts[0]:
            ingress_id = parts[0]
            root = f"{ingress_entry}/{ingress_id}"
            return dict(APPLICATION_ROOT=root)
    # Fallback: Standalone
    return dict(APPLICATION_ROOT='')

from app import routes, models
