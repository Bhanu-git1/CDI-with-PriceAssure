"""
Query safety and row-limit tests.

Covers the two guarantees that keep a generated query from doing damage or
returning an unbounded result set.

Run from backend/:  python -m pytest tests/test_query_safety.py -v
"""

import pytest

from app.datasources import registry
from app.services.mysql_service import MySQLService


@pytest.fixture(scope="module")
def svc():
    # No connection is made: apply_row_limit and is_sql_safe are pure.
    return MySQLService(user="u", database="d")


# --- row limiting ---------------------------------------------------------

@pytest.mark.parametrize("query", [
    "SELECT * FROM Leakage_Activity",
    "SELECT HCP_Name FROM Leakage_Activity ORDER BY Leakage_Percentage DESC",
    "WITH t AS (SELECT 1 AS a) SELECT * FROM t",
    "SELECT State, COUNT(*) FROM Leakage_Activity GROUP BY State",
])
def test_row_queries_are_capped(svc, query):
    assert svc.apply_row_limit(query).endswith(" LIMIT 200")


@pytest.mark.parametrize("query", [
    # The regression: a scalar subquery containing MAX() used to disable the
    # cap for the whole statement, so a row query came back unbounded.
    "SELECT Fatigue_ID, HCP_Name, Fatigue, "
    "CONCAT(ROUND((Fatigue / (SELECT MAX(Fatigue) FROM fatigue_score)) * 100, 1), '%') AS pct "
    "FROM fatigue_score WHERE (Fatigue / (SELECT MAX(Fatigue) FROM fatigue_score)) * 100 > 90",
    # A LIMIT inside a subquery does not bound the outer result set.
    "SELECT * FROM (SELECT * FROM Leakage_Activity LIMIT 10) x JOIN hcp_master ON 1=1",
])
def test_aggregate_and_subquery_limits_do_not_defeat_the_cap(svc, query):
    assert svc.apply_row_limit(query).endswith(" LIMIT 200"), (
        "row-returning query left uncapped"
    )


@pytest.mark.parametrize("query", [
    "SELECT * FROM Leakage_Activity LIMIT 10",
    "SELECT * FROM Leakage_Activity LIMIT 10, 20",
    "SELECT * FROM Leakage_Activity LIMIT 10 OFFSET 5",
    "SELECT * FROM Leakage_Activity LIMIT 10 ",
])
def test_existing_trailing_limit_is_respected(svc, query):
    """A second LIMIT would be a syntax error, so an existing one must win."""
    assert svc.apply_row_limit(query) == query


@pytest.mark.parametrize("query", [
    "SHOW TABLES",
    "DESCRIBE GPO_CUST_HDR",
    "DESC Leakage_Activity",
    "EXPLAIN SELECT * FROM Leakage_Activity",
])
def test_non_row_statements_are_untouched(svc, query):
    """These reject a LIMIT clause, so appending one breaks them."""
    assert svc.apply_row_limit(query) == query


def test_limit_is_configurable(svc):
    assert svc.apply_row_limit("SELECT 1", max_rows=5).endswith(" LIMIT 5")


# --- statement whitelist --------------------------------------------------

@pytest.mark.parametrize("query", [
    "SELECT * FROM t", "SHOW TABLES", "DESCRIBE t", "EXPLAIN SELECT 1",
])
def test_read_statements_are_allowed(svc, query):
    assert svc.is_sql_safe(query)


@pytest.mark.parametrize("query", [
    "INSERT INTO t VALUES (1)",
    "UPDATE t SET a=1",
    "DELETE FROM t",
    "DROP TABLE t",
    "TRUNCATE t",
    "ALTER TABLE t ADD a INT",
    "CREATE TABLE t (a INT)",
    "GRANT ALL ON *.* TO x",
    "SELECT * FROM t; DROP TABLE t",
])
def test_write_statements_are_rejected(svc, query):
    assert not svc.is_sql_safe(query)


def test_permission_columns_are_not_mistaken_for_write_verbs(svc):
    """
    GPO's RBAC columns embed write verbs (CAN_DELETE, CAN_ADD). Word-boundary
    matching must not reject a legitimate SELECT of them.
    """
    assert svc.is_sql_safe(
        "SELECT CAN_VIEW, CAN_ADD, CAN_EDIT, CAN_DELETE FROM GPO_ROLE_PERMISSION"
    )
    assert svc.is_sql_safe("SELECT CREATED_DATE, MODIFIED_BY FROM GPO_CUST_HDR")


# --- server-enforced read-only -------------------------------------------

def test_gpo_source_is_declared_read_only():
    """
    DB 2 holds live operational tables and its configured user has full DDL
    rights, so the read-only session guard must stay switched on.
    """
    assert registry.require("mysql_gpo").adapter.raw_service.read_only is True


def test_primary_source_stays_writable():
    """Chat transcripts are written over this pool; it must not be read-only."""
    assert registry.require("mysql_primary").adapter.raw_service.read_only is False
