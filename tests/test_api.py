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
