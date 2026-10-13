from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

BACKEND = Path(__file__).resolve().parents[1]
TABLES = {"donors", "hospitals", "blood_units", "blood_requests", "allocations"}


def alembic_config() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


def test_upgrade_creates_every_table_and_downgrade_removes_them():
    # alembic/env.py reads DATABASE_URL from settings, which conftest points at test.db.
    engine = create_engine("sqlite:///./test.db")
    cfg = alembic_config()

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    assert set(inspect(engine).get_table_names()) >= TABLES

    command.downgrade(cfg, "base")
    assert TABLES.isdisjoint(inspect(engine).get_table_names())


def test_migration_matches_the_models():
    """The migration and the ORM models must describe the same columns."""
    from app.db import Base

    engine = create_engine("sqlite:///./test.db")
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    inspector = inspect(engine)
    for table in TABLES:
        migrated = {c["name"] for c in inspector.get_columns(table)}
        modelled = set(Base.metadata.tables[table].columns.keys())
        assert migrated == modelled, table
    command.downgrade(cfg, "base")
