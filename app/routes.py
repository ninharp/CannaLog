import base64
import os
import uuid
from datetime import datetime

from flask import render_template, redirect, url_for, flash, request, send_from_directory, make_response, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf.file import FileAllowed
from sqlalchemy.orm import joinedload
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from wtforms import SelectField, MultipleFileField, SubmitField
from wtforms.validators import DataRequired

from app import app, db, login_manager
from app.forms import (
    BaseForm, RegistrationForm, LoginForm, PlantForm, EnvironmentForm, PlantLogForm,
    EnvironmentLogForm, PlantActionLogForm, LogExportForm,
)
from app.lamp_model import Lamp
from app.models import (
    User, Plant, Environment, PlantLog, EnvironmentLog, PlantActionLog,
    Measurement, PlantImage, EnvironmentImage,
)

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


def go(target):
    """Redirect to an app-relative path, honouring the Ingress prefix."""
    return redirect(f"{request.script_root}/{target.lstrip('/')}")


def save_upload(file):
    """Store an uploaded image under a random name and return that name, or None."""
    if not file or not file.filename:
        return None
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        flash(f'Datei {file.filename} ignoriert: nur Bilder erlaubt.', 'warning')
        return None
    filename = secure_filename(f"{uuid.uuid4().hex}{ext}")
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename


def delete_upload(filename):
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    except OSError:
        pass


### API Endpoints for dynamic form population ###

@app.route('/api/environment/<int:env_id>/plants')
@login_required
def environment_plants(env_id):
    plants = Plant.query.filter_by(user_id=current_user.id, environment_id=env_id).all()
    plant_list = [(p.id, p.pflanzenname) for p in plants]
    return jsonify(plant_list)

### App endpoints ###

@app.route('/logs/export', methods=['GET', 'POST'])
@login_required
def export_logs():
    environments = Environment.query.filter_by(user_id=current_user.id).order_by(Environment.name).all()
    plants = Plant.query.filter_by(user_id=current_user.id).all()
    form = LogExportForm()
    form.environment_id.choices = [(e.id, e.name) for e in environments]
    form.plant_ids.choices = [(p.id, p.pflanzenname) for p in plants]
    if request.method == 'GET':
        preselect_env = request.args.get('env_id', type=int)
        if preselect_env and any(e.id == preselect_env for e in environments):
            form.environment_id.data = preselect_env
    report = None
    if form.validate_on_submit():
        env = db.session.get(Environment, form.environment_id.data)
        env_plants = [p for p in plants if p.environment_id == env.id]
        selected = [p for p in plants if p.id in (form.plant_ids.data or [])] or env_plants
        plant_sections = []
        for plant in selected:
            entries = []
            if form.include_plant_logs.data:
                entries += [{'type': 'log', 'obj': log, 'date': log.date, 'time': log.time} for log in plant.logs]
            if form.include_action_logs.data:
                entries += [{'type': 'action', 'obj': action, 'date': action.date, 'time': action.time} for action in plant.actions]
            entries.sort(key=lambda entry: (entry['date'], entry['time'] or datetime.min.time()), reverse=True)
            plant_sections.append({'plant': plant, 'entries': entries})
        report = {
            'env': env,
            'env_logs': sorted(env.logs, key=lambda log: (log.date, log.time or datetime.min.time()), reverse=True) if form.include_env_logs.data else [],
            'plants': plant_sections,
            'generated_at': datetime.now().strftime('%d.%m.%Y, %H:%M'),
        }
        if 'pdf' in request.form:
            from weasyprint import HTML
            with open(os.path.join(app.root_path, 'static', 'cannalog.css')) as f:
                css = f.read()
            with open(os.path.join(app.root_path, 'static', 'assets', 'logo_small.png'), 'rb') as f:
                logo = 'data:image/png;base64,' + base64.b64encode(f.read()).decode('ascii')
            html = render_template('report_pdf.html', report=report, css=css, logo=logo)
            pdf = HTML(string=html).write_pdf()
            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            filename = secure_filename(f"cannalog-{env.name}-{datetime.now():%Y-%m-%d}.pdf") or 'cannalog.pdf'
            response.headers['Content-Disposition'] = f'attachment; filename={filename}'
            return response
    return render_template('logs_export.html', form=form, report=report)


@login_manager.unauthorized_handler
def unauthorized():
    flash(login_manager.login_message, login_manager.login_message_category)
    return redirect(url_for('login', next=request.full_path if request.query_string else request.path))


# Pflanzenaktions-Logbuch

@app.route('/plant_actions')
@login_required
def plant_action_logs():
    # Zeige alle Aktionen für Pflanzen des Users
    plants = Plant.query.filter_by(user_id=current_user.id).all()
    logs = PlantActionLog.query.join(Plant).filter(Plant.user_id == current_user.id).order_by(PlantActionLog.date.desc(), PlantActionLog.time.desc()).all()
    return render_template('plant_action_logs.html', logs=logs, plants=plants)

@app.route('/plant_actions/add', methods=['GET', 'POST'])
@login_required
def add_plant_action_log():
    plants = Plant.query.filter_by(user_id=current_user.id).all()
    form = PlantActionLogForm()
    form.plant_id.choices = [(p.id, p.pflanzenname) for p in plants]
    # Wenn plant_id als Query-Parameter übergeben wurde, vorauswählen
    preselect_id = request.args.get('plant_id', type=int)
    if preselect_id and any(p.id == preselect_id for p in plants):
        form.plant_id.data = preselect_id
    if form.validate_on_submit():
        log = PlantActionLog(
            plant_id=form.plant_id.data,
            date=form.date.data,
            time=form.time.data,
            action=form.action.data,
            notes=form.notes.data
        )
        db.session.add(log)
        db.session.commit()
        flash('Aktion gespeichert.', 'success')
        # Wenn kein plant_id als Query-Parameter gesetzt ist, gehe zum Dashboard
        return go(f"plant/{form.plant_id.data}")
    return render_template('plant_action_log_form.html', form=form)

@app.route('/plant_actions/<int:log_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plant_action_log(log_id):
    log = PlantActionLog.query.get_or_404(log_id)
    plant = Plant.query.get_or_404(log.plant_id)
    if plant.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    plants = Plant.query.filter_by(user_id=current_user.id).all()
    form = PlantActionLogForm(obj=log)
    form.plant_id.choices = [(p.id, p.pflanzenname) for p in plants]
    if form.validate_on_submit():
        log.plant_id = form.plant_id.data
        log.date = form.date.data
        log.time = form.time.data
        log.action = form.action.data
        log.notes = form.notes.data
        db.session.commit()
        return go(f"plant/{log.plant_id}")
    return render_template('plant_action_log_form.html', form=form, edit=True, log=log)

@app.route('/plant_actions/<int:log_id>/delete', methods=['POST'])
@login_required
def delete_plant_action_log(log_id):
    log = PlantActionLog.query.get_or_404(log_id)
    plant = Plant.query.get_or_404(log.plant_id)
    if plant.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    db.session.delete(log)
    db.session.commit()
    flash('Aktion gelöscht.', 'success')
    return go(f"plant/{plant.id}")

# EnvironmentLog: Log-Einträge für Umgebungen
# @app.route('/environment/<int:env_id>/logs')
# @login_required
# def environment_logs(env_id):
#     env = Environment.query.get_or_404(env_id)
#     if env.user_id != current_user.id:
#         flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
#         return go('dashboard')
#     logs = EnvironmentLog.query.filter_by(environment_id=env.id).order_by(EnvironmentLog.date.desc()).all()
#     return render_template('environment_logs.html', env=env, logs=logs)

@app.route('/environment/<int:env_id>/logs/add', methods=['GET', 'POST'])
@login_required
def add_environment_log(env_id):
    env = Environment.query.get_or_404(env_id)
    if env.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    if request.method == 'POST':
        form = EnvironmentLogForm(request.form)
    else:
        form = EnvironmentLogForm()
        if len(form.measurements.entries) == 0:
            for _ in range(form.measurements.min_entries):
                form.measurements.append_entry()
    if form.validate_on_submit():
        log = EnvironmentLog(environment_id=env.id, date=form.date.data, time=form.time.data, notes=form.notes.data)
        db.session.add(log)
        db.session.commit()  # log.id muss existieren
        def has_value(val):
            return val is not None and (isinstance(val, (int, float)) or (isinstance(val, str) and val.strip() != ''))
        for mform in form.measurements.entries:
            t = mform.form.type.data
            v = mform.form.value.data
            minv = mform.form.min_value.data
            maxv = mform.form.max_value.data
            if t and (has_value(v) or has_value(minv) or has_value(maxv)):
                if has_value(v):
                    measurement = Measurement(
                        type=t,
                        value=v,
                        min_value=None,
                        max_value=None,
                        environment_log_id=log.id
                    )
                else:
                    measurement = Measurement(
                        type=t,
                        value=None,
                        min_value=minv if has_value(minv) else None,
                        max_value=maxv if has_value(maxv) else None,
                        environment_log_id=log.id
                    )
                db.session.add(measurement)
        db.session.commit()
        flash('Messung gespeichert.', 'success')
        return go(f"environment/{env.id}")
    return render_template('environment_log_form.html', form=form, env=env)

@app.route('/environment/logs/<int:log_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_environment_log(log_id):
    log = EnvironmentLog.query.get_or_404(log_id)
    env = Environment.query.get_or_404(log.environment_id)
    if env.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    if request.method == 'POST':
        form = EnvironmentLogForm(request.form)
    else:
        form = EnvironmentLogForm(obj=log)
        # Nur auffüllen, falls keine Messungen im Form-Objekt (sonst doppelt)
        if len(form.measurements.entries) < len(log.measurements):
            for m in log.measurements:
                mform = {}
                mform['type'] = m.type
                mform['value'] = m.value
                mform['min_value'] = m.min_value
                mform['max_value'] = m.max_value
                form.measurements.append_entry(mform)
        # Leere Felder auffüllen
        for _ in range(len(form.measurements.entries), form.measurements.min_entries):
            form.measurements.append_entry()
    if form.validate_on_submit():
        log.date = form.date.data
        log.time = form.time.data
        log.notes = form.notes.data
        # Alte Messungen löschen
        for m in log.measurements:
            db.session.delete(m)
        # Neue Messungen speichern
        def has_value(val):
            return val is not None and (isinstance(val, (int, float)) or (isinstance(val, str) and val.strip() != ''))
        for mform in form.measurements.entries:
            t = mform.form.type.data
            v = mform.form.value.data
            minv = mform.form.min_value.data
            maxv = mform.form.max_value.data
            if t and (has_value(v) or has_value(minv) or has_value(maxv)):
                if has_value(v):
                    measurement = Measurement(
                        type=t,
                        value=v,
                        min_value=None,
                        max_value=None,
                        environment_log_id=log.id
                    )
                else:
                    measurement = Measurement(
                        type=t,
                        value=None,
                        min_value=minv if has_value(minv) else None,
                        max_value=maxv if has_value(maxv) else None,
                        environment_log_id=log.id
                    )
                db.session.add(measurement)
        db.session.commit()
        flash('Messung gespeichert.', 'success')
        return go(f"environment/{env.id}")
    
    return render_template('environment_log_form.html', form=form, env=env, edit=True, log=log)

@app.route('/environment/logs/<int:log_id>/delete', methods=['POST'])
@login_required
def delete_environment_log(log_id):
    log = EnvironmentLog.query.get_or_404(log_id)
    env = Environment.query.get_or_404(log.environment_id)
    if env.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    db.session.delete(log)
    db.session.commit()
    flash('Eintrag gelöscht.', 'success')
    return go(f"environment/{env.id}")
# PlantLog: Log-Einträge für Pflanzen
# @app.route('/plant/<int:plant_id>/logs')
# @login_required
# def plant_logs(plant_id):
#     plant = Plant.query.get_or_404(plant_id)
#     if plant.user_id != current_user.id:
#         flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
#         return go('dashboard')
#     logs = PlantLog.query.filter_by(plant_id=plant.id).all()
#     actions = PlantActionLog.query.filter_by(plant_id=plant.id).all()
#     # Kombiniere und sortiere chronologisch absteigend
#     combined = [
#         {"type": "log", "obj": log, "date": log.date} for log in logs
#     ] + [
#         {"type": "action", "obj": action, "date": action.date} for action in actions
#     ]
#     combined.sort(key=lambda x: x["date"], reverse=True)
#     return render_template('plant_logs.html', plant=plant, entries=combined)

@app.route('/plant/<int:plant_id>/logs/add', methods=['GET', 'POST'])
@login_required
def add_plant_log(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    if plant.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    if request.method == 'POST':
        form = PlantLogForm(request.form)
    else:
        form = PlantLogForm()
        if len(form.measurements.entries) == 0:
            for _ in range(form.measurements.min_entries):
                form.measurements.append_entry()
    if form.validate_on_submit():
        log = PlantLog(plant_id=plant.id, date=form.date.data, time=form.time.data, notes=form.notes.data)
        db.session.add(log)
        db.session.commit()  # log.id muss existieren
        def has_value(val):
            return val is not None and (isinstance(val, (int, float)) or (isinstance(val, str) and val.strip() != ''))
        for mform in form.measurements.entries:
            t = mform.form.type.data
            v = mform.form.value.data
            minv = mform.form.min_value.data
            maxv = mform.form.max_value.data
            if t and (has_value(v) or has_value(minv) or has_value(maxv)):
                if has_value(v):
                    measurement = Measurement(
                        type=t,
                        value=v,
                        min_value=None,
                        max_value=None,
                        plant_log_id=log.id
                    )
                else:
                    measurement = Measurement(
                        type=t,
                        value=None,
                        min_value=minv if has_value(minv) else None,
                        max_value=maxv if has_value(maxv) else None,
                        plant_log_id=log.id
                    )
                db.session.add(measurement)
        db.session.commit()
        flash('Messung gespeichert.', 'success')
        return go(f"plant/{plant.id}")
    return render_template('plant_log_form.html', form=form, plant=plant)

@app.route('/plant/logs/<int:log_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plant_log(log_id):
    log = PlantLog.query.get_or_404(log_id)
    plant = Plant.query.get_or_404(log.plant_id)
    if plant.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    if request.method == 'POST':
        form = PlantLogForm(request.form)
    else:
        form = PlantLogForm(obj=log)
        # Nur auffüllen, falls keine Messungen im Form-Objekt (sonst doppelt)
        if len(form.measurements.entries) < len(log.measurements):
            for m in log.measurements:
                mform = {}
                mform['type'] = m.type
                mform['value'] = m.value
                mform['min_value'] = m.min_value
                mform['max_value'] = m.max_value
                form.measurements.append_entry(mform)
        # Leere Felder auffüllen
        for _ in range(len(form.measurements.entries), form.measurements.min_entries):
            form.measurements.append_entry()
    if form.validate_on_submit():
        log.date = form.date.data
        log.time = form.time.data
        log.notes = form.notes.data
        # Alte Messungen löschen
        for m in log.measurements:
            db.session.delete(m)
        # Neue Messungen speichern
        def has_value(val):
            return val is not None and (isinstance(val, (int, float)) or (isinstance(val, str) and val.strip() != ''))
        for mform in form.measurements.entries:
            t = mform.form.type.data
            v = mform.form.value.data
            minv = mform.form.min_value.data
            maxv = mform.form.max_value.data
            if t and (has_value(v) or has_value(minv) or has_value(maxv)):
                if has_value(v):
                    measurement = Measurement(
                        type=t,
                        value=v,
                        min_value=None,
                        max_value=None,
                        plant_log_id=log.id
                    )
                else:
                    measurement = Measurement(
                        type=t,
                        value=None,
                        min_value=minv if has_value(minv) else None,
                        max_value=maxv if has_value(maxv) else None,
                        plant_log_id=log.id
                    )
                db.session.add(measurement)
        db.session.commit()
        flash('Messung gespeichert.', 'success')
        return go(f"plant/{plant.id}")
    return render_template('plant_log_form.html', form=form, plant=plant, edit=True, log=log)

@app.route('/plant/logs/<int:log_id>/delete', methods=['POST'])
@login_required
def delete_plant_log(log_id):
    log = PlantLog.query.get_or_404(log_id)
    plant = Plant.query.get_or_404(log.plant_id)
    if plant.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    db.session.delete(log)
    db.session.commit()
    flash('Eintrag gelöscht.', 'success')
    return go(f"plant/{plant.id}")

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
                return go('dashboard')
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if not app.config['ALLOW_REGISTRATION']:
        flash('Registrierung ist deaktiviert.', 'warning')
        return go('login')
    form = RegistrationForm()
    if form.validate_on_submit():
        # Prüfe, ob der Benutzername schon existiert
        if User.query.filter_by(username=form.username.data).first():
            flash('Diesen Benutzernamen gibt es schon. Wähle einen anderen.', 'danger')
            return render_template('register.html', form=form)
        hashed_pw = generate_password_hash(form.password.data)
        user = User(username=form.username.data, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash('Konto erstellt. Melde dich jetzt an.', 'success')
        return go("login")
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            flash('Angemeldet.', 'success')
            next_url = request.args.get('next', '')
            if next_url.startswith('/') and not next_url.startswith('//'):
                return go(next_url)
            return go("dashboard")
        else:
            flash('Benutzername oder Passwort stimmt nicht.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return go('')

@app.route('/dashboard')
@login_required
def dashboard():
    plants = Plant.query.options(joinedload(Plant.images)).filter_by(user_id=current_user.id).all()
    environments = Environment.query.options(joinedload(Environment.images)).filter_by(user_id=current_user.id).all()
    # Sortiere images nach ID, damit die Nummerierung und Zuordnung stimmt
    for env in environments:
        env.images.sort(key=lambda img: img.id)
        # Preview-Bild bestimmen
        preview_img = None
        if env.preview_image_id:
            for img in env.images:
                if img.id == env.preview_image_id:
                    preview_img = img
                    break
        if not preview_img and env.images:
            preview_img = env.images[0]
        env.preview_img = preview_img
    for plant in plants:
        plant.images.sort(key=lambda img: img.id)
        app.logger.info(f"[dashboard] plant_id={plant.id} preview_image_id={plant.preview_image_id} images={[img.id for img in plant.images]}")
        # Preview-Bild bestimmen
        preview_img = None
        if plant.preview_image_id:
            for img in plant.images:
                if img.id == plant.preview_image_id:
                    preview_img = img
                    break
        if not preview_img and plant.images:
            preview_img = plant.images[0]
        plant.preview_img = preview_img
    return render_template('dashboard.html', plants=plants, environments=environments)

@app.route('/plant/add', methods=['GET', 'POST'])
@login_required
def add_plant():
    env_id_param = request.args.get('env_id', type=int)
    form = PlantForm()
    env_choices = [(e.id, e.name) for e in Environment.query.filter_by(user_id=current_user.id)]
    env_choices.insert(0, (-1, 'Aussenbereich (Ohne Umgebung)'))
    form.environment_id.choices = env_choices
    # Umgebung vorwählen, falls env_id als Parameter übergeben
    if request.method == 'GET' and env_id_param is not None:
        form.environment_id.data = env_id_param
    if form.validate_on_submit():
        env_id = form.environment_id.data if form.environment_id.data != -1 else None
        plant = Plant(
            pflanzenname=form.pflanzenname.data,
            date=form.date.data,
            count=form.count.data,
            medium_type=form.medium_type.data,
            medium_notes=form.medium_notes.data,
            strain=form.strain.data or 'Unbekannter Strain',
            phase=form.phase.data,
            notes=form.notes.data,
            user_id=current_user.id,
            environment_id=env_id
        )
        db.session.add(plant)
        db.session.flush()
        files = request.files.getlist('images')
        for file in files:
            filename = save_upload(file)
            if filename:
                db.session.add(PlantImage(plant_id=plant.id, filename=filename))
        db.session.commit()
        flash('Pflanze angelegt.', 'success')
        return go(f"plant/{plant.id}")
    return render_template('plant_form.html', form=form)


@app.route('/plant/<int:plant_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plant(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    if plant.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    form = PlantForm(obj=plant)
    # WTForms MultipleFileField: ensure .images is always set, even if no new upload
    if request.method == 'POST' and 'images' not in request.files:
        form.images.data = []
    env_choices = [(e.id, e.name) for e in Environment.query.filter_by(user_id=current_user.id)]
    env_choices.insert(0, (-1, 'Aussenbereich (Ohne Umgebung)'))
    form.environment_id.choices = env_choices
    # Vorschaubild-Auswahl
    images = PlantImage.query.filter_by(plant_id=plant.id).order_by(PlantImage.id).all()
    form.preview_image_id.choices = [(-1, 'Kein Vorschaubild')] + [
        (img.id, f"Bild {idx+1}") for idx, img in enumerate(images)
    ]
    if request.method == 'GET':
        form.preview_image_id.data = plant.preview_image_id if plant.preview_image_id else -1
        app.logger.info(f"[edit_plant GET] plant_id={plant.id} preview_image_id={plant.preview_image_id} images={[img.id for img in images]}")
    if request.method == 'POST' and request.form.get('delete_image_id') is not None and request.form.get('delete_image_id') != '':
        # Einzelnes Bild löschen
        img_id = int(request.form.get('delete_image_id'))
        img = PlantImage.query.get_or_404(img_id)
        if img.plant_id != plant.id or plant.user_id != current_user.id:
            flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        else:
            delete_upload(img.filename)
            db.session.delete(img)
            db.session.commit()
            flash('Bild gelöscht.', 'success')
        return go(f"plant/{plant_id}/edit")

    if form.validate_on_submit():
        plant.pflanzenname = form.pflanzenname.data
        plant.date = form.date.data
        plant.count = form.count.data
        plant.medium_type = form.medium_type.data
        plant.medium_notes = form.medium_notes.data
        plant.strain = form.strain.data or 'Unbekannter Strain'
        plant.phase = form.phase.data
        plant.notes = form.notes.data
        plant.environment_id = form.environment_id.data if form.environment_id.data != -1 else None
        # Vorschaubild setzen (immer int!)
        try:
            selected_preview = int(form.preview_image_id.data)
        except Exception:
            selected_preview = -1
        plant.preview_image_id = selected_preview if selected_preview != -1 else None
        app.logger.info(f"[edit_plant POST] plant_id={plant.id} selected_preview={selected_preview} preview_image_id={plant.preview_image_id} images={[img.id for img in images]}")
        # Neue Bilder hinzufügen (optional)
        files = request.files.getlist('images')
        for file in files:
            filename = save_upload(file)
            if filename:
                db.session.add(PlantImage(plant_id=plant.id, filename=filename))
        db.session.commit()
        db.session.refresh(plant)
        db.session.expire(plant, ['images'])
        flash('Pflanze gespeichert.', 'success')
        return go(f"plant/{plant.id}")

    # Am Ende: immer das Formular rendern, wenn kein Redirect erfolgt ist
    return render_template('plant_form.html', form=form, plant=plant, edit=True)

# Plant overview page
@app.route('/plant/<int:plant_id>')
@login_required
def plant_overview(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    if plant.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    logs = PlantLog.query.filter_by(plant_id=plant.id).all()
    actions = PlantActionLog.query.filter_by(plant_id=plant.id).all()
    combined = [
        {"type": "log", "obj": log, "date": log.date, "time": log.time} for log in logs
    ] + [
        {"type": "action", "obj": action, "date": action.date, "time": action.time} for action in actions
    ]
    combined.sort(key=lambda x: (x["date"], x["time"] or datetime.min.time()), reverse=True)
    return render_template('plant_overview.html', plant=plant, entries=combined)
    # return render_template('plant_form.html', form=form, plant=plant)

@app.route('/plant/<int:plant_id>/delete', methods=['POST'])
@login_required
def delete_plant(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    if plant.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    # Delete all images from disk
    for img in plant.images:
        delete_upload(img.filename)
    db.session.delete(plant)
    db.session.commit()
    flash('Pflanze gelöscht.', 'success')
    return go('dashboard')

@app.route('/environment/add', methods=['GET', 'POST'])
@login_required
def add_environment():
    form = EnvironmentForm()
    if form.validate_on_submit():
        env = Environment(
            name=form.name.data,
            auto_watering=form.auto_watering.data,
            light_enabled=form.light_enabled.data,
            exposure_time=int(request.form.get('exposure_time', 18)),
            notes=form.notes.data,
            length=form.length.data,
            width=form.width.data,
            height=form.height.data,
            user_id=current_user.id
        )
        db.session.add(env)
        db.session.flush()
        # Mehrere Bilder speichern (korrektes Handling für dynamische Felder)
        files = request.files.getlist('images')
        for file in files:
            filename = save_upload(file)
            if filename:
                db.session.add(EnvironmentImage(environment_id=env.id, filename=filename))
        # Lampen speichern
        for lamp_form in form.lamps.entries:
            if not lamp_form.form.power.data:
                continue
            lamp = Lamp(
                environment_id=env.id,
                type=lamp_form.form.type.data,
                power=lamp_form.form.power.data,
                kelvin=lamp_form.form.kelvin.data
            )
            db.session.add(lamp)
        db.session.commit()
        flash('Umgebung angelegt.', 'success')
        return go(f"environment/{env.id}")
    return render_template('environment_form.html', form=form)

@app.route('/environment/<int:env_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_environment(env_id):
    env = Environment.query.get_or_404(env_id)
    if env.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')

    if request.method == 'POST':
        form = EnvironmentForm()
        images = EnvironmentImage.query.filter_by(environment_id=env.id).all()
        form.preview_image_id.choices = [(-1, 'Kein Vorschaubild')] + [
            (img.id, f"Bild {idx+1}") for idx, img in enumerate(images)
        ]
        # Pre-select preview image (handle both int and str from form)
        try:
            preview_val = int(request.form.get('preview_image_id', -1))
        except Exception:
            preview_val = -1
        form.preview_image_id.data = preview_val
        # Lampen-FieldList nach POST ohne Lampen-Daten immer aus der DB initialisieren
        if not request.form.getlist('lamps-0-type'):
            env_db = Environment.query.get_or_404(env_id)
            form.lamps.entries = []
            for lamp in env_db.lamps:
                form.lamps.append_entry({
                    'type': lamp.type,
                    'power': lamp.power,
                    'kelvin': lamp.kelvin
                })
        # Bild löschen wie im Plant-Formular
        delete_image_id = request.form.get('delete_image_id')
        if delete_image_id:
            img = db.session.get(EnvironmentImage, int(delete_image_id))
            if img and img.environment_id == env.id:
                delete_upload(img.filename)
                db.session.delete(img)
                db.session.commit()
                flash('Bild gelöscht.', 'success')
                return go(f'environment/{env.id}/edit')
        if form.validate_on_submit():
            env.name = form.name.data
            env.auto_watering = form.auto_watering.data
            env.light_enabled = form.light_enabled.data
            env.exposure_time = int(request.form.get('exposure_time', env.exposure_time or 18))
            env.notes = form.notes.data
            env.length = form.length.data
            env.width = form.width.data
            env.height = form.height.data
            # Vorschaubild setzen (immer int!)
            try:
                selected_preview = int(form.preview_image_id.data)
            except Exception:
                selected_preview = -1
            env.preview_image_id = selected_preview if selected_preview != -1 else None
            # Bilder hinzufügen (nur neue, alte bleiben erhalten)
            files = request.files.getlist('images')
            for file in files:
                filename = save_upload(file)
                if filename:
                    db.session.add(EnvironmentImage(environment_id=env.id, filename=filename))
            # Lampen aktualisieren: alte löschen, neue anlegen
            Lamp.query.filter_by(environment_id=env.id).delete()
            for lamp_form in form.lamps.entries:
                if not lamp_form.form.power.data:
                    continue
                lamp = Lamp(
                    environment_id=env.id,
                    type=lamp_form.form.type.data,
                    power=lamp_form.form.power.data,
                    kelvin=lamp_form.form.kelvin.data
                )
                db.session.add(lamp)
            db.session.commit()
            db.session.refresh(env)
            flash('Umgebung gespeichert.', 'success')
            return go(f"environment/{env.id}")
        # Bei POST mit Fehlern: Formular mit Benutzereingaben anzeigen
        return render_template('environment_form.html', form=form, env=env)
    # GET oder nach Redirect: Environment frisch laden und Lampen-FieldList aus DB initialisieren
    env = Environment.query.get_or_404(env_id)
    form = EnvironmentForm(obj=env)
    # Bildauswahl für Vorschaubild
    images = EnvironmentImage.query.filter_by(environment_id=env.id).all()
    form.preview_image_id.choices = [(-1, 'Kein Vorschaubild')] + [
        (img.id, f"Bild {idx+1}") for idx, img in enumerate(images)
    ]
    form.preview_image_id.data = env.preview_image_id if env.preview_image_id else -1
    form.lamps.entries = []
    for lamp in env.lamps:
        form.lamps.append_entry({
            'type': lamp.type,
            'power': lamp.power,
            'kelvin': lamp.kelvin
        })
    return render_template('environment_form.html', form=form, env=env)

@app.route('/environment/<int:env_id>/delete', methods=['POST'])
@login_required
def delete_environment(env_id):
    env = Environment.query.get_or_404(env_id)
    if env.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    # Delete all environment images from disk
    for img in env.images:
        delete_upload(img.filename)
    move_plants = request.args.get('move_plants', type=int) == 1
    if move_plants:
        # Set all plants to Aussenbereich (environment_id=None)
        for plant in env.plants:
            plant.environment_id = None
        db.session.delete(env)
        db.session.commit()
        flash('Umgebung gelöscht. Die Pflanzen stehen jetzt unter „Draußen“.', 'success')
    else:
        # Lösche alle Pflanzen dieser Umgebung (inkl. Bilder)
        for plant in env.plants:
            for img in plant.images:
                delete_upload(img.filename)
            db.session.delete(plant)
        db.session.delete(env)
        db.session.commit()
        flash('Umgebung und ihre Pflanzen gelöscht.', 'success')
    return go('dashboard')

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Bild aus Umgebung löschen
@app.route('/environment/<int:env_id>/image/<int:image_id>/delete', methods=['POST'])
@login_required
def delete_environment_image(env_id, image_id):
    img = EnvironmentImage.query.get_or_404(image_id)
    env = Environment.query.get_or_404(env_id)
    if env.user_id != current_user.id or img.environment_id != env.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go(f"environment/{env_id}/edit")
    # Datei löschen
    delete_upload(img.filename)
    db.session.delete(img)
    db.session.commit()
    flash('Bild gelöscht.', 'success')
    # Environment-Objekt frisch laden, mit reload-Parameter um Browser-Cache zu umgehen
    return go(f"environment/{env_id}/edit#env-image-list")

# Umgebung-Übersicht
@app.route('/environment/<int:env_id>')
@login_required
def environment_overview(env_id):
    env = Environment.query.get_or_404(env_id)
    if env.user_id != current_user.id:
        flash('Dieser Eintrag gehört zu einem anderen Konto.', 'danger')
        return go('dashboard')
    plants = Plant.query.filter_by(environment_id=env.id, user_id=current_user.id).all()
    logs = EnvironmentLog.query.filter_by(environment_id=env.id).all()
    logs_sorted = sorted(logs, key=lambda x: (x.date, x.time or datetime.min.time()), reverse=True)
    return render_template('environment_overview.html', env=env, plants=plants, entries=logs_sorted)



# Globale Pflanzenlog-Route mit eigenem Formular
class GlobalPlantLogForm(PlantLogForm):
    plant_id = SelectField('Pflanze', coerce=int, validators=[DataRequired()])

@app.route('/plant_log/add', methods=['GET', 'POST'])
@login_required
def add_plant_log_global():
    plants = Plant.query.filter_by(user_id=current_user.id).all()
    form = GlobalPlantLogForm()
    form.plant_id.choices = [(p.id, p.pflanzenname) for p in plants]
    if request.method == 'POST':
        form = GlobalPlantLogForm(request.form)
        form.plant_id.choices = [(p.id, p.pflanzenname) for p in plants]
    else:
        form.plant_id.data = request.args.get('plant_id', type=int)
    if form.validate_on_submit():
        log = PlantLog(plant_id=form.plant_id.data, date=form.date.data, time=form.time.data, notes=form.notes.data)
        db.session.add(log)
        db.session.commit()
        def has_value(val):
            return val is not None and (isinstance(val, (int, float)) or (isinstance(val, str) and val.strip() != ''))
        for mform in form.measurements.entries:
            t = mform.form.type.data
            v = mform.form.value.data
            minv = mform.form.min_value.data
            maxv = mform.form.max_value.data
            if t and (has_value(v) or has_value(minv) or has_value(maxv)):
                if has_value(v):
                    measurement = Measurement(type=t, value=v, min_value=None, max_value=None, plant_log_id=log.id)
                else:
                    measurement = Measurement(type=t, value=None, min_value=minv if has_value(minv) else None, max_value=maxv if has_value(maxv) else None, plant_log_id=log.id)
                db.session.add(measurement)
        db.session.commit()
        flash('Messung gespeichert.', 'success')
        return go(f"plant/{log.plant_id}")
    return render_template('plant_log_form.html', form=form, plant=None, global_mode=True)


# Globale Umgebungslog-Route mit eigenem Formular
class GlobalEnvironmentLogForm(EnvironmentLogForm):
    env_id = SelectField('Umgebung', coerce=int, validators=[DataRequired()])

@app.route('/environment_log/add', methods=['GET', 'POST'])
@login_required
def add_environment_log_global():
    envs = Environment.query.filter_by(user_id=current_user.id).all()
    form = GlobalEnvironmentLogForm()
    form.env_id.choices = [(e.id, e.name) for e in envs]
    if request.method == 'POST':
        form = GlobalEnvironmentLogForm(request.form)
        form.env_id.choices = [(e.id, e.name) for e in envs]
    else:
        form.env_id.data = request.args.get('env_id', type=int)
    if form.validate_on_submit():
        log = EnvironmentLog(environment_id=form.env_id.data, date=form.date.data, time=form.time.data, notes=form.notes.data)
        db.session.add(log)
        db.session.commit()
        def has_value(val):
            return val is not None and (isinstance(val, (int, float)) or (isinstance(val, str) and val.strip() != ''))
        for mform in form.measurements.entries:
            t = mform.form.type.data
            v = mform.form.value.data
            minv = mform.form.min_value.data
            maxv = mform.form.max_value.data
            if t and (has_value(v) or has_value(minv) or has_value(maxv)):
                if has_value(v):
                    measurement = Measurement(type=t, value=v, min_value=None, max_value=None, environment_log_id=log.id)
                else:
                    measurement = Measurement(type=t, value=None, min_value=minv if has_value(minv) else None, max_value=maxv if has_value(maxv) else None, environment_log_id=log.id)
                db.session.add(measurement)
        db.session.commit()
        flash('Klimawerte gespeichert.', 'success')
        return go(f"environment/{log.environment_id}")
    return render_template('environment_log_form.html', form=form, env=None, global_mode=True)

# Globaler Bild-Upload
@app.route('/image/add', methods=['GET', 'POST'])
@login_required
def add_image_global():
    plants = Plant.query.filter_by(user_id=current_user.id).all()
    environments = Environment.query.filter_by(user_id=current_user.id).all()
    # Kombiniertes Dropdown: Wert ist z.B. "plant-1" oder "env-2"
    choices = [(f"plant-{p.id}", f"Pflanze: {p.pflanzenname}") for p in plants] + \
              [(f"env-{e.id}", f"Umgebung: {e.name}") for e in environments]
    class ImageUploadForm(BaseForm):
        target = SelectField('Wofür sind die Fotos?', choices=choices, validators=[DataRequired()])
        images = MultipleFileField('Fotos', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Nur Bilddateien (JPG, PNG, GIF, WebP).')])
        submit = SubmitField('Hochladen')
    form = ImageUploadForm()
    if request.method == 'GET':
        form.target.data = request.args.get('target')
    if request.method == 'POST':
        form = ImageUploadForm(request.form)
        form.target.data = request.form.get('target')
        form.images.data = request.files.getlist('images')
        if form.validate_on_submit():
            files = form.images.data
            target = form.target.data
            if target.startswith('plant-'):
                plant_id = int(target.split('-')[1])
                for file in files:
                    filename = save_upload(file)
                    if filename:
                        db.session.add(PlantImage(plant_id=plant_id, filename=filename))
            elif target.startswith('env-'):
                env_id = int(target.split('-')[1])
                for file in files:
                    filename = save_upload(file)
                    if filename:
                        db.session.add(EnvironmentImage(environment_id=env_id, filename=filename))
            db.session.commit()
            flash('Fotos hochgeladen.', 'success')
            return go(f"plant/{plant_id}" if target.startswith('plant-') else f"environment/{env_id}")
    return render_template('image_upload_form.html', form=form)

@app.route('/healthz')
def healthz():
    return 'ok'


@app.route('/account/api', methods=['GET', 'POST'])
@login_required
def api_access():
    from app.api import hash_token, new_token
    form = BaseForm()
    token = None
    if form.validate_on_submit():
        action = request.form.get('action')
        if action == 'create':
            token = new_token()
            current_user.api_token_hash = hash_token(token)
            current_user.api_token_last_used = None
            db.session.commit()
            flash('Neues Token erzeugt. Es wird nur jetzt angezeigt.', 'success')
        elif action == 'revoke':
            current_user.api_token_hash = None
            current_user.api_token_last_used = None
            db.session.commit()
            flash('Token widerrufen.', 'success')
            return go('account/api')
    response = make_response(render_template('api_access.html', form=form, token=token, section='api_access'))
    response.headers['Cache-Control'] = 'no-store'
    return response
