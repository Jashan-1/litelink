from alembic import context
from sqlalchemy import create_engine

from app import config, models

engine = create_engine(config.DATABASE_URL)  # psycopg also has a sync mode, so the app's URL works unchanged
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=models.Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
