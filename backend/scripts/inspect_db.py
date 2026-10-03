"""Look inside the app's database.

    python -m scripts.inspect_db                 # every table with its row count
    python -m scripts.inspect_db users           # first 20 rows of a table
    python -m scripts.inspect_db games 5         # first 5 rows
    python -m scripts.inspect_db "select username, email from users"   # any read-only query

Uses the same database as the app (LDM_DATABASE_URL, default backend/league_draft_manager.db).
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from app.core.database import engine


def _print_rows(columns, rows) -> None:
    if not rows:
        print("(no rows)")
        return
    table = [[("" if v is None else str(v))[:40] for v in row] for row in rows]
    widths = [max(len(c), *(len(r[i]) for r in table)) for i, c in enumerate(columns)]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for row in table:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))


def main(args: list[str]) -> None:
    tables = inspect(engine).get_table_names()
    with engine.connect() as conn:
        if not args:
            print(f"Database: {engine.url}\n")
            for name in sorted(tables):
                count = conn.execute(text(f'select count(*) from "{name}"')).scalar()
                print(f"{name:<24}{count:>8} rows")
            return
        if args[0] in tables:
            limit = int(args[1]) if len(args) > 1 else 20
            result = conn.execute(text(f'select * from "{args[0]}" limit :n'), {"n": limit})
        elif args[0].lstrip().lower().startswith("select"):
            result = conn.execute(text(args[0]))
        else:
            sys.exit(f"Unknown table {args[0]!r}. Tables: {', '.join(sorted(tables))}")
        _print_rows(list(result.keys()), result.fetchall())


if __name__ == "__main__":
    main(sys.argv[1:])
