"""Outils exposés aux agents (function calling). Chaque erreur est renvoyée à l'agent pour qu'il se corrige."""
import re

from . import db, forecast as fc

SQL_TOOLS = [
    {"type": "function", "function": {
        "name": "describe_schema", "description": "Return tables, columns, row counts and samples of the database.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "run_sql",
        "description": "Run ONE read-only SQLite SELECT query and save the result as a named dataset.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "dataset_name": {"type": "string", "description": "snake_case name, e.g. monthly_revenue"}},
            "required": ["query", "dataset_name"]}}},
]
ANALYST_TOOLS = [
    {"type": "function", "function": {
        "name": "list_datasets", "description": "List available datasets with their columns.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "stats", "description": "Descriptive statistics and growth of a numeric column of a dataset.",
        "parameters": {"type": "object", "properties": {
            "dataset": {"type": "string"}, "column": {"type": "string"}}, "required": ["dataset", "column"]}}},
]
FORECAST_TOOLS = [
    {"type": "function", "function": {
        "name": "forecast",
        "description": "Forecast the next periods of a monthly time series stored in a dataset.",
        "parameters": {"type": "object", "properties": {
            "dataset": {"type": "string"}, "value_column": {"type": "string"},
            "horizon": {"type": "integer", "description": "Number of months, 1 to 12"}},
            "required": ["dataset", "value_column"]}}},
]


def slug(s):
    return re.sub(r"[^a-z0-9_]+", "_", (s or "").lower()).strip("_")[:40]


def fmt_table(cols, rows, n=12):
    lines = [" | ".join(map(str, cols))] + [" | ".join(map(str, r)) for r in rows[:n]]
    if len(rows) > n:
        lines.append(f"... ({len(rows) - n} more rows)")
    return "\n".join(lines)


def next_labels(last, h):
    m = re.match(r"^(\d{4})-(\d{2})$", str(last))
    if not m:
        return [f"+{i}" for i in range(1, h + 1)]
    y, mo = int(m.group(1)), int(m.group(2))
    out = []
    for _ in range(h):
        mo += 1
        if mo > 12:
            y, mo = y + 1, 1
        out.append(f"{y}-{mo:02d}")
    return out


class Toolkit:
    def __init__(self, conn, state):
        self.conn, self.state = conn, state

    def execute(self, name, args):
        try:
            return getattr(self, f"_{name}")(**args)
        except AttributeError:
            return f"ERROR: unknown tool '{name}'"
        except TypeError as e:
            return f"ERROR: bad arguments for {name}: {e}"
        except Exception as e:
            return f"ERROR: {e}"

    def _describe_schema(self):
        return db.schema_description(self.conn)

    def _run_sql(self, query, dataset_name=""):
        cols, rows, truncated = db.run_query(self.conn, query)
        name = slug(dataset_name) or f"dataset_{len(self.state.datasets) + 1}"
        if not rows:
            return "Query OK but 0 rows returned. Check filters, joins and date formats."
        self.state.datasets[name] = {"columns": cols, "rows": rows, "sql": query}
        return (f"Dataset '{name}' saved: {len(rows)} rows{' (truncated)' if truncated else ''}.\n"
                + fmt_table(cols, rows))

    def _get(self, dataset, column):
        ds = self.state.datasets.get(dataset)
        if not ds:
            raise ValueError(f"Unknown dataset '{dataset}'. Available: {list(self.state.datasets)}")
        cols = [c.lower() for c in ds["columns"]]
        if column.lower() not in cols:
            raise ValueError(f"Unknown column '{column}'. Columns: {ds['columns']}")
        return ds, cols.index(column.lower())

    def _list_datasets(self):
        if not self.state.datasets:
            return "No dataset yet."
        return "\n".join(f"- {n}: columns={d['columns']}, rows={len(d['rows'])}"
                         for n, d in self.state.datasets.items())

    def _stats(self, dataset, column):
        ds, j = self._get(dataset, column)
        pairs = [(r[0], r[j]) for r in ds["rows"] if isinstance(r[j], (int, float))]
        if not pairs:
            raise ValueError(f"Column '{column}' has no numeric values.")
        vals = [v for _, v in pairs]
        total = sum(vals)
        lo = min(pairs, key=lambda p: p[1])
        hi = max(pairs, key=lambda p: p[1])
        out = {"count": len(vals), "sum": round(total, 2), "mean": round(total / len(vals), 2),
               "min": f"{lo[1]} ({lo[0]})", "max": f"{hi[1]} ({hi[0]})",
               "first": f"{vals[0]} ({pairs[0][0]})", "last": f"{vals[-1]} ({pairs[-1][0]})"}
        if vals[0]:
            out["change_first_to_last_pct"] = round(100 * (vals[-1] - vals[0]) / abs(vals[0]), 1)
        if len(vals) >= 2 and vals[-2]:
            out["change_last_vs_previous_pct"] = round(100 * (vals[-1] - vals[-2]) / abs(vals[-2]), 1)
        if total:
            out["top_share_pct"] = round(100 * hi[1] / total, 1)
        return str(out)

    def _forecast(self, dataset, value_column, horizon=6):
        ds, j = self._get(dataset, value_column)
        labels = [r[0] for r in ds["rows"] if isinstance(r[j], (int, float))]
        values = [r[j] for r in ds["rows"] if isinstance(r[j], (int, float))]
        res = fc.forecast(values, horizon)
        res_labels = next_labels(labels[-1], len(res["forecast"]))
        self.state.forecasts[dataset] = {
            "dataset": dataset, "column": value_column, "labels": labels, "history": values,
            "future_labels": res_labels, "forecast": res["forecast"], "mape": res["mape"],
            "method": res["method"], "trend_pct_per_period": res["trend_pct_per_period"]}
        pts = "; ".join(f"{l}: {p['value']} [{p['low']}-{p['high']}]" for l, p in zip(res_labels, res["forecast"]))
        return (f"Method: {res['method']}. Backtest MAPE (last 3 points): {res['mape']}%. "
                f"Trend per period: {res['trend_pct_per_period']}%. Forecast (80% interval): {pts}")
