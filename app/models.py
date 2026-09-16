from app import db
from flask_login import UserMixin
from datetime import datetime

class PlantActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey('plant.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    action = db.Column(db.String(50), nullable=False)
    plant = db.relationship('Plant', backref='action_logs')
class PlantLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey('plant.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    measurements = db.relationship('Measurement', backref='plant_log', lazy=True, cascade='all, delete-orphan')

class EnvironmentLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    measurements = db.relationship('Measurement', backref='environment_log', lazy=True, cascade='all, delete-orphan')

class Measurement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float)
    min_value = db.Column(db.Float)
    max_value = db.Column(db.Float)
    plant_log_id = db.Column(db.Integer, db.ForeignKey('plant_log.id'))
    environment_log_id = db.Column(db.Integer, db.ForeignKey('environment_log.id'))

class EnvironmentImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    plants = db.relationship('Plant', backref='owner', lazy=True)
    environments = db.relationship('Environment', backref='owner', lazy=True)

class Environment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    auto_watering = db.Column(db.Boolean, default=False)
    light_enabled = db.Column(db.Boolean, default=True)
    exposure_time = db.Column(db.Integer, default=18)  # Stunden 0-24
    notes = db.Column(db.Text)
    images = db.relationship('EnvironmentImage', backref='environment', lazy=True, cascade='all, delete-orphan', foreign_keys='EnvironmentImage.environment_id')
    preview_image_id = db.Column(db.Integer, db.ForeignKey('environment_image.id'), nullable=True)
    length = db.Column(db.Float)  # Meter
    width = db.Column(db.Float)
    height = db.Column(db.Float)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plants = db.relationship('Plant', backref='environment', lazy=True)
    lamps = db.relationship('Lamp', back_populates='environment', cascade='all, delete-orphan')

class PlantImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey('plant.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)

class Plant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pflanzenname = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date)  # statt plant_date
    count = db.Column(db.Integer, default=1)  # Anzahl der Pflanzen
    medium_type = db.Column(db.String(20))  # Erde, Hydro, Kokos
    medium_notes = db.Column(db.Text)  # Medienbeschreibung/Notizen
    strain = db.Column(db.String(100), default='Unbekannter Strain')
    phase = db.Column(db.String(20))  # Keimung, Sämling, Wachstum, Blüte, Trocknung, Fermentierung
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    images = db.relationship('PlantImage', backref='plant', lazy=True, cascade='all, delete-orphan', foreign_keys='PlantImage.plant_id')
    preview_image_id = db.Column(db.Integer, db.ForeignKey('plant_image.id'), nullable=True)
    actions = db.relationship('PlantActionLog', backref='plant_action_parent', cascade='all, delete-orphan')
