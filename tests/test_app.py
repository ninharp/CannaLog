"""Durchlauf durch die App: direkter Port und Home-Assistant-Ingress.

Start: pip install -r requirements.txt pytest && pytest
"""
import os
import re
import tempfile
from datetime import date

import pytest

os.environ.setdefault('CANNALOG_DATA_DIR', tempfile.mkdtemp())

from app import app as flask_app, db  # noqa: E402
from app.models import Environment, Plant, PlantActionLog, PlantLog  # noqa: E402
from app.schema import upgrade_schema  # noqa: E402

INGRESS_PREFIX = '/api/hassio_ingress/TESTTOKEN'
INGRESS_ENV = {'REMOTE_ADDR': '172.30.32.2'}
PORT_ENV = {'REMOTE_ADDR': '192.168.1.50'}


@pytest.fixture(scope='module')
def client():
    upgrade_schema()
    flask_app.config['WTF_CSRF_ENABLED'] = False
    with flask_app.test_client() as c:
        c.post('/register', data={'username': 'tester', 'password': 'geheim123',
                                  'confirm_password': 'geheim123'})
        c.post('/login', data={'username': 'tester', 'password': 'geheim123'})
        yield c


@pytest.fixture(scope='module')
def data(client):
    client.post('/environment/add', data={'name': 'Zelt', 'exposure_time': '18', 'length': '80',
                                          'width': '80', 'height': '160', 'light_enabled': 'y',
                                          'lamps-0-type': 'led', 'lamps-0-power': '240'})
    client.post('/plant/add', data={'pflanzenname': 'Testpflanze', 'date': '2026-08-01', 'count': '1',
                                    'medium_type': 'erde', 'phase': 'Blüte', 'environment_id': '1'})
    with flask_app.app_context():
        return {'env_id': Environment.query.first().id, 'plant_id': Plant.query.first().id}


def errors_of(response):
    html = response.get_data(as_text=True)
    return re.findall(r'field__error">([^<]+)', html)


def test_schema_upgrade_is_idempotent():
    upgrade_schema()
    upgrade_schema()


def test_measurement_is_saved(client, data):
    response = client.post(f"/plant/{data['plant_id']}/logs/add", data={
        'date': '2026-09-28', 'measurements-0-type': 'ph', 'measurements-0-value': '6,1'.replace(',', '.'),
        'notes': 'Alles gut'})
    assert response.status_code == 302
    with flask_app.app_context():
        log = PlantLog.query.order_by(PlantLog.id.desc()).first()
        assert log.date == date(2026, 9, 28)
        assert log.measurements[0].type == 'ph'


def test_action_is_saved(client, data):
    response = client.post('/plant_actions/add', data={
        'plant_id': data['plant_id'], 'date': '2026-09-28', 'action': 'wasser', 'notes': '1,5 l'})
    assert response.status_code == 302
    with flask_app.app_context():
        assert PlantActionLog.query.count() == 1


@pytest.mark.parametrize('path, payload, expected_field', [
    ('/plant/1/logs/add', {'date': '', 'measurements-0-type': 'ph', 'measurements-0-value': '6'}, 'Datum'),
    ('/plant/1/logs/add', {'date': '2026-09-28', 'measurements-0-type': 'ph',
                           'measurements-0-value': 'abc'}, 'Wert'),
    ('/environment/1/logs/add', {'date': '2026-09-28', 'measurements-0-type': 'co2',
                                 'measurements-0-min_value': 'abc'}, 'Min'),
    ('/plant_actions/add', {'plant_id': '1', 'date': '2026-09-28', 'action': ''}, 'Aktion'),
    ('/plant/add', {'pflanzenname': '', 'date': '2026-09-28', 'count': '1', 'medium_type': 'erde',
                    'phase': 'Blüte', 'environment_id': '1'}, 'Pflanzenname'),
    ('/environment/add', {'name': 'Zwei', 'exposure_time': '18', 'lamps-0-type': 'led',
                          'lamps-0-power': 'viel'}, 'Leistung'),
])
def test_invalid_input_marks_the_field(client, data, path, payload, expected_field):
    """Jeder Fehler steht am Feld und in der Sammelmeldung — sonst sucht man vergeblich."""
    response = client.post(path, data=payload)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'field--invalid' in html, 'kein Feld markiert'
    assert errors_of(response), 'keine Meldung am Feld'
    assert expected_field in html
    summary = re.search(r'flash__item--danger">(.*?)</div>', html, re.S)
    assert summary and expected_field in summary.group(1), 'Feld fehlt in der Sammelmeldung'


def test_error_messages_are_german(client, data):
    response = client.post(f"/plant/{data['plant_id']}/logs/add",
                           data={'date': '', 'measurements-0-type': 'ph', 'measurements-0-value': '6'})
    assert 'Dieses Feld wird benötigt.' in errors_of(response)


def test_pages_work_behind_ingress(client, data):
    """Hinter Ingress tragen alle Links und Weiterleitungen den Präfix."""
    headers = {'X-Ingress-Path': INGRESS_PREFIX}
    for path in ['dashboard', f"plant/{data['plant_id']}", f"environment/{data['env_id']}",
                 'plant_actions', 'logs/export', 'plant/add', 'image/add']:
        response = client.get(f'/{path}', headers=headers, environ_base=INGRESS_ENV)
        assert response.status_code == 200, path
        html = response.get_data(as_text=True)
        assert f'<base href="{INGRESS_PREFIX}/"' in html, path
        absolute = [link for link in re.findall(r'(?:href|src|action)="(/[^"]*)"', html)
                    if not link.startswith(INGRESS_PREFIX)]
        assert not absolute, f'{path}: absolute Links ohne Präfix {absolute}'

    response = client.post('/plant_actions/add', headers=headers, environ_base=INGRESS_ENV,
                           data={'plant_id': data['plant_id'], 'date': '2026-09-28', 'action': 'ernte'})
    assert response.headers['Location'].startswith(INGRESS_PREFIX)


def test_ingress_header_is_ignored_from_other_hosts(client):
    """Nur der Ingress-Proxy darf den Präfix setzen, sonst könnte ihn jeder fälschen."""
    response = client.get('/dashboard', headers={'X-Ingress-Path': '/fremd'}, environ_base=PORT_ENV)
    assert '/fremd' not in response.headers.get('Location', '')


def test_report_and_pdf(client, data):
    payload = {'environment_id': data['env_id'], 'include_env_logs': 'y', 'include_plant_logs': 'y',
               'include_action_logs': 'y'}
    assert b'Testpflanze' in client.post('/logs/export', data=payload).data
    pytest.importorskip('weasyprint')
    response = client.post('/logs/export', data=dict(payload, pdf='1'))
    assert response.status_code == 200 and response.data[:4] == b'%PDF'


def test_action_time_is_saved_and_shown(client, data):
    response = client.post('/plant_actions/add', data={
        'plant_id': data['plant_id'], 'date': '2026-09-29', 'time': '08:15', 'action': 'wasser'})
    assert response.status_code == 302
    with flask_app.app_context():
        log = PlantActionLog.query.order_by(PlantActionLog.id.desc()).first()
        assert log.time.strftime('%H:%M') == '08:15'
    html = client.get('/plant_actions').get_data(as_text=True)
    assert '29.09.2026 08:15' in html


def test_time_is_optional(client, data):
    response = client.post('/plant_actions/add', data={
        'plant_id': data['plant_id'], 'date': '2026-09-27', 'action': 'training'})
    assert response.status_code == 302
    with flask_app.app_context():
        log = PlantActionLog.query.order_by(PlantActionLog.id.desc()).first()
        assert log.time is None


def test_measurement_time_is_saved(client, data):
    response = client.post(f"/plant/{data['plant_id']}/logs/add", data={
        'date': '2026-09-29', 'time': '18:30', 'measurements-0-type': 'ec', 'measurements-0-value': '1.4'})
    assert response.status_code == 302
    with flask_app.app_context():
        log = PlantLog.query.order_by(PlantLog.id.desc()).first()
        assert log.time.strftime('%H:%M') == '18:30'
    html = client.get(f"/plant/{data['plant_id']}").get_data(as_text=True)
    assert '29.09.2026 18:30' in html


def test_environment_log_time_is_saved(client, data):
    from app.models import EnvironmentLog
    response = client.post(f"/environment/{data['env_id']}/logs/add", data={
        'date': '2026-09-29', 'time': '23:55', 'measurements-0-type': 'vpd', 'measurements-0-value': '1.1'})
    assert response.status_code == 302
    with flask_app.app_context():
        log = EnvironmentLog.query.order_by(EnvironmentLog.id.desc()).first()
        assert log.time.strftime('%H:%M') == '23:55'


def test_invalid_time_is_rejected(client, data):
    response = client.post('/plant_actions/add', data={
        'plant_id': data['plant_id'], 'date': '2026-09-29', 'time': '25:99', 'action': 'wasser'})
    assert response.status_code == 200
    assert 'Uhrzeit' in ' '.join(errors_of(response)) or 'Uhrzeit' in response.get_data(as_text=True)


def test_deleting_a_plant_removes_its_entries(client, data):
    with flask_app.app_context():
        plant = Plant.query.get(data['plant_id'])
        assert plant.logs and plant.actions
    assert client.post(f"/plant/{data['plant_id']}/delete").status_code == 302
    with flask_app.app_context():
        assert PlantLog.query.count() == 0
        assert PlantActionLog.query.count() == 0
        assert db.session.get(Plant, data['plant_id']) is None
