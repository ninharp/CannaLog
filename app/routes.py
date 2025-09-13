



# ...EXISTING CODE...

# Globale Routen ans Dateiende verschoben:

# --- ab hier am Dateiende einfügen ---


from app import app, db, login_manager
from flask import render_template, redirect, url_for, flash, request, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
from app.models import User, Plant, Environment, PlantLog, EnvironmentLog, PlantActionLog
from app.lamp_model import Lamp
from app.forms import RegistrationForm, LoginForm, PlantForm, EnvironmentForm, PlantLogForm, EnvironmentLogForm, PlantActionLogForm
from wtforms import SelectField
from flask_wtf import FlaskForm
from wtforms import SelectField, MultipleFileField, SubmitField
from wtforms.validators import DataRequired
from flask_wtf.file import FileAllowed

# Pflanzenaktions-Logbuch

@app.route('/plant_actions')
@login_required
def plant_action_logs():
    # Zeige alle Aktionen für Pflanzen des Users
    plants = Plant.query.filter_by(user_id=current_user.id).all()
    logs = PlantActionLog.query.join(Plant).filter(Plant.user_id == current_user.id).order_by(PlantActionLog.date.desc()).all()
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
            action=form.action.data,
            notes=form.notes.data
        )
        db.session.add(log)
        db.session.commit()
        flash('Pflanzenaktion hinzugefügt.', 'success')
        # Wenn kein plant_id als Query-Parameter gesetzt ist, gehe zum Dashboard
        if not preselect_id:
            return redirect(url_for('dashboard'))
        return redirect(url_for('plant_overview', plant_id=form.plant_id.data))
    return render_template('plant_action_log_form.html', form=form)

@app.route('/plant_actions/<int:log_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plant_action_log(log_id):
    log = PlantActionLog.query.get_or_404(log_id)
    plant = Plant.query.get_or_404(log.plant_id)
    if plant.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('plant_action_logs'))
    plants = Plant.query.filter_by(user_id=current_user.id).all()
    form = PlantActionLogForm(obj=log)
    form.plant_id.choices = [(p.id, p.pflanzenname) for p in plants]
    if form.validate_on_submit():
        log.plant_id = form.plant_id.data
        log.date = form.date.data
        log.action = form.action.data
        log.notes = form.notes.data
        db.session.commit()
        return redirect(url_for('plant_overview', plant_id=log.plant_id))
    return render_template('plant_action_log_form.html', form=form, edit=True, log=log)

@app.route('/plant_actions/<int:log_id>/delete', methods=['POST'])
@login_required
def delete_plant_action_log(log_id):
    log = PlantActionLog.query.get_or_404(log_id)
    plant = Plant.query.get_or_404(log.plant_id)
    if plant.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('plant_action_logs'))
    db.session.delete(log)
    db.session.commit()
    flash('Pflanzenaktion gelöscht.', 'success')
    return redirect(url_for('plant_overview', plant_id=plant.id))
from app import app, db, login_manager
from flask import render_template, redirect, url_for, flash, request, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
from app.models import User, Plant, Environment, PlantLog, EnvironmentLog
from app.lamp_model import Lamp
from app.forms import RegistrationForm, LoginForm, PlantForm, EnvironmentForm, PlantLogForm, EnvironmentLogForm

# EnvironmentLog: Log-Einträge für Umgebungen
@app.route('/environment/<int:env_id>/logs')
@login_required
def environment_logs(env_id):
    env = Environment.query.get_or_404(env_id)
    if env.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    logs = EnvironmentLog.query.filter_by(environment_id=env.id).order_by(EnvironmentLog.date.desc()).all()
    return render_template('environment_logs.html', env=env, logs=logs)

@app.route('/environment/<int:env_id>/logs/add', methods=['GET', 'POST'])
@login_required
def add_environment_log(env_id):
    env = Environment.query.get_or_404(env_id)
    if env.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    from app.models import Measurement
    import logging
    if request.method == 'POST':
        form = EnvironmentLogForm(request.form)
        logging.warning(f"CSRF-Token im POST: {request.form.get('csrf_token')}")
    else:
        form = EnvironmentLogForm()
        if len(form.measurements.entries) == 0:
            for _ in range(form.measurements.min_entries):
                form.measurements.append_entry()
    if form.validate_on_submit():
        log = EnvironmentLog(environment_id=env.id, date=form.date.data, notes=form.notes.data)
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
        flash('Log-Eintrag hinzugefügt.', 'success')
        return redirect(url_for('environment_overview', env_id=env.id))
    return render_template('environment_log_form.html', form=form, env=env)

@app.route('/environment/logs/<int:log_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_environment_log(log_id):
    log = EnvironmentLog.query.get_or_404(log_id)
    env = Environment.query.get_or_404(log.environment_id)
    if env.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    from app.models import Measurement
    import logging
    if request.method == 'POST':
        form = EnvironmentLogForm(request.form)
        logging.warning(f"CSRF-Token im POST: {request.form.get('csrf_token')}")
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
        flash('Log-Eintrag aktualisiert.', 'success')
        return redirect(url_for('environment_overview', env_id=env.id))
    return render_template('environment_log_form.html', form=form, env=env, edit=True, log=log)

@app.route('/environment/logs/<int:log_id>/delete', methods=['POST'])
@login_required
def delete_environment_log(log_id):
    log = EnvironmentLog.query.get_or_404(log_id)
    env = Environment.query.get_or_404(log.environment_id)
    if env.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    db.session.delete(log)
    db.session.commit()
    flash('Log-Eintrag gelöscht.', 'success')
    return redirect(url_for('environment_overview', env_id=env.id))
# --- Imports ---
from app import app, db, login_manager
from flask import render_template, redirect, url_for, flash, request, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
from app.models import User, Plant, Environment, PlantLog
from app.lamp_model import Lamp
from app.forms import RegistrationForm, LoginForm, PlantForm, EnvironmentForm, PlantLogForm, EnvironmentLogForm
# PlantLog: Log-Einträge für Pflanzen
@app.route('/plant/<int:plant_id>/logs')
@login_required
def plant_logs(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    if plant.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    logs = PlantLog.query.filter_by(plant_id=plant.id).all()
    actions = PlantActionLog.query.filter_by(plant_id=plant.id).all()
    # Kombiniere und sortiere chronologisch absteigend
    combined = [
        {"type": "log", "obj": log, "date": log.date} for log in logs
    ] + [
        {"type": "action", "obj": action, "date": action.date} for action in actions
    ]
    combined.sort(key=lambda x: x["date"], reverse=True)
    return render_template('plant_logs.html', plant=plant, entries=combined)

@app.route('/plant/<int:plant_id>/logs/add', methods=['GET', 'POST'])
@login_required
def add_plant_log(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    if plant.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    import logging
    logging.warning(f"POST: {request.method == 'POST'} | formdata keys: {list(request.form.keys())}")
    if request.method == 'POST':
        form = PlantLogForm(request.form)
        logging.warning(f"CSRF-Token im POST: {request.form.get('csrf_token')}")
    else:
        form = PlantLogForm()
        if len(form.measurements.entries) == 0:
            for _ in range(form.measurements.min_entries):
                form.measurements.append_entry()
    logging.warning(f"Form validate_on_submit: {form.validate_on_submit()}")
    logging.warning(f"Form errors: {form.errors}")
    if form.validate_on_submit():
        log = PlantLog(plant_id=plant.id, date=form.date.data, notes=form.notes.data)
        db.session.add(log)
        db.session.commit()  # log.id muss existieren
        from app.models import Measurement
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
        flash('Log-Eintrag hinzugefügt.', 'success')
        return redirect(url_for('plant_overview', plant_id=plant.id))
    return render_template('plant_log_form.html', form=form, plant=plant)

@app.route('/plant/logs/<int:log_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plant_log(log_id):
    log = PlantLog.query.get_or_404(log_id)
    plant = Plant.query.get_or_404(log.plant_id)
    if plant.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    from app.models import Measurement
    import logging
    if request.method == 'POST':
        form = PlantLogForm(request.form)
        logging.warning(f"CSRF-Token im POST: {request.form.get('csrf_token')}")
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
    logging.warning(f"Form validate_on_submit: {form.validate_on_submit()}")
    logging.warning(f"Form errors: {form.errors}")
    if form.validate_on_submit():
        log.date = form.date.data
        log.notes = form.notes.data
        # Alte Messungen löschen
        for m in log.measurements:
            db.session.delete(m)
        # Neue Messungen speichern
        from app.models import Measurement
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
        flash('Log-Eintrag aktualisiert.', 'success')
        return redirect(url_for('plant_overview', plant_id=plant.id))
    return render_template('plant_log_form.html', form=form, plant=plant, edit=True, log=log)

@app.route('/plant/logs/<int:log_id>/delete', methods=['POST'])
@login_required
def delete_plant_log(log_id):
    log = PlantLog.query.get_or_404(log_id)
    plant = Plant.query.get_or_404(log.plant_id)
    if plant.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    db.session.delete(log)
    db.session.commit()
    flash('Log-Eintrag gelöscht.', 'success')
    return redirect(url_for('plant_overview', plant_id=plant.id))
from app import app, db, login_manager
from flask import render_template, redirect, url_for, flash, request, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
from app.models import User, Plant, Environment, PlantLog
from app.lamp_model import Lamp
from app.forms import RegistrationForm, LoginForm, PlantForm, EnvironmentForm

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_pw = generate_password_hash(form.password.data)
        user = User(username=form.username.data, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash('Registrierung erfolgreich! Bitte einloggen.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect(url_for('dashboard'))
        else:
            flash('Login fehlgeschlagen. Prüfe Benutzername und Passwort.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    from sqlalchemy.orm import joinedload
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
        from app.models import PlantImage
        for file in files:
            if file and file.filename:
                ext = os.path.splitext(file.filename)[1]
                unique_name = f"{uuid.uuid4().hex}{ext}"
                filename = secure_filename(unique_name)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                img = PlantImage(plant_id=plant.id, filename=filename)
                db.session.add(img)
        db.session.commit()
        flash('Pflanze hinzugefügt!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('plant_form.html', form=form)


@app.route('/plant/<int:plant_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_plant(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    if plant.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    form = PlantForm(obj=plant)
    # WTForms MultipleFileField: ensure .images is always set, even if no new upload
    if request.method == 'POST' and 'images' not in request.files:
        form.images.data = []
    env_choices = [(e.id, e.name) for e in Environment.query.filter_by(user_id=current_user.id)]
    env_choices.insert(0, (-1, 'Aussenbereich (Ohne Umgebung)'))
    form.environment_id.choices = env_choices
    from app.models import PlantImage
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
            flash('Keine Berechtigung.', 'danger')
        else:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img.filename))
            except Exception:
                pass
            db.session.delete(img)
            db.session.commit()
            flash('Bild gelöscht.', 'success')
        return redirect(url_for('edit_plant', plant_id=plant_id))

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
            if file and file.filename:
                ext = os.path.splitext(file.filename)[1]
                unique_name = f"{uuid.uuid4().hex}{ext}"
                filename = secure_filename(unique_name)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                img = PlantImage(plant_id=plant.id, filename=filename)
                db.session.add(img)
        db.session.commit()
        db.session.refresh(plant)
        db.session.expire(plant, ['images'])
        flash('Pflanze aktualisiert!', 'success')
        return redirect(url_for('dashboard'))

    # Am Ende: immer das Formular rendern, wenn kein Redirect erfolgt ist
    return render_template('plant_form.html', form=form, plant=plant, edit=True)

# Plant overview page
@app.route('/plant/<int:plant_id>')
@login_required
def plant_overview(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    if plant.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    logs = PlantLog.query.filter_by(plant_id=plant.id).all()
    actions = PlantActionLog.query.filter_by(plant_id=plant.id).all()
    combined = [
        {"type": "log", "obj": log, "date": log.date} for log in logs
    ] + [
        {"type": "action", "obj": action, "date": action.date} for action in actions
    ]
    combined.sort(key=lambda x: x["date"], reverse=True)
    return render_template('plant_overview.html', plant=plant, entries=combined)

    return render_template('plant_form.html', form=form, plant=plant)

@app.route('/plant/<int:plant_id>/delete', methods=['POST'])
@login_required
def delete_plant(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    if plant.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    # Delete all images from disk
    from app.models import PlantImage
    import os
    for img in plant.images:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img.filename))
        except Exception:
            pass
    db.session.delete(plant)
    db.session.commit()
    flash('Pflanze gelöscht! Alle zugehörigen Bilder wurden entfernt.', 'success')
    return redirect(url_for('dashboard'))

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
            if file and file.filename:
                ext = os.path.splitext(file.filename)[1]
                unique_name = f"{uuid.uuid4().hex}{ext}"
                filename = secure_filename(unique_name)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                from app.models import EnvironmentImage
                img = EnvironmentImage(environment_id=env.id, filename=filename)
                db.session.add(img)
        # Lampen speichern
        for lamp_form in form.lamps.entries:
            lamp = Lamp(
                environment_id=env.id,
                type=lamp_form.form.type.data,
                power=lamp_form.form.power.data,
                kelvin=lamp_form.form.kelvin.data
            )
            db.session.add(lamp)
        db.session.commit()
        flash('Umgebung hinzugefügt!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('environment_form.html', form=form)

@app.route('/environment/<int:env_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_environment(env_id):
    env = Environment.query.get_or_404(env_id)
    if env.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))

    from app.models import EnvironmentImage
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
            from app.models import EnvironmentImage
            img = EnvironmentImage.query.get(int(delete_image_id))
            if img and img.environment_id == env.id:
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img.filename))
                except Exception:
                    pass
                db.session.delete(img)
                db.session.commit()
                flash('Bild gelöscht.', 'success')
                return redirect(url_for('edit_environment', env_id=env.id))
        if form.validate_on_submit():
            import sys
            print(f"[DEBUG] Speichern: Vorher: {env.name}", file=sys.stderr)
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
            print(f"[DEBUG] Speichern: Nachher: {env.name}, preview_image_id={env.preview_image_id}", file=sys.stderr)
            # Bilder hinzufügen (nur neue, alte bleiben erhalten)
            files = request.files.getlist('images')
            for file in files:
                if file and file.filename:
                    ext = os.path.splitext(file.filename)[1]
                    unique_name = f"{uuid.uuid4().hex}{ext}"
                    filename = secure_filename(unique_name)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    img = EnvironmentImage(environment_id=env.id, filename=filename)
                    db.session.add(img)
            # Lampen aktualisieren: alte löschen, neue anlegen
            Lamp.query.filter_by(environment_id=env.id).delete()
            for lamp_form in form.lamps.entries:
                lamp = Lamp(
                    environment_id=env.id,
                    type=lamp_form.form.type.data,
                    power=lamp_form.form.power.data,
                    kelvin=lamp_form.form.kelvin.data
                )
                db.session.add(lamp)
            db.session.commit()
            db.session.refresh(env)
            print(f"[DEBUG] Speichern: Nach Commit: {env.name}", file=sys.stderr)
            flash('Umgebung aktualisiert!', 'success')
            return redirect(url_for('dashboard'))
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
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    # Delete all environment images from disk
    from app.models import EnvironmentImage, Plant
    import os
    for img in env.images:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img.filename))
        except Exception:
            pass
    move_plants = request.args.get('move_plants', type=int) == 1
    if move_plants:
        # Set all plants to Aussenbereich (environment_id=None)
        for plant in env.plants:
            plant.environment_id = None
        db.session.delete(env)
        db.session.commit()
        flash('Umgebung gelöscht! Pflanzen wurden auf Aussenbereich verschoben. Alle zugehörigen Bilder wurden entfernt.', 'success')
    else:
        # Lösche alle Pflanzen dieser Umgebung (inkl. Bilder)
        for plant in env.plants:
            for img in plant.images:
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img.filename))
                except Exception:
                    pass
            db.session.delete(plant)
        db.session.delete(env)
        db.session.commit()
        flash('Umgebung und alle zugehörigen Pflanzen und Bilder wurden gelöscht.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Bild aus Umgebung löschen
from app.models import EnvironmentImage
@app.route('/environment/<int:env_id>/image/<int:image_id>/delete', methods=['POST'])
@login_required
def delete_environment_image(env_id, image_id):
    import sys
    print(f"[DEBUG] Bild löschen: image_id={image_id}, env_id={env_id}", file=sys.stderr)
    img = EnvironmentImage.query.get_or_404(image_id)
    env = Environment.query.get_or_404(env_id)
    if env.user_id != current_user.id or img.environment_id != env.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('edit_environment', env_id=env_id))
    # Datei löschen
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], img.filename))
        print(f"[DEBUG] Datei gelöscht: {img.filename}", file=sys.stderr)
    except Exception as e:
        print(f"[DEBUG] Fehler beim Löschen der Datei: {e}", file=sys.stderr)
        pass
    db.session.delete(img)
    db.session.commit()
    print(f"[DEBUG] Bild-Objekt gelöscht: {image_id}", file=sys.stderr)
    flash('Bild gelöscht.', 'success')
    # Environment-Objekt frisch laden, mit reload-Parameter um Browser-Cache zu umgehen
    return redirect(url_for('edit_environment', env_id=env_id, _anchor='env-image-list'))

# Umgebung-Übersicht
@app.route('/environment/<int:env_id>')
@login_required
def environment_overview(env_id):
    env = Environment.query.get_or_404(env_id)
    if env.user_id != current_user.id:
        flash('Keine Berechtigung.', 'danger')
        return redirect(url_for('dashboard'))
    plants = Plant.query.filter_by(environment_id=env.id, user_id=current_user.id).all()
    logs = EnvironmentLog.query.filter_by(environment_id=env.id).all()
    logs_sorted = sorted(logs, key=lambda x: x.date, reverse=True)
    return render_template('environment_overview.html', env=env, plants=plants, entries=logs_sorted)

from app.forms import PlantForm
from flask_wtf import FlaskForm
from wtforms import SelectField, MultipleFileField, SubmitField
from wtforms.validators import DataRequired
from flask_wtf.file import FileAllowed


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
    if form.validate_on_submit():
        log = PlantLog(plant_id=form.plant_id.data, date=form.date.data, notes=form.notes.data)
        db.session.add(log)
        db.session.commit()
        from app.models import Measurement
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
        flash('Log-Eintrag hinzugefügt.', 'success')
        return redirect(url_for('dashboard'))
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
    if form.validate_on_submit():
        log = EnvironmentLog(environment_id=form.env_id.data, date=form.date.data, notes=form.notes.data)
        db.session.add(log)
        db.session.commit()
        from app.models import Measurement
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
        flash('Log-Eintrag hinzugefügt.', 'success')
        return redirect(url_for('dashboard'))
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
    class ImageUploadForm(FlaskForm):
        target = SelectField('Ziel', choices=choices, validators=[DataRequired()])
        images = MultipleFileField('Bilder', validators=[FileAllowed(['jpg', 'jpeg', 'png'], 'Nur Bilder erlaubt!')])
        submit = SubmitField('Hochladen')
    form = ImageUploadForm()
    if request.method == 'POST':
        form = ImageUploadForm(request.form)
        form.target.data = request.form.get('target')
        form.images.data = request.files.getlist('images')
        if form.validate_on_submit():
            from app.models import PlantImage, EnvironmentImage
            files = form.images.data
            target = form.target.data
            if target.startswith('plant-'):
                plant_id = int(target.split('-')[1])
                for file in files:
                    if file and file.filename:
                        filename = secure_filename(str(uuid.uuid4()) + '_' + file.filename)
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                        img = PlantImage(plant_id=plant_id, filename=filename)
                        db.session.add(img)
            elif target.startswith('env-'):
                env_id = int(target.split('-')[1])
                for file in files:
                    if file and file.filename:
                        filename = secure_filename(str(uuid.uuid4()) + '_' + file.filename)
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                        img = EnvironmentImage(environment_id=env_id, filename=filename)
                        db.session.add(img)
            db.session.commit()
            flash('Bilder hochgeladen.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('image_upload_form.html', form=form)