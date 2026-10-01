"""API token lifecycle and the /api/v1 endpoints."""
import os
import re
import tempfile

import pytest

os.environ.setdefault('CANNALOG_DATA_DIR', tempfile.mkdtemp())

from app import app as flask_app, db  # noqa: E402
from app.models import User  # noqa: E402
from app.schema import upgrade_schema  # noqa: E402


@pytest.fixture(scope='module')
def web():
    upgrade_schema()
    flask_app.config['WTF_CSRF_ENABLED'] = False
    with flask_app.test_client() as c:
        c.post('/register', data={'username': 'apiuser', 'password': 'geheim123',
                                  'confirm_password': 'geheim123'})
        c.post('/login', data={'username': 'apiuser', 'password': 'geheim123'})
        yield c
    # The database is shared with the other test modules, which expect empty tables
    # and ids starting at 1: leave nothing behind.
    with flask_app.app_context():
        for table in reversed(db.metadata.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()


def create_token(web):
    html = web.post('/account/api', data={'action': 'create'}, follow_redirects=True).get_data(as_text=True)
    match = re.search(r'cl_[A-Za-z0-9_\-]{20,}', html)
    assert match, 'token is shown once after creation'
    return match.group(0)


def test_token_page_requires_login():
    with flask_app.test_client() as anon:
        assert anon.get('/account/api').status_code == 302


def test_token_is_shown_once_and_stored_hashed(web):
    token = create_token(web)
    with flask_app.app_context():
        user = User.query.filter_by(username='apiuser').first()
        assert user.api_token_hash and user.api_token_hash != token
        assert len(user.api_token_hash) == 64
    assert token not in web.get('/account/api').get_data(as_text=True)


def test_new_token_replaces_old_one(web):
    first = create_token(web)
    second = create_token(web)
    assert first != second
    with flask_app.app_context():
        from app.api import hash_token
        user = User.query.filter_by(username='apiuser').first()
        assert user.api_token_hash == hash_token(second)


def test_revoke_removes_token(web):
    create_token(web)
    web.post('/account/api', data={'action': 'revoke'})
    with flask_app.app_context():
        assert User.query.filter_by(username='apiuser').first().api_token_hash is None


from datetime import date  # noqa: E402

from app.models import Environment, EnvironmentLog, Plant, PlantActionLog, PlantLog  # noqa: E402


@pytest.fixture(scope='module')
def api(web):
    web.post('/environment/add', data={'name': 'Zelt 1', 'exposure_time': '18', 'length': '80',
                                       'width': '80', 'height': '160'})
    web.post('/environment/add', data={'name': 'Leer', 'exposure_time': '18', 'length': '80',
                                       'width': '80', 'height': '160'})
    with flask_app.app_context():
        env = Environment.query.filter_by(name='Zelt 1').first().id
        empty = Environment.query.filter_by(name='Leer').first().id
    for name in ('Amnesia', 'Kush'):
        web.post('/plant/add', data={'pflanzenname': name, 'date': '2026-08-20', 'count': '1',
                                     'medium_type': 'erde', 'phase': 'Wachstum', 'environment_id': str(env)})
    token = create_token(web)
    with flask_app.app_context():
        plants = {p.pflanzenname: p.id for p in Plant.query.filter_by(environment_id=env)}
    client = flask_app.test_client()  # no session cookie

    def call(method, path, json=None, token_value=token):
        headers = {'Authorization': f'Bearer {token_value}'} if token_value else {}
        return client.open(f'/api/v1{path}', method=method, json=json, headers=headers)

    return {'call': call, 'env': env, 'empty': empty, 'plants': plants}


def test_status(api):
    r = api['call']('GET', '/status')
    assert r.status_code == 200
    assert r.get_json()['user'] == 'apiuser'
    assert 'version' in r.get_json()


@pytest.mark.parametrize('token_value', [None, 'cl_falsch'])
def test_missing_or_wrong_token_is_rejected(api, token_value):
    r = api['call']('GET', '/status', token_value=token_value)
    assert r.status_code == 401
    assert 'error' in r.get_json()


def test_environments_list_plants(api):
    envs = api['call']('GET', '/environments').get_json()
    zelt = next(e for e in envs if e['id'] == api['env'])
    assert zelt['name'] == 'Zelt 1'
    assert sorted(p['name'] for p in zelt['plants']) == ['Amnesia', 'Kush']
    assert zelt['latest'] == {'ph': None, 'ec': None}


def test_action_for_environment_creates_one_entry_per_plant(api):
    r = api['call']('POST', '/actions', {'environment_id': api['env'], 'action': 'wasser',
                                          'date': '2026-10-01', 'time': '08:00', 'notes': 'automatisch'})
    assert r.status_code == 201
    assert r.get_json()['created'] == 2
    assert sorted(r.get_json()['plants']) == ['Amnesia', 'Kush']
    with flask_app.app_context():
        logs = PlantActionLog.query.filter_by(date=date(2026, 10, 1), action='wasser').all()
        assert len(logs) == 2
        assert {log.time.strftime('%H:%M') for log in logs} == {'08:00'}
        assert {log.notes for log in logs} == {'automatisch'}


def test_action_for_single_plant(api):
    r = api['call']('POST', '/actions', {'plant_id': api['plants']['Kush'], 'action': 'training'})
    assert r.status_code == 201
    assert r.get_json() == {'created': 1, 'plants': ['Kush']}
    with flask_app.app_context():
        log = PlantActionLog.query.filter_by(action='training').one()
        assert log.date == date.today() and log.time is None


def test_measurement_for_environment(api):
    r = api['call']('POST', '/measurements', {'environment_id': api['env'], 'time': '18:05',
                                               'date': '2026-10-01', 'values': {'ph': 6.2, 'ec': 1.4}})
    assert r.status_code == 201 and r.get_json()['created'] == 2
    with flask_app.app_context():
        log = PlantLog.query.filter_by(plant_id=api['plants']['Amnesia'], date=date(2026, 10, 1)).one()
        assert {m.type: m.value for m in log.measurements} == {'ph': 6.2, 'ec': 1.4}
    latest = next(e for e in api['call']('GET', '/environments').get_json() if e['id'] == api['env'])['latest']
    assert latest['ph'] == {'value': 6.2, 'date': '2026-10-01', 'time': '18:05'}
    assert latest['ec']['value'] == 1.4


def test_environment_log_with_min_max(api):
    r = api['call']('POST', '/environment-logs', {
        'environment_id': api['env'], 'date': '2026-10-01', 'time': '23:55',
        'values': {'umgebungstemperatur': {'min': 19.8, 'max': 24.1}, 'vpd': 0.9,
                   'luftfeuchtigkeit': {'value': 70, 'min': 62, 'max': 75}}})
    assert r.status_code == 201 and r.get_json() == {'created': 1}
    with flask_app.app_context():
        log = EnvironmentLog.query.filter_by(environment_id=api['env'], date=date(2026, 10, 1)).one()
        by_type = {m.type: m for m in log.measurements}
        assert (by_type['umgebungstemperatur'].min_value, by_type['umgebungstemperatur'].max_value) == (19.8, 24.1)
        assert by_type['umgebungstemperatur'].value is None
        assert by_type['vpd'].value == 0.9
        assert (by_type['luftfeuchtigkeit'].value, by_type['luftfeuchtigkeit'].min_value) == (70, 62)


@pytest.mark.parametrize('path, payload', [
    ('/actions', {'action': 'wasser'}),                                  # no target
    ('/actions', {'plant_id': 1, 'environment_id': 1, 'action': 'wasser'}),  # both targets
    ('/actions', {'environment_id': 'ENV', 'action': 'fliegen'}),         # unknown action
    ('/actions', {'environment_id': 'ENV', 'action': 'wasser', 'time': '25:00'}),
    ('/actions', {'environment_id': 'ENV', 'action': 'wasser', 'date': '01.10.2026'}),
    ('/measurements', {'environment_id': 'ENV', 'values': {}}),
    ('/measurements', {'environment_id': 'ENV', 'values': {'ph': 'sauer'}}),
    ('/measurements', {'environment_id': 'ENV', 'values': {'co2': 400}}),  # not a plant type
    ('/environment-logs', {'environment_id': 'ENV', 'values': {'ph': 6}}),  # not an environment type
    ('/environment-logs', {'environment_id': 'ENV', 'values': {'vpd': {'avg': 1}}}),
])
def test_invalid_input_is_rejected(api, path, payload):
    payload = {k: (api['env'] if v == 'ENV' else v) for k, v in payload.items()}
    r = api['call']('POST', path, payload)
    assert r.status_code == 422, r.get_data(as_text=True)
    assert r.get_json()['error']


def test_empty_environment_is_rejected(api):
    r = api['call']('POST', '/actions', {'environment_id': api['empty'], 'action': 'wasser'})
    assert r.status_code == 422
    assert r.get_json()['error'] == 'Keine Pflanzen in dieser Umgebung.'


def test_body_must_be_json_object(api):
    r = api['call']('POST', '/actions', [1, 2])
    assert r.status_code == 422


def test_foreign_and_unknown_ids_are_not_found(api, web):
    with flask_app.app_context():
        from werkzeug.security import generate_password_hash
        other = User(username='fremd', password=generate_password_hash('geheim123'))
        db.session.add(other)
        db.session.commit()
        env = Environment(name='Fremd', user_id=other.id)
        db.session.add(env)
        db.session.commit()
        plant = Plant(pflanzenname='Fremdpflanze', user_id=other.id, environment_id=env.id)
        db.session.add(plant)
        db.session.commit()
        foreign_env, foreign_plant = env.id, plant.id
    assert api['call']('POST', '/actions', {'environment_id': foreign_env, 'action': 'wasser'}).status_code == 404
    assert api['call']('POST', '/actions', {'plant_id': foreign_plant, 'action': 'wasser'}).status_code == 404
    assert api['call']('POST', '/actions', {'plant_id': 99999, 'action': 'wasser'}).status_code == 404
    names = [e['name'] for e in api['call']('GET', '/environments').get_json()]
    assert 'Fremd' not in names


def test_token_use_is_recorded(api):
    api['call']('GET', '/status')
    with flask_app.app_context():
        assert User.query.filter_by(username='apiuser').first().api_token_last_used is not None
