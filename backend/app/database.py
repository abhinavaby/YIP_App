from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


def database_url(value: str) -> URL:
    """Normalize Supabase's PostgreSQL URL and enforce its connection requirements."""
    url = make_url(value.strip())
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername == "postgresql+psycopg":
        query = dict(url.query)
        hostname = url.host or ""
        if hostname.endswith((".supabase.co", ".pooler.supabase.com")):
            query.setdefault("sslmode", "require")
        if hostname.endswith(".pooler.supabase.com"):
            query.setdefault("prepare_threshold", "none")
        url = url.set(query=query)
    return url


resolved_url = database_url(settings.database_url)
is_sqlite = resolved_url.drivername.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
if resolved_url.drivername == "postgresql+psycopg" and "prepare_threshold" in resolved_url.query:
    prepare_threshold = resolved_url.query["prepare_threshold"].lower()
    connect_args["prepare_threshold"] = None if prepare_threshold in ("none", "off", "disable") else int(prepare_threshold)
    resolved_url = resolved_url.set(query={
        key: value for key, value in resolved_url.query.items() if key != "prepare_threshold"
    })

engine = create_engine(resolved_url, connect_args=connect_args, pool_pre_ping=not is_sqlite)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def enable_sqlite_wal(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
