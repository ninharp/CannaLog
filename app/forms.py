# --- Log-Export Formular ---
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from flask_login import current_user
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, DateField, IntegerField, FileField, SelectField, FloatField, FieldList, FormField, MultipleFileField, SelectMultipleField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Optional
from datetime import date as dt_date
from app.models import Plant

class LogExportForm(FlaskForm):
    environment_id = SelectField('Umgebung', coerce=int, validators=[DataRequired()])
    plant_ids = SelectMultipleField('Pflanzen', coerce=int)
    include_env_logs = BooleanField('Umgebungs-Logs', default=True)
    include_plant_logs = BooleanField('Pflanzen-Logs', default=True)
    include_action_logs = BooleanField('Aktions-Logs', default=True)
    as_pdf = BooleanField('Als PDF exportieren')
    submit = SubmitField('Exportieren')

# Aktionen für Pflanzenaktions-Log
PLANT_ACTIONS = [
    ('', '---'),
    ('wasser', 'Wasser geben'),
    ('naehrstoffe', 'Nährstoffe'),
    ('abwehrmittel', 'Abwehrmittel'),
    ('umtopfen', 'Umtopfen'),
    ('beschneiden', 'Beschneiden'),
    ('training', 'Training'),
    ('anbauflaeche', 'Anbauflaeche ändern'),
    ('spuelen', 'Spülen'),
    ('ernte', 'Ernte'),
    ('tot', 'Als tot erklären'),
    ('sonstiges', 'Sonstiges'),
]

class PlantActionLogForm(FlaskForm):
    class Meta:
        csrf = True
    plant_id = SelectField('Pflanze', coerce=int, validators=[DataRequired()])
    date = DateField('Datum', format='%Y-%m-%d', default=dt_date.today, validators=[DataRequired()])
    action = SelectField('Aktion', choices=PLANT_ACTIONS, validators=[DataRequired()])
    notes = TextAreaField('Notizen', validators=[Optional()])
    submit = SubmitField('Speichern')

# Messungstypen für Pflanzen-Log
MEASUREMENT_TYPES = [
    ('', '---'),
    ('hoehe', 'Höhe (cm)'),
    ('tds', 'TDS (ppm)'),
    ('ph', 'pH'),
    ('ec', 'EC (mS/cm)'),
    ('wassertemperatur', 'Wassertemperatur (°C)'),
    ('ppfd', 'PPFD (µmol/m²s)'),
]

# Messungstypen für Environment-Log
ENV_MEASUREMENT_TYPES = [
    ('', '---'),
    ('luftfeuchtigkeit', 'Luftfeuchtigkeit (%)'),
    ('umgebungstemperatur', 'Umgebungstemperatur (°C)'),
    ('aussentemperatur', 'Aussentemperatur (°C)'),
    ('lichtabstand', 'Lichtabstand (cm)'),
    ('co2', 'CO₂ (ppm)'),
    ('niederschlaege', 'Niederschläge (mm)'),
    ('durchschnittliche_ppfd', 'Durchschnittliche PPFD (µmol/m²s)'),
    ('vpd', 'VPD (kPa)'),
]

ENV_LAMP_TYPES = [
    ('led', 'LED'),
    ('hps', 'Hochdruck-Natriumdampf (HPS)'),
    ('cfl', 'Kompaktleuchstofflampe (CFL)'),
    ('mh', 'Metallhalogen (MH)'),
    ('sonstige', 'Sonstige')
]

ENV_MEDIA_TYPES = [
    ('erde', 'Erde'), 
    ('hydro', 'Hydro'), 
    ('kokos', 'Kokos')
]

ENV_PHASE_TYPES = [
    ('Keimung', 'Keimung'), 
    ('Sämling', 'Sämling'), 
    ('Wachstum', 'Wachstum'), 
    ('Blüte', 'Blüte'), 
    ('Trocknung', 'Trocknung'), 
    ('Fermentierung', 'Fermentierung')
]

class MeasurementForm(FlaskForm):
    class Meta:
        csrf = False
    type = SelectField('Messung', choices=MEASUREMENT_TYPES, validators=[Optional()])
    value = FloatField('Wert', validators=[Optional()], render_kw={"step": "any"})
    min_value = FloatField('Min', validators=[Optional()], render_kw={"step": "any"})
    max_value = FloatField('Max', validators=[Optional()], render_kw={"step": "any"})

# Für EnvironmentLog eigene MeasurementForm mit anderen Typen
class EnvironmentMeasurementForm(FlaskForm):
    class Meta:
        csrf = False
    type = SelectField('Messung', choices=ENV_MEASUREMENT_TYPES, validators=[Optional()])
    value = FloatField('Wert', validators=[Optional()], render_kw={"step": "any"})
    min_value = FloatField('Min', validators=[Optional()], render_kw={"step": "any"})
    max_value = FloatField('Max', validators=[Optional()], render_kw={"step": "any"})

class PlantLogForm(FlaskForm):
    class Meta:
        csrf = True
    date = DateField('Datum', format='%Y-%m-%d', default=dt_date.today, validators=[DataRequired()])
    notes = TextAreaField('Notizen', validators=[Optional()])
    measurements = FieldList(FormField(MeasurementForm), min_entries=1, max_entries=6)
    submit = SubmitField('Speichern')

class EnvironmentLogForm(FlaskForm):
    class Meta:
        csrf = True
    date = DateField('Datum', format='%Y-%m-%d', default=dt_date.today, validators=[DataRequired()])
    notes = TextAreaField('Notizen', validators=[Optional()])
    measurements = FieldList(FormField(EnvironmentMeasurementForm), min_entries=1, max_entries=6)
    submit = SubmitField('Speichern')

class LampForm(FlaskForm):
    class Meta:
        csrf = False
    type = SelectField('Lampentyp', choices=ENV_LAMP_TYPES, validators=[DataRequired()])
    power = IntegerField('Leistung (Watt)', validators=[DataRequired()])
    kelvin = IntegerField('Farbtemperatur (K)', validators=[Optional()])  # optional

class RegistrationForm(FlaskForm):
    username = StringField('Benutzername', validators=[DataRequired(), Length(min=3, max=150)])
    password = PasswordField('Passwort', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Passwort bestätigen', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrieren')

class LoginForm(FlaskForm):
    username = StringField('Benutzername', validators=[DataRequired()])
    password = PasswordField('Passwort', validators=[DataRequired()])
    remember = BooleanField('Angemeldet bleiben')
    submit = SubmitField('Login')

class PlantForm(FlaskForm):
    pflanzenname = StringField('Pflanzenname', validators=[DataRequired()])
    date = DateField('Datum', format='%Y-%m-%d', default=dt_date.today)
    count = IntegerField('Anzahl Pflanzen', default=1)
    medium_type = SelectField('Medientyp', choices=ENV_MEDIA_TYPES, validators=[DataRequired()])
    medium_notes = TextAreaField('Medienbeschreibung/Notizen')
    strain = StringField('Strain', default='Unbekannter Strain', render_kw={"autocomplete": "off"})
    phase = SelectField('Phase', choices=ENV_PHASE_TYPES, validators=[DataRequired()])
    notes = TextAreaField('Notizen')
    images = MultipleFileField('Bilder', validators=[FileAllowed(['jpg', 'jpeg', 'png'], 'Nur Bilder erlaubt!')])
    environment_id = SelectField('Umgebung', coerce=int)
    preview_image_id = IntegerField('Vorschaubild', validators=[Optional()])
    submit = SubmitField('Speichern')

class EnvironmentForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    auto_watering = BooleanField('Automatische Bewässerung')
    light_enabled = BooleanField('Lichtsteuerung aktiv')
    exposure_time = IntegerField('Belichtungszeit (0-24h)', default=18)
    notes = TextAreaField('Notizen')
    images = MultipleFileField('Bilder', validators=[FileAllowed(['jpg', 'jpeg', 'png'], 'Nur Bilder erlaubt!')])
    preview_image_id = IntegerField('Vorschaubild', validators=[Optional()])
    length = IntegerField('Länge (cm)')
    width = IntegerField('Breite (cm)')
    height = IntegerField('Höhe (cm)')
    lamps = FieldList(FormField(LampForm), min_entries=1, max_entries=10)
    submit = SubmitField('Speichern')
