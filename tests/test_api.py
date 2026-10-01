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


def test_token_page_is_never_cached(web):
    created = web.post('/account/api', data={'action': 'create'})
    assert 'no-store' in created.headers.get('Cache-Control', '')
    assert 'no-store' in web.get('/account/api').headers.get('Cache-Control', '')


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

    def raw(method, path, body, token_value=token):
        headers = {'Authorization': f'Bearer {token_value}'}
        return client.open(f'/api/v1{path}', method=method, data=body,
                           content_type='application/json', headers=headers)

    return {'call': call, 'raw': raw, 'client': client, 'token': token, 'web': web,
            'env': env, 'empty': empty, 'plants': plants}


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


@pytest.fixture(scope='module')
def foreign(api):
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
        return {'env': env.id, 'plant': plant.id}


def test_foreign_and_unknown_ids_are_not_found(api, foreign):
    assert api['call']('POST', '/actions', {'environment_id': foreign['env'], 'action': 'wasser'}).status_code == 404
    assert api['call']('POST', '/actions', {'plant_id': foreign['plant'], 'action': 'wasser'}).status_code == 404
    assert api['call']('POST', '/actions', {'plant_id': 99999, 'action': 'wasser'}).status_code == 404
    names = [e['name'] for e in api['call']('GET', '/environments').get_json()]
    assert 'Fremd' not in names


def test_token_use_is_recorded(api):
    api['call']('GET', '/status')
    with flask_app.app_context():
        assert User.query.filter_by(username='apiuser').first().api_token_last_used is not None


# --- hardening (fix round 1) ---

def _counts():
    from app.models import Measurement
    with flask_app.app_context():
        return (PlantActionLog.query.count(), PlantLog.query.count(), Measurement.query.count(),
                EnvironmentLog.query.count())


@pytest.mark.parametrize('action', [[], {}, 5, None, True])
def test_non_string_action_is_rejected(api, action):
    r = api['call']('POST', '/actions', {'environment_id': api['env'], 'action': action})
    assert r.status_code == 422
    assert r.get_json()['error'] == 'Unbekannte Aktion.'


@pytest.mark.parametrize('literal', ['NaN', 'Infinity', '-Infinity', '1e999', '1' + '0' * 400])
def test_non_finite_and_overflowing_numbers_are_rejected(api, literal):
    before = _counts()
    body = '{"environment_id": %d, "values": {"ph": %s}}' % (api['env'], literal)
    r = api['raw']('POST', '/measurements', body)
    assert r.status_code == 422, r.get_data(as_text=True)
    assert r.get_json()['error'] == 'Messwerte müssen Zahlen sein.'
    body = '{"environment_id": %d, "values": {"vpd": {"max": %s}}}' % (api['env'], literal)
    assert api['raw']('POST', '/environment-logs', body).status_code == 422
    assert _counts() == before


def test_huge_ids_are_not_found(api):
    assert api['call']('POST', '/actions', {'plant_id': 2 ** 70, 'action': 'wasser'}).status_code == 404
    assert api['call']('POST', '/actions', {'environment_id': 2 ** 70, 'action': 'wasser'}).status_code == 404
    assert api['call']('POST', '/environment-logs', {'environment_id': 2 ** 70, 'values': {'vpd': 1}}).status_code == 404
    assert api['call']('POST', '/actions', {'plant_id': str(2 ** 70), 'action': 'wasser'}).status_code == 404


def test_ids_may_be_digit_strings(api):
    r = api['call']('POST', '/actions', {'environment_id': str(api['env']), 'action': 'spuelen'})
    assert r.status_code == 201 and r.get_json()['created'] == 2
    r = api['call']('POST', '/actions', {'plant_id': str(api['plants']['Kush']), 'action': 'ernte'})
    assert r.status_code == 201 and r.get_json() == {'created': 1, 'plants': ['Kush']}
    r = api['call']('POST', '/environment-logs', {'environment_id': str(api['env']), 'values': {'vpd': 1.0}})
    assert r.status_code == 201


@pytest.mark.parametrize('bad', [1.5, True, [1], {'a': 1}, 'abc', '1.5', '-1', ' 1', ''])
@pytest.mark.parametrize('key', ['plant_id', 'environment_id'])
def test_malformed_ids_are_rejected(api, key, bad):
    r = api['call']('POST', '/actions', {key: bad, 'action': 'wasser'})
    assert r.status_code == 422
    assert r.get_json()['error'] == 'plant_id und environment_id müssen ganze Zahlen sein.'


def test_exactly_one_target_is_checked_first(api):
    r = api['call']('POST', '/actions', {'plant_id': 1.5, 'environment_id': 1, 'action': 'wasser'})
    assert r.status_code == 422
    assert 'Genau eines' in r.get_json()['error']


def test_unknown_api_path_is_json_404(api):
    r = api['call']('GET', '/foo')
    assert r.status_code == 404 and r.is_json
    assert r.get_json() == {'error': 'Nicht gefunden.'}
    r = api['client'].get('/api/v1/foo')  # without a token as well
    assert r.status_code == 404 and r.is_json


def test_wrong_method_is_json_405(api):
    r = api['call']('POST', '/status')
    assert r.status_code == 405 and r.is_json
    assert r.get_json() == {'error': 'Methode nicht erlaubt.'}


def test_oversized_body_is_json_413(api):
    old = flask_app.config['MAX_CONTENT_LENGTH']
    flask_app.config['MAX_CONTENT_LENGTH'] = 100
    try:
        r = api['raw']('POST', '/actions', '{"notes": "' + 'x' * 500 + '"}')
    finally:
        flask_app.config['MAX_CONTENT_LENGTH'] = old
    assert r.status_code == 413 and r.is_json
    assert r.get_json()['error']


def test_unexpected_exception_is_json_500(api, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('kaputt')
    monkeypatch.setattr('app.api._target_plants', boom)
    flask_app.config['PROPAGATE_EXCEPTIONS'] = False
    try:
        r = api['call']('POST', '/actions', {'environment_id': api['env'], 'action': 'wasser'})
    finally:
        flask_app.config['PROPAGATE_EXCEPTIONS'] = None
    assert r.status_code == 500 and r.get_json() == {'error': 'Interner Fehler.'}


def test_web_ui_errors_stay_html(api):
    r = api['client'].get('/gibt-es-nicht')
    assert r.status_code == 404
    assert not r.is_json and b'<' in r.data
    # a path that merely starts with the same letters is not part of the API
    assert not api['client'].get('/api/v10/x').is_json


def test_rejected_multi_plant_request_persists_nothing(api):
    before = _counts()
    r = api['call']('POST', '/measurements', {'environment_id': api['env'],
                                               'values': {'ph': 6.0, 'ec': 'viel'}})
    assert r.status_code == 422
    r = api['call']('POST', '/measurements', {'environment_id': api['env'], 'time': '99:00',
                                               'values': {'ph': 6.0}})
    assert r.status_code == 422
    assert _counts() == before


def test_foreign_environment_on_logs_is_not_found(api, foreign):
    before = _counts()
    assert api['call']('POST', '/measurements', {'environment_id': foreign['env'],
                                                  'values': {'ph': 6}}).status_code == 404
    assert api['call']('POST', '/environment-logs', {'environment_id': foreign['env'],
                                                      'values': {'vpd': 1}}).status_code == 404
    assert _counts() == before


def test_environment_only_uses_own_plants(api, foreign):
    """A foreign plant stuck in the user's environment must not be written to."""
    with flask_app.app_context():
        stray = Plant(pflanzenname='Streuner', user_id=User.query.filter_by(username='fremd').one().id,
                      environment_id=api['env'])
        db.session.add(stray)
        db.session.commit()
        stray_id = stray.id
    try:
        r = api['call']('POST', '/actions', {'environment_id': api['env'], 'action': 'sonstiges'})
        assert r.status_code == 201
        assert sorted(r.get_json()['plants']) == ['Amnesia', 'Kush']
        with flask_app.app_context():
            assert PlantActionLog.query.filter_by(plant_id=stray_id).count() == 0
    finally:
        with flask_app.app_context():
            db.session.delete(db.session.get(Plant, stray_id))
            db.session.commit()


def test_latest_values_prefer_newest_date_then_time_then_creation(api, web):
    from app.models import Measurement
    web.post('/environment/add', data={'name': 'Latest', 'exposure_time': '18', 'length': '80',
                                       'width': '80', 'height': '160'})
    with flask_app.app_context():
        env = Environment.query.filter_by(name='Latest').one().id
    web.post('/plant/add', data={'pflanzenname': 'Eins', 'date': '2026-08-20', 'count': '1',
                                 'medium_type': 'erde', 'phase': 'Wachstum', 'environment_id': str(env)})
    web.post('/plant/add', data={'pflanzenname': 'Zwei', 'date': '2026-08-20', 'count': '1',
                                 'medium_type': 'erde', 'phase': 'Wachstum', 'environment_id': str(env)})
    from datetime import time as dt_time
    with flask_app.app_context():
        one, two = [p.id for p in Plant.query.filter_by(environment_id=env).order_by(Plant.id)]

        def add(plant, day, clock, kind, value):
            log = PlantLog(plant_id=plant, date=day, time=clock)
            log.measurements = [Measurement(type=kind, value=value)]
            db.session.add(log)
            db.session.commit()

        # same day: the entry with a time beats the one without, even if created later
        add(one, date(2026, 11, 1), dt_time(7, 0), 'ph', 6.0)
        add(two, date(2026, 11, 1), None, 'ph', 5.0)
        add(one, date(2026, 10, 31), dt_time(23, 0), 'ph', 4.0)   # older day never wins
        # same date and time: the later-created one wins
        add(one, date(2026, 11, 2), dt_time(8, 0), 'ec', 1.0)
        add(two, date(2026, 11, 2), dt_time(8, 0), 'ec', 2.0)
        # NULL values are ignored
        log = PlantLog(plant_id=one, date=date(2026, 12, 1))
        log.measurements = [Measurement(type='ec', value=None, min_value=1.0)]
        db.session.add(log)
        db.session.commit()
    latest = next(e for e in api['call']('GET', '/environments').get_json() if e['id'] == env)['latest']
    assert latest['ph'] == {'value': 6.0, 'date': '2026-11-01', 'time': '07:00'}
    assert latest['ec'] == {'value': 2.0, 'date': '2026-11-02', 'time': '08:00'}


def test_untimed_entry_wins_on_a_newer_day(api):
    from app.models import Measurement
    with flask_app.app_context():
        env = Environment.query.filter_by(name='Latest').one().id
        plant = Plant.query.filter_by(environment_id=env).first().id
        log = PlantLog(plant_id=plant, date=date(2026, 11, 3))
        log.measurements = [Measurement(type='ph', value=7.0)]
        db.session.add(log)
        db.session.commit()
    latest = next(e for e in api['call']('GET', '/environments').get_json() if e['id'] == env)['latest']
    assert latest['ph'] == {'value': 7.0, 'date': '2026-11-03', 'time': None}


def test_scheme_is_case_insensitive(api):
    r = api['client'].get('/api/v1/status', headers={'Authorization': f"bearer {api['token']}"})
    assert r.status_code == 200
    r = api['client'].get('/api/v1/status', headers={'Authorization': f"Basic {api['token']}"})
    assert r.status_code == 401


def test_empty_strings_mean_absent_and_falsy_values_are_rejected(api):
    r = api['call']('POST', '/actions', {'plant_id': api['plants']['Kush'], 'action': 'wasser',
                                          'time': '', 'notes': ''})
    assert r.status_code == 201
    r = api['call']('POST', '/actions', {'plant_id': api['plants']['Kush'], 'action': 'wasser',
                                          'time': None, 'notes': None, 'date': None})
    assert r.status_code == 201
    for field, value in [('time', False), ('time', 0), ('notes', 0), ('notes', []), ('date', 0),
                         ('date', ''), ('date', False)]:
        r = api['call']('POST', '/actions', {'plant_id': api['plants']['Kush'], 'action': 'wasser',
                                              field: value})
        assert r.status_code == 422, (field, value)


def test_token_use_is_written_at_most_once_a_minute(api):
    from datetime import datetime, timedelta
    with flask_app.app_context():
        user = User.query.filter_by(username='apiuser').one()
        user.api_token_last_used = datetime.now() - timedelta(seconds=10)
        stamp = user.api_token_last_used
        db.session.commit()
    db.session.expire_all()  # requests share the fixture's app context and its session
    api['call']('GET', '/status')
    with flask_app.app_context():
        assert User.query.filter_by(username='apiuser').one().api_token_last_used == stamp
        user = User.query.filter_by(username='apiuser').one()
        user.api_token_last_used = datetime.now() - timedelta(minutes=5)
        db.session.commit()
    db.session.expire_all()
    api['call']('GET', '/status')
    with flask_app.app_context():
        assert User.query.filter_by(username='apiuser').one().api_token_last_used > datetime.now() - timedelta(seconds=30)


def test_failing_last_used_commit_does_not_break_reads(api, monkeypatch):
    from datetime import datetime, timedelta
    with flask_app.app_context():
        user = User.query.filter_by(username='apiuser').one()
        user.api_token_last_used = datetime.now() - timedelta(minutes=5)
        db.session.commit()
    db.session.expire_all()
    real_commit = db.session.commit
    calls = []

    def failing_commit():
        calls.append(1)
        raise RuntimeError('database is locked')
    monkeypatch.setattr(db.session, 'commit', failing_commit)
    try:
        r = api['call']('GET', '/status')
    finally:
        monkeypatch.setattr(db.session, 'commit', real_commit)
    assert calls and r.status_code == 200


# --- final review fixes ---

@pytest.mark.parametrize('content_type', [None, 'text/plain'])
def test_json_body_is_parsed_whatever_the_content_type(api, content_type):
    before = _counts()
    headers = {'Authorization': f"Bearer {api['token']}"}
    kwargs = {'content_type': content_type} if content_type else {}
    r = api['client'].post('/api/v1/actions', data='{"plant_id": %d, "action": "wasser"}' % api['plants']['Kush'],
                           headers=headers, **kwargs)
    assert r.status_code == 201, r.get_data(as_text=True)
    assert _counts()[0] == before[0] + 1
    for body in ('kein json', '[1, 2]', ''):
        r = api['client'].post('/api/v1/actions', data=body, headers=headers, **kwargs)
        assert r.status_code == 422 and r.get_json()['error'] == 'JSON-Objekt erwartet.', body


def test_token_use_is_stored_in_local_time(api):
    from datetime import datetime, timedelta
    with flask_app.app_context():
        user = User.query.filter_by(username='apiuser').one()
        user.api_token_last_used = None
        db.session.commit()
    db.session.expire_all()
    api['call']('GET', '/status')
    with flask_app.app_context():
        stamp = User.query.filter_by(username='apiuser').one().api_token_last_used
    assert abs(datetime.now() - stamp) < timedelta(seconds=30)


def test_example_call_on_token_page_direct_port(web):
    html = web.get('/account/api', environ_base={'REMOTE_ADDR': '192.168.1.50'}).get_data(as_text=True)
    assert 'http://localhost/api/v1/status' in html
    assert 'direkten Port' not in html


def test_example_call_on_token_page_behind_ingress(web):
    prefix = '/api/hassio_ingress/TESTTOKEN'
    html = web.get('/account/api', headers={'X-Ingress-Path': prefix},
                   environ_base={'REMOTE_ADDR': '172.30.32.2'}).get_data(as_text=True)
    assert 'http://&lt;home-assistant-ip&gt;:5000/api/v1/status' in html
    assert 'curl' in html and 'hassio_ingress/TESTTOKEN/api' not in html
    assert 'direkten Port' in html


def _order_of(html, markers):
    return [m for _, m in sorted((html.index(m), m) for m in markers)]


def test_entries_without_time_sort_after_midnight_entries(api):
    kush = api['plants']['Kush']
    day = '2031-03-03'
    for note, clock in (('M2-ohne', None), ('M2-null', '00:00'), ('M2-morgens', '07:30')):
        body = {'plant_id': kush, 'action': 'wasser', 'date': day, 'notes': note}
        if clock:
            body['time'] = clock
        assert api['call']('POST', '/actions', body).status_code == 201
    expected = ['M2-morgens', 'M2-null', 'M2-ohne']
    assert _order_of(api['web'].get('/plant_actions').get_data(as_text=True), expected) == expected
    assert _order_of(api['web'].get(f'/plant/{kush}').get_data(as_text=True), expected) == expected


@pytest.mark.parametrize('clock, expected', [('07:30:45', '07:30:00'), ('23:59:59', '23:59:00'), ('07:30', '07:30:00')])
def test_time_accepts_seconds_and_drops_them(api, clock, expected):
    r = api['call']('POST', '/actions', {'plant_id': api['plants']['Kush'], 'action': 'wasser',
                                          'date': '2031-04-04', 'time': clock, 'notes': 'M3-' + clock})
    assert r.status_code == 201
    with flask_app.app_context():
        log = PlantActionLog.query.filter_by(notes='M3-' + clock).one()
        assert str(log.time) == expected


@pytest.mark.parametrize('clock', ['7:30:45:1', '07:30:61', '24:00:00', '07-30', 'abc', 730, '07:30 '])
def test_other_time_formats_are_rejected(api, clock):
    r = api['call']('POST', '/actions', {'plant_id': api['plants']['Kush'], 'action': 'wasser', 'time': clock})
    assert r.status_code == 422


def test_huge_digit_strings_are_not_found(api):
    huge = '9' * 5000
    for path, body in (('/actions', {'plant_id': huge, 'action': 'wasser'}),
                       ('/actions', {'environment_id': huge, 'action': 'wasser'}),
                       ('/measurements', {'plant_id': huge, 'values': {'ph': 6}}),
                       ('/environment-logs', {'environment_id': huge, 'values': {'vpd': 1}})):
        assert api['call']('POST', path, body).status_code == 404, path
    assert api['call']('POST', '/actions', {'plant_id': '0' * 25 + '1', 'action': 'wasser'}).status_code == 404


@pytest.mark.parametrize('body', [{'values': {'vpd': 1}}, {'environment_id': None, 'values': {'vpd': 1}}])
def test_environment_log_without_environment_id(api, body):
    r = api['call']('POST', '/environment-logs', body)
    assert r.status_code == 422
    assert r.get_json()['error'] == 'environment_id fehlt.'


def test_environment_log_malformed_id_keeps_integer_message(api):
    r = api['call']('POST', '/environment-logs', {'environment_id': 'abc', 'values': {'vpd': 1}})
    assert r.status_code == 422
    assert r.get_json()['error'] == 'plant_id und environment_id müssen ganze Zahlen sein.'


@pytest.fixture(autouse=True)
def _no_entries_for_recent_tests(request):
    """The api fixture is module-scoped; the recent tests count entries and need none left over."""
    if request.node.name.startswith('test_recent') and 'api' in request.fixturenames:
        with flask_app.app_context():
            PlantActionLog.query.delete()
            PlantLog.query.delete()
            db.session.commit()
    yield


def _recent(api, n=10, env_key='env'):
    envs = api['call']('GET', f'/environments?recent={n}').get_json()
    return next(e for e in envs if e['id'] == api[env_key])['recent']


def test_environments_without_recent_is_unchanged(api):
    envs = api['call']('GET', '/environments').get_json()
    assert all('recent' not in e for e in envs)
    envs0 = api['call']('GET', '/environments?recent=0').get_json()
    assert all('recent' not in e for e in envs0)


def test_recent_groups_entries_for_all_plants(api):
    api['call']('POST', '/actions', {'environment_id': api['env'], 'action': 'wasser',
                                     'date': '2026-10-01', 'time': '18:09', 'notes': 'automatisch'})
    items = _recent(api)
    assert items == [{'type': 'action', 'date': '2026-10-01', 'time': '18:09', 'action': 'wasser',
                      'label': 'Wasser geben', 'plants': ['Amnesia', 'Kush'], 'all': True,
                      'notes': 'automatisch'}]


def test_recent_single_plant_and_measurement(api):
    api['call']('POST', '/actions', {'plant_id': api['plants']['Kush'], 'action': 'training',
                                     'date': '2026-10-01', 'time': '09:00'})
    api['call']('POST', '/measurements', {'environment_id': api['env'], 'date': '2026-10-01',
                                          'time': '10:00', 'values': {'ph': 6.5, 'ec': 1.5}})
    items = _recent(api)
    assert [i['type'] for i in items] == ['measurement', 'action']
    assert items[0]['values'] == {'ph': 6.5, 'ec': 1.5}
    assert items[0]['all'] is True and items[0]['notes'] is None
    assert items[1]['plants'] == ['Kush'] and items[1]['all'] is False
    assert items[1]['label'] == 'Training'


def test_recent_order_and_limit(api):
    for day, clock in (('2026-09-30', '08:00'), ('2026-10-01', None), ('2026-10-01', '07:00'),
                       ('2026-10-01', '12:00')):
        body = {'environment_id': api['env'], 'action': 'wasser', 'date': day}
        if clock:
            body['time'] = clock
        api['call']('POST', '/actions', body)
    items = _recent(api)
    assert [(i['date'], i['time']) for i in items] == [
        ('2026-10-01', '12:00'), ('2026-10-01', '07:00'), ('2026-10-01', None), ('2026-09-30', '08:00')]
    assert len(_recent(api, 2)) == 2


def test_recent_different_notes_are_not_grouped(api):
    for name, note in (('Amnesia', 'a'), ('Kush', 'b')):
        api['call']('POST', '/actions', {'plant_id': api['plants'][name], 'action': 'wasser',
                                         'date': '2026-10-01', 'time': '08:00', 'notes': note})
    assert len(_recent(api)) == 2


def test_recent_empty_environment(api):
    assert _recent(api, env_key='empty') == []


@pytest.mark.parametrize('bad', ['-1', '51', 'abc', '1.5', ''])
def test_recent_rejects_invalid_values(api, bad):
    r = api['call']('GET', f'/environments?recent={bad}')
    assert r.status_code == 422
    assert 'error' in r.get_json()


def test_recent_never_contains_foreign_plants(api, foreign):
    with flask_app.app_context():
        stray = Plant(pflanzenname='Streuner', user_id=User.query.filter_by(username='fremd').one().id,
                      environment_id=api['env'])
        db.session.add(stray)
        db.session.commit()
        stray_id = stray.id
        db.session.add(PlantActionLog(plant_id=stray_id, action='wasser', date=date(2026, 10, 1)))
        db.session.commit()
    try:
        api['call']('POST', '/actions', {'environment_id': api['env'], 'action': 'wasser',
                                         'date': '2026-10-01', 'time': '08:00'})
        items = _recent(api)
        assert len(items) == 1
        assert set(items[0]['plants']) == {'Amnesia', 'Kush'} and items[0]['all'] is True
    finally:
        with flask_app.app_context():
            PlantActionLog.query.filter_by(plant_id=stray_id).delete()
            db.session.delete(db.session.get(Plant, stray_id))
            db.session.commit()
