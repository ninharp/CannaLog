"""Token-authenticated JSON API for automation (Home Assistant, panels)."""
import hashlib
import secrets
from datetime import date as dt_date, datetime, time as dt_time
from functools import wraps

from flask import Blueprint, g, jsonify, request


def hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def new_token():
    return 'cl_' + secrets.token_urlsafe(32)


api = Blueprint('api_v1', __name__, url_prefix='/api/v1')


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


@api.errorhandler(ApiError)
def handle_api_error(error):
    from app import db
    db.session.rollback()
    return jsonify(error=error.message), error.status


def _types(choices):
    return {key for key, _ in choices if key}


def token_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from app import db
        from app.models import User
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            raise ApiError(401, 'Token fehlt.')
        user = User.query.filter_by(api_token_hash=hash_token(header[7:].strip())).first()
        if user is None:
            raise ApiError(401, 'Token ungültig.')
        user.api_token_last_used = datetime.utcnow()
        db.session.commit()
        g.api_user = user
        return view(*args, **kwargs)
    return wrapped


def _body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(422, 'JSON-Objekt erwartet.')
    return data


def _when(data):
    """(date, time, notes) from the common fields; date defaults to today."""
    raw_date, raw_time = data.get('date'), data.get('time')
    try:
        day = dt_date.fromisoformat(raw_date) if raw_date else dt_date.today()
    except (TypeError, ValueError):
        raise ApiError(422, 'Datum muss das Format JJJJ-MM-TT haben.')
    clock = None
    if raw_time:
        try:
            clock = datetime.strptime(raw_time, '%H:%M').time()
        except (TypeError, ValueError):
            raise ApiError(422, 'Uhrzeit muss das Format HH:MM haben.')
    notes = data.get('notes') or None
    if notes is not None and not isinstance(notes, str):
        raise ApiError(422, 'Notiz muss Text sein.')
    return day, clock, notes


def _environment(env_id):
    from app.models import Environment
    env = None
    if isinstance(env_id, int) and not isinstance(env_id, bool):
        env = Environment.query.filter_by(id=env_id, user_id=g.api_user.id).first()
    if env is None:
        raise ApiError(404, 'Umgebung nicht gefunden.')
    return env


def _target_plants(data):
    """Plants addressed by exactly one of plant_id / environment_id."""
    from app.models import Plant
    plant_id, env_id = data.get('plant_id'), data.get('environment_id')
    if (plant_id is None) == (env_id is None):
        raise ApiError(422, 'Genau eines von plant_id oder environment_id angeben.')
    if plant_id is not None:
        plant = None
        if isinstance(plant_id, int) and not isinstance(plant_id, bool):
            plant = Plant.query.filter_by(id=plant_id, user_id=g.api_user.id).first()
        if plant is None:
            raise ApiError(404, 'Pflanze nicht gefunden.')
        return [plant]
    plants = list(_environment(env_id).plants)
    if not plants:
        raise ApiError(422, 'Keine Pflanzen in dieser Umgebung.')
    return plants


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError(422, 'Messwerte müssen Zahlen sein.')
    return float(value)


def _measurements(values, allowed, ranges=False):
    """Measurement rows from {type: number} or, with ranges, {type: {value, min, max}}."""
    from app.models import Measurement
    if not isinstance(values, dict) or not values:
        raise ApiError(422, 'Mindestens ein Messwert in values erwartet.')
    rows = []
    for kind, raw in values.items():
        if kind not in allowed:
            raise ApiError(422, f'Unbekannter Messwert: {kind}.')
        if ranges and isinstance(raw, dict):
            if not raw or set(raw) - {'value', 'min', 'max'}:
                raise ApiError(422, f'{kind}: erlaubt sind value, min und max.')
            parts = {key: _number(raw[key]) for key in raw}
            rows.append(Measurement(type=kind, value=parts.get('value'),
                                    min_value=parts.get('min'), max_value=parts.get('max')))
        else:
            rows.append(Measurement(type=kind, value=_number(raw)))
    return rows


def _latest(plants, kind):
    best = None
    for plant in plants:
        for log in plant.logs:
            for m in log.measurements:
                if m.type != kind or m.value is None:
                    continue
                key = (log.date, log.time or dt_time.min)
                if best is None or key > best[0]:
                    best = (key, m.value, log)
    if best is None:
        return None
    _, value, log = best
    return {'value': value, 'date': log.date.isoformat(),
            'time': log.time.strftime('%H:%M') if log.time else None}


@api.route('/status')
@token_required
def status():
    from app import APP_VERSION
    return jsonify(version=APP_VERSION, user=g.api_user.username)


@api.route('/environments')
@token_required
def environments():
    from app.models import Environment
    result = []
    for env in Environment.query.filter_by(user_id=g.api_user.id).order_by(Environment.id):
        plants = list(env.plants)
        result.append({
            'id': env.id,
            'name': env.name,
            'plants': [{'id': p.id, 'name': p.pflanzenname, 'phase': p.phase} for p in plants],
            'latest': {kind: _latest(plants, kind) for kind in ('ph', 'ec')},
        })
    return jsonify(result)


@api.route('/actions', methods=['POST'])
@token_required
def create_actions():
    from app import db
    from app.forms import PLANT_ACTIONS
    from app.models import PlantActionLog
    data = _body()
    plants = _target_plants(data)
    action = data.get('action')
    if action not in _types(PLANT_ACTIONS):
        raise ApiError(422, 'Unbekannte Aktion.')
    day, clock, notes = _when(data)
    for plant in plants:
        db.session.add(PlantActionLog(plant_id=plant.id, date=day, time=clock, action=action, notes=notes))
    db.session.commit()
    return jsonify(created=len(plants), plants=[p.pflanzenname for p in plants]), 201


@api.route('/measurements', methods=['POST'])
@token_required
def create_measurements():
    from app import db
    from app.forms import MEASUREMENT_TYPES
    from app.models import PlantLog
    data = _body()
    plants = _target_plants(data)
    day, clock, notes = _when(data)
    allowed = _types(MEASUREMENT_TYPES)
    for plant in plants:
        log = PlantLog(plant_id=plant.id, date=day, time=clock, notes=notes)
        log.measurements = _measurements(data.get('values'), allowed)
        db.session.add(log)
    db.session.commit()
    return jsonify(created=len(plants), plants=[p.pflanzenname for p in plants]), 201


@api.route('/environment-logs', methods=['POST'])
@token_required
def create_environment_log():
    from app import db
    from app.forms import ENV_MEASUREMENT_TYPES
    from app.models import EnvironmentLog
    data = _body()
    env = _environment(data.get('environment_id'))
    day, clock, notes = _when(data)
    log = EnvironmentLog(environment_id=env.id, date=day, time=clock, notes=notes)
    log.measurements = _measurements(data.get('values'), _types(ENV_MEASUREMENT_TYPES), ranges=True)
    db.session.add(log)
    db.session.commit()
    return jsonify(created=1), 201
