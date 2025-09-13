from app import db

class Lamp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    type = db.Column(db.String(50))  # LED, HPS, CFL, etc.
    power = db.Column(db.Integer)    # Watt
    kelvin = db.Column(db.Integer)   # Farbtemperatur

    environment = db.relationship('Environment', back_populates='lamps')
