"""Create missing tables and columns on startup.

The project has no Alembic migrations, and databases from older releases lack
columns added later. SQLite supports ADD COLUMN, which covers every change so far.
"""
from sqlalchemy import inspect, text

from app import app, db


def upgrade_schema():
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        with db.engine.begin() as conn:
            for table in db.metadata.sorted_tables:
                existing = {col['name'] for col in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name in existing:
                        continue
                    col_type = column.type.compile(dialect=db.engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
                    app.logger.warning('Added missing column %s.%s', table.name, column.name)


if __name__ == '__main__':
    upgrade_schema()
    print('Database schema is up to date.')
