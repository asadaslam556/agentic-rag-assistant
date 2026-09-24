import sqlite3
from pathlib import Path

import pytest

from agentic_rag.config import Settings
from agentic_rag.llm.mock import match_sql_example
from agentic_rag.tools import build_default_tools
from agentic_rag.tools import sql as sql_module
from agentic_rag.tools.sql import MAX_ROWS, SQLTool

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "structured" / "sales.sql"


@pytest.fixture()
def tool():
    sql_tool = SQLTool(SAMPLE)
    yield sql_tool
    sql_tool.close()


def test_the_schema_and_examples_reach_the_planner(tool):
    rendered = tool.spec.render()
    assert "customers(id INTEGER, name TEXT" in rendered
    assert "orders(id INTEGER, customer_id INTEGER" in rendered
    assert rendered.count("Q: ") == 3 and rendered.count("SQL: ") == 3


def test_worked_examples_return_the_right_rows(tool):
    answers = [tool.run(sql=sql).evidence[0].text for _, sql in tool.examples]
    assert answers == [
        "Database query result: name Nordlicht Logistik, robots ordered 32.",
        "Database query result: open orders 2.",
        "Database query result: revenue eur 1,857,000.",
    ]


def test_the_evidence_cites_the_query_itself(tool):
    item = tool.run(sql="SELECT COUNT(*) AS customers FROM customers;").evidence[0]
    assert item.source_type == "sql"
    assert item.source_ref == "sales.sql: SELECT COUNT(*) AS customers FROM customers"
    assert item.text == "Database query result: customers 5."


@pytest.mark.parametrize(
    "hostile",
    [
        "DELETE FROM orders",
        "UPDATE orders SET quantity = 0",
        "INSERT INTO customers VALUES (9, 'x', 'y', 'z')",
        "DROP TABLE orders",
        "CREATE TABLE loot (x)",
        "ATTACH DATABASE 'elsewhere.db' AS other",
        "PRAGMA query_only = OFF",
    ],
)
def test_anything_but_a_read_is_refused(tool, hostile):
    result = tool.run(sql=hostile)
    assert result.evidence == []
    assert "not authorized" in result.observation
    assert tool.run(sql="SELECT COUNT(*) FROM orders").evidence[0].text.endswith(" 7.")


@pytest.mark.parametrize(
    "hostile",
    [
        # sizes are small on purpose: the point is that the call is refused,
        # and a test must never allocate what the real attack would
        "SELECT length(randomblob(10)) AS n",
        "SELECT length(zeroblob(10)) AS n",
        "SELECT printf('%.*c', 10, 'x') AS s",
        "SELECT format('%s', 'x') AS s",
        "SELECT load_extension('anything')",
    ],
)
def test_functions_that_manufacture_or_reach_outside_are_refused(tool, hostile):
    result = tool.run(sql=hostile)
    assert result.evidence == []
    assert "not authorized" in result.observation


def test_the_everyday_functions_still_work(tool):
    sql = (
        "SELECT upper(substr(name, 1, 3)) AS code, round(avg(quantity), 1) AS avg_qty, "
        "strftime('%Y', min(order_date)) AS first_year, group_concat(DISTINCT sku) AS skus "
        "FROM orders o JOIN customers c ON c.id = o.customer_id "
        "WHERE name LIKE 'Nord%' AND date(order_date) >= date('2025-01-01') GROUP BY name"
    )
    assert tool.run(sql=sql).evidence[0].text == (
        "Database query result: code NOR, avg qty 16, first year 2025, skus ATLAS-P2."
    )


@pytest.mark.skipif(not hasattr(sqlite3.Connection, "setlimit"), reason="Connection.setlimit is Python 3.11+")
def test_one_oversized_value_is_refused(tool):
    # 5**8 = 390,625 names joined into one string, well past MAX_VALUE_BYTES
    joins = ", ".join(f"customers c{i}" for i in range(8))
    result = tool.run(sql=f"SELECT length(group_concat(c0.name)) AS n FROM {joins}")
    assert result.evidence == []
    assert "too big" in result.observation


def test_stacked_statements_are_refused(tool):
    result = tool.run(sql="SELECT 1; DROP TABLE orders")
    assert result.evidence == []
    assert "one statement" in result.observation


def test_a_bad_query_explains_itself_so_the_planner_can_fix_it(tool):
    result = tool.run(sql="SELECT revenue FROM sales")
    assert result.evidence == []
    assert "no such table: sales" in result.observation
    assert "try again" in result.observation


def test_a_query_past_the_time_limit_is_interrupted(tool, monkeypatch):
    monkeypatch.setattr(sql_module, "TIME_LIMIT_SECONDS", -1.0)
    result = tool.run(sql="SELECT COUNT(*) FROM orders a, orders b, orders c, orders d")
    assert result.evidence == []
    assert "interrupted" in result.observation


def test_rows_are_capped(tool):
    text = tool.run(sql="SELECT a.id, b.id, c.id FROM orders a, orders b, orders c").evidence[0].text
    assert f"({MAX_ROWS}) " in text and f"({MAX_ROWS + 1}) " not in text
    assert text.endswith(f"Only the first {MAX_ROWS} rows are shown.")


def test_an_empty_result_is_still_evidence(tool):
    result = tool.run(sql="SELECT name FROM customers WHERE country = 'Atlantis'")
    assert result.evidence[0].text == "The database query returned no rows."


def test_a_database_file_is_opened_read_only_and_left_untouched(tmp_path):
    path = tmp_path / "shop.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE items (name TEXT, price REAL)")
        connection.execute("INSERT INTO items VALUES ('bolt', 0.25)")
    connection.close()
    before = path.read_bytes()

    file_tool = SQLTool(path)
    try:
        assert file_tool.examples == []
        assert file_tool.run(sql="SELECT price FROM items").evidence[0].text == "Database query result: price 0.25."
        assert file_tool.run(sql="DELETE FROM items").evidence == []
    finally:
        file_tool.close()
    assert path.read_bytes() == before


def test_the_mock_runs_the_closest_worked_example():
    system = SQLTool(SAMPLE).spec.render()
    assert "COUNT(*) AS open_orders" in match_sql_example(system, "How many customer orders are still open?")
    assert "robots_ordered" in match_sql_example(system, "Which customer has ordered the most robots in total?")
    # sharing one word with an example is not enough: this stays on the catalog
    assert match_sql_example(system, "How many robots does Auralis have deployed?") == ""
    assert match_sql_example(system, "What was SAP cloud revenue growth in Q1 2024?") == ""


def test_the_tool_is_only_offered_when_the_database_loads(tmp_path, capsys):
    def tools_for(path: str) -> dict:
        return build_default_tools(Settings(search_provider="none", sql_database_path=path), searcher=None)

    assert "sql_query" in tools_for(str(SAMPLE))
    assert "sql_query" not in tools_for("")
    assert "sql_query" not in tools_for(str(tmp_path / "missing.sql"))
    broken = tmp_path / "broken.sql"
    broken.write_text("CREATE TABLE (", encoding="utf-8")
    assert "sql_query" not in tools_for(str(broken))
    assert "sql_query disabled" in capsys.readouterr().err


def test_a_database_question_end_to_end(tmp_path):
    from agentic_rag.pipeline import AgenticRAG

    pipeline = AgenticRAG(
        Settings(
            llm_provider="mock",
            embeddings_provider="local",
            search_provider="none",
            storage_dir=str(tmp_path / "storage"),
            catalog_path=str(ROOT / "data" / "structured" / "catalog.json"),
            sql_database_path=str(SAMPLE),
        )
    )
    try:
        answer = pipeline.ask("Which customer has ordered the most robots in total?")
    finally:
        pipeline.close()
    assert "Nordlicht Logistik" in answer.text and "32" in answer.text
    assert [step.action for step in answer.steps] == ["sql_query", "finish"]
    assert answer.citations[0].source_type == "sql"
    assert answer.verification.passed
