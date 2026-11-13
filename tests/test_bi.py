"""Tests hors-ligne : LLM simulé, vraie base SQLite temporaire."""
import json
import os
import sys
import tempfile
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import seed
from app import db, forecast as fc
from app.supervisor import Supervisor
from app.state import BIState
from app.tools import Toolkit

DB = os.path.join(tempfile.mkdtemp(), "t.db")
seed.build(DB)

MONTHLY = ("SELECT strftime('%Y-%m', o.order_date) AS month, ROUND(SUM(oi.quantity*p.unit_price*(1-oi.discount)),2) "
           "AS revenue FROM orders o JOIN order_items oi ON oi.order_id=o.id JOIN products p ON p.id=oi.product_id "
           "GROUP BY month ORDER BY month")


def call(name, args, cid="x"):
    return NS(content="", tool_calls=[NS(id=cid, function=NS(name=name, arguments=json.dumps(args)))])


def text(t):
    return NS(content=t, tool_calls=None)


class Scripted:
    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, **kw):
        return self.replies.pop(0)


def test_sql_guard():
    for bad in ("DROP TABLE orders", "SELECT 1; DROP TABLE orders", "DELETE FROM orders", "PRAGMA table_info(orders)"):
        try:
            db.validate_sql(bad)
            assert False, bad
        except ValueError:
            pass
    assert db.validate_sql("WITH a AS (SELECT 1) SELECT * FROM a;").startswith("WITH")


def test_readonly_connection():
    conn = db.connect_ro(DB)
    try:
        conn.execute("DELETE FROM orders")
        assert False
    except Exception as e:
        assert "readonly" in str(e).lower()


def test_forecast_linear_and_seasonal():
    res = fc.forecast([100 + 10 * i for i in range(24)], 3)
    assert abs(res["forecast"][0]["value"] - 340) < 5
    seasonal = [(100 + 5 * i) * (1.3 if i % 12 == 11 else 1.0) for i in range(36)]
    r2 = fc.forecast(seasonal, 12)
    assert "saisonnalité" in r2["method"] and r2["mape"] is not None and r2["mape"] < 10


def test_toolkit_error_recovery():
    tk = Toolkit(db.connect_ro(DB), BIState(question="q"))
    assert tk.execute("run_sql", {"query": "SELECT * FROM nope", "dataset_name": "x"}).startswith("ERROR")
    assert tk.execute("stats", {"dataset": "x", "column": "y"}).startswith("ERROR")
    assert "Dataset 'monthly_revenue'" in tk.execute("run_sql", {"query": MONTHLY, "dataset_name": "Monthly Revenue"})


def test_full_multi_agent_flow():
    llm = Scripted([
        text(json.dumps({"steps": [{"agent": "forecast", "task": "forecast"}, {"agent": "sql", "task": "monthly revenue"},
                                    {"agent": "analyst", "task": "insights"}]})),
        call("describe_schema", {}, "1"), call("run_sql", {"query": MONTHLY, "dataset_name": "monthly_revenue"}, "2"),
        text("monthly_revenue saved"),
        call("stats", {"dataset": "monthly_revenue", "column": "revenue"}, "3"), text("Insight chiffré"),
        call("forecast", {"dataset": "monthly_revenue", "value_column": "revenue", "horizon": 6}, "4"), text("Prévision ok"),
        text("# Réponse\nrecommandations"),
    ])
    events = []
    state = Supervisor(llm, db.connect_ro(DB), on_event=events.append).run("Évolution du CA ?")
    assert state.plan[0]["agent"] == "sql" and state.plan[-1]["agent"] == "advisor"
    assert "monthly_revenue" in state.datasets and "monthly_revenue" in state.forecasts
    assert state.answer.startswith("# Réponse")


def test_sql_agent_retry_when_no_dataset():
    llm = Scripted([
        text('{"steps": [{"agent": "sql", "task": "t"}]}'),
        text("je n'ai rien fait"),                                                  # 1re tentative : aucun dataset
        call("run_sql", {"query": MONTHLY, "dataset_name": "m"}, "1"), text("ok"),  # 2e tentative guidée
        text("Réponse finale"),
    ])
    state = Supervisor(llm, db.connect_ro(DB)).run("question")
    assert "m" in state.datasets and state.answer == "Réponse finale"
