"""Database access.

One connection per request, opened lazily and closed by Flask's teardown.
Every query in this project is a parameterized statement loaded from
backend/sql/*.sql -- there is no SQL string building anywhere, and no ORM.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pymysql
from flask import current_app, g

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _dsn() -> dict:
    """Connection parameters, from the environment only."""
    return dict(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        # XAMPP's root password is empty by default. Read it rather than
        # assume it, so a machine that has set one still works.
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "aqi_india"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def connect() -> pymysql.connections.Connection:
    """A fresh connection. Used by the jobs, which run outside Flask."""
    return pymysql.connect(**_dsn())


def get_db() -> pymysql.connections.Connection:
    """The current request's connection."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(exc=None) -> None:
    db = g.pop("db", None)
    if db is None:
        return
    # A request that raised must not leave a half-applied transaction.
    try:
        if exc is None:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()


def strip_sql_comments(sql: str) -> str:
    """Remove `--` line comments, respecting quoted strings.

    Not cosmetic. PyMySQL binds parameters with Python's `%` operator
    (`query % escaped_args`), so ANY literal `%` in the statement is read
    as a format specifier -- including one inside a comment. A comment
    reading "~100% by the averaging definition" raises

        ValueError: unsupported format character 'b' (0x62)

    at bind time, nowhere near the comment that caused it. Escaping each
    one as `%%` works but silently re-breaks the moment somebody writes a
    normal percent sign in a new comment.

    Stripping the comments before the driver ever sees them removes the
    whole class of failure, and the files keep their explanations for
    the humans reading them.

    Literal percent signs in executable SQL -- a LIKE pattern, the
    modulo operator -- still have to be written `%%`. There are none in
    this project; the queries use ranges and arithmetic instead.
    """
    out: list[str] = []
    quote: str | None = None
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if quote:
            out.append(ch)
            # Doubled quote inside a quoted string is an escaped quote.
            if ch == quote:
                if i + 1 < n and sql[i + 1] == quote:
                    out.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
            elif ch == "\\" and i + 1 < n:
                out.append(sql[i + 1])
                i += 2
                continue
            i += 1
            continue
        if ch in ("\'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            # Skip to end of line, keeping the newline so line-based
            # error messages from the server still line up roughly.
            j = sql.find("\n", i)
            if j == -1:
                break
            i = j
            continue
        out.append(ch)
        i += 1

    # Collapse the blank lines the stripped comments leave behind.
    lines = [ln.rstrip() for ln in "".join(out).splitlines()]
    return "\n".join(ln for ln in lines if ln.strip())


@lru_cache(maxsize=None)
def load_sql(name: str) -> str:
    """Read a statement from backend/sql/, comments stripped.

    Cached, because these files do not change while the process runs.
    The name is a bare filename -- callers never pass user input here,
    and the resolved path is checked to be inside SQL_DIR regardless.
    """
    path = (SQL_DIR / name).resolve()
    if not path.is_relative_to(SQL_DIR):
        raise ValueError(f"SQL file outside sql/: {name}")
    if not path.exists():
        raise FileNotFoundError(f"No such SQL file: {path}")
    return strip_sql_comments(path.read_text(encoding="utf-8"))


def query_all(name: str, params: dict | None = None) -> list[dict]:
    with get_db().cursor() as cur:
        cur.execute(load_sql(name), params or {})
        return cur.fetchall()


def query_one(name: str, params: dict | None = None) -> dict | None:
    with get_db().cursor() as cur:
        cur.execute(load_sql(name), params or {})
        return cur.fetchone()


def execute(name: str, params: dict | None = None) -> int:
    """Run a write. Returns affected row count. Caller owns the commit."""
    with get_db().cursor() as cur:
        cur.execute(load_sql(name), params or {})
        return cur.rowcount


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
