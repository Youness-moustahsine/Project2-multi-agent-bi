"""Quatre agents spécialisés. Les trois premiers utilisent le function calling ; le Business Advisor synthétise."""
import json

from .tools import ANALYST_TOOLS, FORECAST_TOOLS, SQL_TOOLS, fmt_table

LANGS = {"fr": "French", "en": "English", "ar": "Arabic"}

SQL_SYSTEM = (
    "You are the SQL Agent, an expert in SQLite. Always call describe_schema first. Then write ONE read-only "
    "SELECT at a time with run_sql, giving each result a clear snake_case dataset_name. If a query fails or "
    "returns nothing, read the error and fix the query. For time series use monthly aggregation "
    "(strftime('%Y-%m', ...)) ordered chronologically with columns [month, value]. "
    "When the needed datasets are saved, reply with one short sentence listing them."
)
ANALYST_SYSTEM = (
    "You are the Data Analyst Agent. Use the stats tool on the relevant datasets and columns, then write 3 to 5 "
    "precise insights (trends, concentration, best/worst performers). Every insight MUST contain a number "
    "returned by a tool. Never invent figures."
)
FORECAST_SYSTEM = (
    "You are the Forecasting Agent. Call forecast on the relevant monthly time series (a dataset with a month "
    "column and one numeric value column). Then explain in 3 to 4 sentences: the trend, the forecast values, the "
    "uncertainty interval and how reliable the model is (backtest MAPE). Never invent figures."
)
ADVISOR_SYSTEM = (
    "You are the Business Advisor Agent, a senior consultant. Using ONLY the facts provided, answer the manager's "
    "question in Markdown with these sections: Réponse directe, Constats clés, Prévisions (if any), "
    "Recommandations (3 to 5 prioritized actions, each tied to a figure), Limites. Write in {lang}. "
    "Be concise and concrete; never invent numbers."
)


def tool_loop(llm, system, user, specs, toolkit, max_steps, emit):
    """Boucle agentique : réflexion -> appel d'outil -> observation, avec budget d'étapes."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for step in range(max_steps):
        last = step == max_steps - 1
        if last:
            messages.append({"role": "user", "content": "Final step: reply now with your final text, no more tool calls."})
        try:
            msg = llm.chat(messages, tools=None if last else specs)
        except Exception as e:
            emit("error", str(e)[:200])
            return ""
        calls = getattr(msg, "tool_calls", None) or []
        if not calls:
            return (msg.content or "").strip()
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": c.id, "type": "function",
             "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}} for c in calls]})
        for c in calls:
            try:
                args = json.loads(c.function.arguments or "{}")
            except Exception:
                args = {}
            emit("tool", f"{c.function.name} {json.dumps(args, ensure_ascii=False)[:220]}")
            obs = toolkit.execute(c.function.name, args)
            if obs.startswith("ERROR"):
                emit("error", obs[:200])
            messages.append({"role": "tool", "tool_call_id": c.id, "content": obs[:3500]})
    return ""


def overview(state, n=5):
    if not state.datasets:
        return "(no dataset)"
    return "\n\n".join(f"Dataset '{k}' ({len(d['rows'])} rows)\n{fmt_table(d['columns'], d['rows'], n)}"
                       for k, d in state.datasets.items())


def run_sql_agent(llm, tk, state, task, emit, max_steps, retry_note=""):
    user = f"Manager question: {state.question}\nYour task: {task}\n{retry_note}"
    return tool_loop(llm, SQL_SYSTEM, user, SQL_TOOLS, tk, max_steps, emit)


def run_analyst_agent(llm, tk, state, task, emit, max_steps):
    user = f"Manager question: {state.question}\nYour task: {task}\nAvailable data:\n{overview(state)}"
    return tool_loop(llm, ANALYST_SYSTEM, user, ANALYST_TOOLS, tk, max_steps, emit)


def run_forecast_agent(llm, tk, state, task, emit, max_steps):
    user = f"Manager question: {state.question}\nYour task: {task}\nAvailable data:\n{overview(state)}"
    return tool_loop(llm, FORECAST_SYSTEM, user, FORECAST_TOOLS, tk, max_steps, emit)


def run_advisor_agent(llm, tk, state, task, emit, max_steps):
    facts = "\n\n".join(f"[{f['agent']}] {f['text']}" for f in state.findings if f["text"]) or "(no findings)"
    user = (f"Manager question: {state.question}\nTask: {task}\n\nFindings from the other agents:\n{facts}\n\n"
            f"Data extracts:\n{overview(state, 8)}")
    try:
        msg = llm.chat([{"role": "system", "content": ADVISOR_SYSTEM.format(lang=LANGS.get(state.lang, "French"))},
                        {"role": "user", "content": user}], temperature=0.3)
        state.answer = (msg.content or "").strip()
    except Exception as e:
        emit("error", str(e)[:200])
    return state.answer


AGENTS = {"sql": run_sql_agent, "analyst": run_analyst_agent,
          "forecast": run_forecast_agent, "advisor": run_advisor_agent}
