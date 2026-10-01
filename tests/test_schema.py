"""Schema upgrade of a database from release 1.2.1 (before entry times and API tokens)."""
import os
import tempfile

os.environ.setdefault('CANNALOG_DATA_DIR', tempfile.mkdtemp())

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app.schema import upgrade_engine  # noqa: E402

NEW_COLUMNS = [('plant_action_log', 'time'), ('plant_log', 'time'), ('environment_log', 'time'),
               ('user', 'api_token_hash'), ('user', 'api_token_last_used')]

OLD_SCHEMA = [
    'CREATE TABLE "user" (id INTEGER PRIMARY KEY, username VARCHAR(150) NOT NULL UNIQUE, password VARCHAR(200) NOT NULL)',
    'CREATE TABLE environment (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, auto_watering BOOLEAN, '
    'light_enabled BOOLEAN, exposure_time INTEGER, notes TEXT, preview_image_id INTEGER, length FLOAT, '
    'width FLOAT, height FLOAT, user_id INTEGER NOT NULL)',
    'CREATE TABLE plant (id INTEGER PRIMARY KEY, pflanzenname VARCHAR(100) NOT NULL, date DATE, count INTEGER, '
    'medium_type VARCHAR(20), medium_notes TEXT, strain VARCHAR(100), phase VARCHAR(20), notes TEXT, '
    'user_id INTEGER NOT NULL, environment_id INTEGER, created_at DATETIME, preview_image_id INTEGER)',
    'CREATE TABLE plant_action_log (id INTEGER PRIMARY KEY, plant_id INTEGER NOT NULL, date DATE NOT NULL, '
    'notes TEXT, action VARCHAR(50) NOT NULL)',
    'CREATE TABLE plant_log (id INTEGER PRIMARY KEY, plant_id INTEGER NOT NULL, date DATE NOT NULL, notes TEXT)',
    'CREATE TABLE environment_log (id INTEGER PRIMARY KEY, environment_id INTEGER NOT NULL, date DATE NOT NULL, '
    'notes TEXT)',
    "INSERT INTO \"user\" VALUES (1, 'alt', 'hash')",
    "INSERT INTO environment (id, name, user_id) VALUES (1, 'Zelt', 1)",
    "INSERT INTO plant (id, pflanzenname, user_id, environment_id) VALUES (1, 'Alte', 1, 1)",
    "INSERT INTO plant_action_log VALUES (1, 1, '2026-05-01', 'n', 'wasser')",
    "INSERT INTO plant_log VALUES (1, 1, '2026-05-01', 'n')",
    "INSERT INTO environment_log VALUES (1, 1, '2026-05-01', 'n')",
]


def _columns(engine):
    inspector = inspect(engine)
    return {(table, col['name']) for table in inspector.get_table_names() for col in inspector.get_columns(table)}


def _snapshot(engine):
    with engine.connect() as conn:
        return {
            'columns': sorted(_columns(engine)),
            'indexes': sorted((t, i['name']) for t in inspect(engine).get_table_names()
                              for i in inspect(engine).get_indexes(t)),
            'rows': [tuple(r) for table in ('user', 'plant', 'plant_action_log', 'plant_log', 'environment_log')
                     for r in conn.execute(text(f'SELECT * FROM "{table}"'))],
        }


def test_upgrade_of_a_1_2_1_database(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "old.db"}')
    with engine.begin() as conn:
        for statement in OLD_SCHEMA:
            conn.execute(text(statement))
    assert not set(NEW_COLUMNS) & _columns(engine)

    upgrade_engine(engine)

    assert set(NEW_COLUMNS) <= _columns(engine)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT username, api_token_hash, api_token_last_used FROM "user"')).one() \
            == ('alt', None, None)
        for table in ('plant_action_log', 'plant_log', 'environment_log'):
            assert conn.execute(text(f'SELECT id, date, notes, time FROM {table}')).one() \
                == (1, '2026-05-01', 'n', None), table
        assert conn.execute(text('SELECT pflanzenname FROM plant')).scalar() == 'Alte'
    assert 'ix_user_api_token_hash' in {i['name'] for i in inspect(engine).get_indexes('user')}

    first = _snapshot(engine)
    upgrade_engine(engine)
    assert _snapshot(engine) == first
