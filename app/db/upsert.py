from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

_CHUNK = 1000


def _chunks(rows: Sequence[Mapping[str, Any]], size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def bulk_upsert(
    session: Session,
    model: Any,
    rows: Sequence[Mapping[str, Any]],
    update_cols: Sequence[str] | None = None,
    chunk: int = _CHUNK,
) -> int:
    if not rows:
        return 0
    table = model.__table__
    dialect = session.bind.dialect.name
    pk_cols = [c.name for c in table.primary_key.columns]

    for chunk_rows in _chunks(list(rows), chunk):
        if dialect == "mysql":
            stmt = mysql_insert(table).values(chunk_rows)
            if update_cols:
                set_ = {c: stmt.inserted[c] for c in update_cols}
            else:
                set_ = {pk_cols[0]: stmt.inserted[pk_cols[0]]}
            stmt = stmt.on_duplicate_key_update(**set_)
        elif dialect == "sqlite":
            stmt = sqlite_insert(table).values(chunk_rows)
            if update_cols:
                stmt = stmt.on_conflict_do_update(
                    index_elements=pk_cols,
                    set_={c: getattr(stmt.excluded, c) for c in update_cols},
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=pk_cols)
        else:
            raise NotImplementedError(f"upsert not implemented for dialect {dialect!r}")
        session.execute(stmt)
    return len(rows)


def bulk_insert(
    session: Session,
    model: Any,
    rows: Sequence[Mapping[str, Any]],
    chunk: int = _CHUNK,
) -> int:
    if not rows:
        return 0
    table = model.__table__
    for chunk_rows in _chunks(list(rows), chunk):
        session.execute(table.insert(), list(chunk_rows))
    return len(rows)
