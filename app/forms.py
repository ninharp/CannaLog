# --- Log-Export Formular ---
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, DateField, IntegerField, SelectField, FloatField, FieldList, FormField, MultipleFileField, SelectMultipleField
from wtforms.validators import DataRequired, Length, EqualTo, Optional
from datetime import date as dt_date

class LogExportForm(FlaskForm):
    environment_id = SelectField('Umgebung', coerce=int, validators=[DataRequired()])
    plant_ids = SelectMultipleField('Pflanzen', coerce=int, validators=[Optional()])
    include_env_logs = BooleanField('Klimawerte der Umgebung', default=True)
    include_plant_logs = BooleanField('Messungen der Pflanzen', default=True)
    include_action_logs = BooleanField('Aktionen der Pflanzen', default=True)
    as_pdf = BooleanField('Als PDF exportieren')
    submit = SubmitField('Exportieren')

# Aktionen für Pflanzenaktions-Log
PLANT_ACTIONS = [
    ('', 'Aktion wählen'),
    ('wasser', 'Wasser geben'),
    ('naehrstoffe', 'Nährstoffe'),
    ('abwehrmittel', 'Abwehrmittel'),
    ('umtopfen', 'Umtopfen'),
    ('beschneiden', 'Beschneiden'),
    ('training', 'Training'),
    ('anbauflaeche', 'Anbaufläche ändern'),
    ('spuelen', 'Spülen'),
    ('ernte', 'Ernte'),
    ('tot', 'Als tot erklären'),
    ('sonstiges', 'Sonstiges'),
]

class PlantActionLogForm(FlaskForm):
    plant_id = SelectField('Pflanze', coerce=int, validators=[DataRequired()])
    date = DateField('Datum', format='%Y-%m-%d', default=dt_date.today, validators=[DataRequired()])
    action = SelectField('Aktion', choices=PLANT_ACTIONS, validators=[DataRequired()])
    notes = TextAreaField('Notizen', validators=[Optional()])
    submit = SubmitField('Speichern')

# Messungstypen für Pflanzen-Log
MEASUREMENT_TYPES = [
    ('', 'Messwert wählen'),
    ('hoehe', 'Höhe (cm)'),
    ('tds', 'TDS (ppm)'),
    ('ph', 'pH'),
    ('ec', 'EC (mS/cm)'),
    ('wassertemperatur', 'Wassertemperatur (°C)'),
    ('ppfd', 'PPFD (µmol/m²s)'),
]

# Messungstypen für Environment-Log
ENV_MEASUREMENT_TYPES = [
    ('', 'Messwert wählen'),
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
    ('cfl', 'Kompaktleuchtstofflampe (CFL)'),
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
    type = SelectField('Messwert', choices=MEASUREMENT_TYPES, validators=[Optional()])
    value = FloatField('Wert', validators=[Optional()], render_kw={"step": "any"})
    min_value = FloatField('Min', validators=[Optional()], render_kw={"step": "any"})
    max_value = FloatField('Max', validators=[Optional()], render_kw={"step": "any"})

# Für EnvironmentLog eigene MeasurementForm mit anderen Typen
class EnvironmentMeasurementForm(FlaskForm):
    class Meta:
        csrf = False
    type = SelectField('Messwert', choices=ENV_MEASUREMENT_TYPES, validators=[Optional()])
    value = FloatField('Wert', validators=[Optional()], render_kw={"step": "any"})
    min_value = FloatField('Min', validators=[Optional()], render_kw={"step": "any"})
    max_value = FloatField('Max', validators=[Optional()], render_kw={"step": "any"})

class PlantLogForm(FlaskForm):
    date = DateField('Datum', format='%Y-%m-%d', default=dt_date.today, validators=[DataRequired()])
    notes = TextAreaField('Notizen', validators=[Optional()])
    measurements = FieldList(FormField(MeasurementForm), min_entries=1, max_entries=6)
    submit = SubmitField('Speichern')

class EnvironmentLogForm(FlaskForm):
    date = DateField('Datum', format='%Y-%m-%d', default=dt_date.today, validators=[DataRequired()])
    notes = TextAreaField('Notizen', validators=[Optional()])
    measurements = FieldList(FormField(EnvironmentMeasurementForm), min_entries=1, max_entries=6)
    submit = SubmitField('Speichern')

class LampForm(FlaskForm):
    class Meta:
        csrf = False
    type = SelectField('Lampentyp', choices=ENV_LAMP_TYPES, validators=[Optional()])
    power = IntegerField('Leistung (W)', validators=[Optional()])
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
    submit = SubmitField('Anmelden')

class PlantForm(FlaskForm):
    pflanzenname = StringField('Pflanzenname', validators=[DataRequired()])
    date = DateField('Startdatum', format='%Y-%m-%d', default=dt_date.today, validators=[Optional()])
    count = IntegerField('Anzahl Pflanzen', default=1, validators=[Optional()])
    medium_type = SelectField('Medium', choices=ENV_MEDIA_TYPES, validators=[DataRequired()])
    medium_notes = TextAreaField('Beschreibung', validators=[Optional()])
    strain = StringField('Sorte (Strain)', validators=[Optional()], render_kw={"autocomplete": "off", "placeholder": "Unbekannter Strain"})
    phase = SelectField('Phase', choices=ENV_PHASE_TYPES, validators=[DataRequired()])
    notes = TextAreaField('Notizen')
    images = MultipleFileField('Fotos', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Nur Bilddateien (JPG, PNG, GIF, WebP).')])
    environment_id = SelectField('Umgebung', coerce=int)
    preview_image_id = IntegerField('Vorschaubild', validators=[Optional()])
    submit = SubmitField('Speichern')

class EnvironmentForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    auto_watering = BooleanField('Automatische Bewässerung')
    light_enabled = BooleanField('Mit Lampe und festem Lichtzyklus')
    exposure_time = IntegerField('Lichtstunden pro Tag', default=18, validators=[Optional()])
    notes = TextAreaField('Notizen')
    images = MultipleFileField('Fotos', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Nur Bilddateien (JPG, PNG, GIF, WebP).')])
    preview_image_id = IntegerField('Vorschaubild', validators=[Optional()])
    length = IntegerField('Länge (cm)', validators=[Optional()])
    width = IntegerField('Breite (cm)', validators=[Optional()])
    height = IntegerField('Höhe (cm)', validators=[Optional()])
    lamps = FieldList(FormField(LampForm), min_entries=1, max_entries=10)
    submit = SubmitField('Speichern')
