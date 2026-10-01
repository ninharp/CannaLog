"""Token-authenticated JSON API for automation (Home Assistant, panels)."""
import hashlib
import math
import re
import secrets
from datetime import date as dt_date, datetime, timedelta
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.exceptions import HTTPException


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


API_PREFIX = '/api/v1/'
HTTP_MESSAGES = {
    400: 'Ungültige Anfrage.',
    401: 'Nicht angemeldet.',
    403: 'Zugriff verweigert.',
    404: 'Nicht gefunden.',
    405: 'Methode nicht erlaubt.',
    408: 'Zeitüberschreitung.',
    413: 'Anfrage zu groß.',
    415: 'Nicht unterstützter Inhaltstyp.',
    429: 'Zu viele Anfragen.',
    500: 'Interner Fehler.',
}


@api.app_errorhandler(HTTPException)
def handle_http_error(error):
    """JSON errors for everything below /api/v1/ (also unmatched URLs); the web UI keeps its pages."""
    if not request.path.startswith(API_PREFIX):
        return error
    from app import db
    code = error.code or 500
    if code >= 500:
        db.session.rollback()  # Flask has already logged the traceback via app.logger
    response = jsonify(error=HTTP_MESSAGES.get(code, 'Fehler bei der Anfrage.'))
    response.status_code = code
    allowed = getattr(error, 'valid_methods', None)
    if allowed:
        response.headers['Allow'] = ', '.join(allowed)
    return response


def _types(choices):
    return {key for key, _ in choices if key}


def _touch(user):
    """Record token use at most once a minute; a failing write must not break the request."""
    from app import db
    now = datetime.now()  # naive local time, like the rest of the app
    last = user.api_token_last_used
    if last is not None and now - last < timedelta(seconds=60):
        return
    try:
        user.api_token_last_used = now
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.warning('Could not record API token use', exc_info=True)


def token_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from app import db
        from app.models import User
        scheme, _, token = request.headers.get('Authorization', '').partition(' ')
        if scheme.lower() != 'bearer' or not token.strip():
            raise ApiError(401, 'Token fehlt.')
        user = User.query.filter_by(api_token_hash=hash_token(token.strip())).first()
        if user is None:
            raise ApiError(401, 'Token ungültig.')
        _touch(user)
        g.api_user = user
        return view(*args, **kwargs)
    return wrapped


def _body():
    data = request.get_json(force=True, silent=True)  # whatever the content type
    if not isinstance(data, dict):
        raise ApiError(422, 'JSON-Objekt erwartet.')
    return data


def _when(data):
    """(date, time, notes) from the common fields; date defaults to today.

    Only a missing key or null means "absent"; for time and notes an empty string does too.
    """
    raw_date, raw_time, raw_notes = data.get('date'), data.get('time'), data.get('notes')
    try:
        day = dt_date.today() if raw_date is None else dt_date.fromisoformat(raw_date)
    except (TypeError, ValueError):
        raise ApiError(422, 'Datum muss das Format JJJJ-MM-TT haben.')
    clock = None
    if raw_time is not None and raw_time != '':
        clock = None
        for fmt in ('%H:%M', '%H:%M:%S'):
            try:
                clock = datetime.strptime(raw_time, fmt).time().replace(second=0)  # seconds are dropped
                break
            except (TypeError, ValueError):
                continue
        if clock is None:
            raise ApiError(422, 'Uhrzeit muss das Format HH:MM haben.')
    if raw_notes is not None and not isinstance(raw_notes, str):
        raise ApiError(422, 'Notiz muss Text sein.')
    return day, clock, raw_notes or None


MAX_ID = 2 ** 63 - 1


def _id(value):
    """Integer id from an int or a string of decimal digits; None if out of database range."""
    if isinstance(value, str) and re.fullmatch(r'[0-9]+', value):
        if len(value) > 19:  # beyond the database range; do not even convert it
            return None
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(422, 'plant_id und environment_id müssen ganze Zahlen sein.')
    return value if 0 <= value <= MAX_ID else None


def _own_plants(env):
    from app.models import Plant
    return Plant.query.filter_by(environment_id=env.id, user_id=g.api_user.id).order_by(Plant.id).all()


def _environment(env_id):
    from app.models import Environment
    env_id = _id(env_id)
    env = None
    if env_id is not None:
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
        plant_id = _id(plant_id)
        plant = None
        if plant_id is not None:
            plant = Plant.query.filter_by(id=plant_id, user_id=g.api_user.id).first()
        if plant is None:
            raise ApiError(404, 'Pflanze nicht gefunden.')
        return [plant]
    plants = _own_plants(_environment(env_id))
    if not plants:
        raise ApiError(422, 'Keine Pflanzen in dieser Umgebung.')
    return plants


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError(422, 'Messwerte müssen Zahlen sein.')
    try:
        number = float(value)
    except OverflowError:
        raise ApiError(422, 'Messwerte müssen Zahlen sein.')
    if not math.isfinite(number):  # NaN and Infinity are accepted by Python's JSON parser
        raise ApiError(422, 'Messwerte müssen Zahlen sein.')
    return number


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


def _latest(env, kind):
    """Newest non-null value of a plant measurement type in an environment (one bounded query)."""
    from app import db
    from app.models import Measurement, Plant, PlantLog
    row = (db.session.query(Measurement.value, PlantLog.date, PlantLog.time)
           .join(PlantLog, Measurement.plant_log_id == PlantLog.id)
           .join(Plant, PlantLog.plant_id == Plant.id)
           .filter(Plant.environment_id == env.id, Plant.user_id == g.api_user.id,
                   Measurement.type == kind, Measurement.value.isnot(None))
           # entries without a time sort after timed ones of the same day; the log id breaks ties
           .order_by(PlantLog.date.desc(), PlantLog.time.is_(None), PlantLog.time.desc(), PlantLog.id.desc())
           .first())
    if row is None:
        return None
    value, day, clock = row
    return {'value': value, 'date': day.isoformat(), 'time': clock.strftime('%H:%M') if clock else None}


def _recent(env, limit):
    """Newest journal entries (actions and measurements) of the user's plants in an environment.

    Entries of several plants that are identical in kind, date, time, content and notes
    are merged into one item.
    """
    from app.forms import PLANT_ACTIONS
    from app.models import PlantActionLog, PlantLog
    plants = _own_plants(env)
    if not plants:
        return []
    names = {p.id: p.pflanzenname for p in plants}
    labels = dict(PLANT_ACTIONS)
    # each source can contribute at most `limit` groups, and a group spans at most len(plants) rows
    rows_max = limit * len(plants) + limit

    def newest(model):
        return (model.query.filter(model.plant_id.in_(list(names)))
                .order_by(model.date.desc(), model.time.is_(None), model.time.desc(), model.id.desc())
                .limit(rows_max).all())

    groups = {}

    def add(key, row, extra):
        group = groups.setdefault(key, {'row': row, 'plant_ids': set(), 'max_id': 0, **extra})
        group['plant_ids'].add(row.plant_id)
        group['max_id'] = max(group['max_id'], row.id)

    for row in newest(PlantActionLog):
        add(('action', row.date, row.time, row.action, row.notes or None), row, {'action': row.action})
    for row in newest(PlantLog):
        values = sorted((m.type, m.value) for m in row.measurements if m.value is not None)
        if values:
            add(('measurement', row.date, row.time, tuple(values), row.notes or None), row,
                {'values': dict(values)})

    def order(group):
        row = group['row']
        # newest first: date desc, untimed after timed of the same day, time desc, id desc
        return (row.date.toordinal(), row.time is not None,
                (row.time.hour * 60 + row.time.minute) if row.time else 0, group['max_id'])

    items = []
    for group in sorted(groups.values(), key=order, reverse=True)[:limit]:
        row = group['row']
        item = {'type': 'measurement' if 'values' in group else 'action',
                'date': row.date.isoformat(),
                'time': row.time.strftime('%H:%M') if row.time else None}
        if 'values' in group:
            item['values'] = group['values']
        else:
            item['action'] = group['action']
            item['label'] = labels.get(group['action'], group['action'])
        item['plants'] = sorted(names[i] for i in group['plant_ids'])
        item['all'] = group['plant_ids'] == set(names)
        item['notes'] = row.notes or None
        items.append(item)
    return items


@api.route('/status')
@token_required
def status():
    from app import APP_VERSION
    return jsonify(version=APP_VERSION, user=g.api_user.username)


@api.route('/environments')
@token_required
def environments():
    from app.models import Environment
    raw_recent = request.args.get('recent')
    recent = 0
    if raw_recent is not None:
        if not re.fullmatch(r'[0-9]{1,3}', raw_recent) or int(raw_recent) > 50:
            raise ApiError(422, 'recent muss eine ganze Zahl von 0 bis 50 sein.')
        recent = int(raw_recent)
    result = []
    for env in Environment.query.filter_by(user_id=g.api_user.id).order_by(Environment.id):
        plants = _own_plants(env)
        result.append({
            'id': env.id,
            'name': env.name,
            'plants': [{'id': p.id, 'name': p.pflanzenname, 'phase': p.phase} for p in plants],
            'latest': {kind: _latest(env, kind) for kind in ('ph', 'ec')},
        })
        if recent > 0:
            result[-1]['recent'] = _recent(env, recent)
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
    if not isinstance(action, str) or action not in _types(PLANT_ACTIONS):
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
    if data.get('environment_id') is None:
        raise ApiError(422, 'environment_id fehlt.')
    env = _environment(data.get('environment_id'))
    day, clock, notes = _when(data)
    log = EnvironmentLog(environment_id=env.id, date=day, time=clock, notes=notes)
    log.measurements = _measurements(data.get('values'), _types(ENV_MEASUREMENT_TYPES), ranges=True)
    db.session.add(log)
    db.session.commit()
    return jsonify(created=1), 201
