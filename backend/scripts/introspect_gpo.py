"""
One-off / re-runnable schema introspector for the GPO database (DB 2).

Reads INFORMATION_SCHEMA from the live `gpo` database and emits a JSON dump of
every table, its columns, declared foreign keys, indexes and row counts.

The JSON output is the input for building `semantic/gpo_schema_model.yaml` — the
semantic layer must never contain invented column names, so it is generated from
the real schema rather than written by hand for 39 tables.

Usage (from backend/):
    python -m scripts.introspect_gpo                 # writes scripts/gpo_schema_dump.json
    python -m scripts.introspect_gpo --out other.json
"""

import argparse
import json
import os
import sys

# Allow running as a plain script (python scripts/introspect_gpo.py) as well as
# a module, by making `backend/` importable.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import mysql.connector  # noqa: E402

from app.config import settings  # noqa: E402


def introspect(host, port, user, password, database):
    conn = mysql.connector.connect(
        host=host, port=port, user=user, password=password,
        database=database, connection_timeout=15,
    )
    cur = conn.cursor(dictionary=True)

    # --- tables + row estimates -------------------------------------------
    cur.execute(
        """
        SELECT TABLE_NAME, TABLE_ROWS, TABLE_COMMENT
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """,
        (database,),
    )
    tables = {
        r["TABLE_NAME"]: {
            "name": r["TABLE_NAME"],
            "approx_rows": r["TABLE_ROWS"],
            "comment": r["TABLE_COMMENT"] or "",
            "columns": [],
            "foreign_keys": [],
            "indexes": [],
        }
        for r in cur.fetchall()
    }

    # --- columns -----------------------------------------------------------
    cur.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, DATA_TYPE, IS_NULLABLE,
               COLUMN_KEY, COLUMN_DEFAULT, EXTRA, COLUMN_COMMENT
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """,
        (database,),
    )
    for r in cur.fetchall():
        t = tables.get(r["TABLE_NAME"])
        if t is None:
            continue
        t["columns"].append({
            "name": r["COLUMN_NAME"],
            "type": r["COLUMN_TYPE"],
            "data_type": r["DATA_TYPE"],
            "nullable": r["IS_NULLABLE"] == "YES",
            "key": r["COLUMN_KEY"],          # PRI / UNI / MUL / ''
            "default": r["COLUMN_DEFAULT"],
            "extra": r["EXTRA"],
            "comment": r["COLUMN_COMMENT"] or "",
        })

    # --- declared foreign keys --------------------------------------------
    cur.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME,
               REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL
        ORDER BY TABLE_NAME, CONSTRAINT_NAME
        """,
        (database,),
    )
    declared_fks = []
    for r in cur.fetchall():
        fk = {
            "table": r["TABLE_NAME"],
            "column": r["COLUMN_NAME"],
            "constraint": r["CONSTRAINT_NAME"],
            "ref_table": r["REFERENCED_TABLE_NAME"],
            "ref_column": r["REFERENCED_COLUMN_NAME"],
        }
        declared_fks.append(fk)
        if r["TABLE_NAME"] in tables:
            tables[r["TABLE_NAME"]]["foreign_keys"].append(fk)

    # --- indexes (reveal de-facto join keys when FKs are not declared) ----
    cur.execute(
        """
        SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME, NON_UNIQUE, SEQ_IN_INDEX
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
        """,
        (database,),
    )
    for r in cur.fetchall():
        t = tables.get(r["TABLE_NAME"])
        if t is None:
            continue
        t["indexes"].append({
            "index": r["INDEX_NAME"],
            "column": r["COLUMN_NAME"],
            "unique": r["NON_UNIQUE"] == 0,
        })

    # --- exact row counts --------------------------------------------------
    # TABLE_ROWS from INFORMATION_SCHEMA is an InnoDB estimate and can be wildly
    # wrong on small tables, so count for real. The semantic layer quotes these
    # to the model, so they need to be accurate.
    for name, t in tables.items():
        try:
            cur.execute(f"SELECT COUNT(*) AS c FROM `{name}`")
            t["row_count"] = cur.fetchone()["c"]
        except Exception as e:  # a table we cannot read should not abort the dump
            t["row_count"] = None
            t["row_count_error"] = str(e)

    cur.close()
    conn.close()

    return {
        "database": database,
        "host": host,
        "table_count": len(tables),
        "declared_foreign_keys": declared_fks,
        "tables": tables,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "gpo_schema_dump.json"),
    )
    args = ap.parse_args()

    dump = introspect(
        settings.GPO_MYSQL_HOST,
        settings.GPO_MYSQL_PORT,
        settings.GPO_MYSQL_USER,
        settings.GPO_MYSQL_PASSWORD,
        settings.GPO_MYSQL_DATABASE,
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2, default=str)

    print(f"database          : {dump['database']} @ {dump['host']}")
    print(f"tables            : {dump['table_count']}")
    print(f"declared FKs      : {len(dump['declared_foreign_keys'])}")
    print(f"written to        : {args.out}")


if __name__ == "__main__":
    main()
