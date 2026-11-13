"""Superviseur : planifie quels agents appeler, les orchestre et gère les échecs."""
import json
import re
import time

from . import config
from .agents import AGENTS
from .state import BIState
from .tools import Toolkit

PLAN_SYSTEM = (
    "You are the Supervisor of a team of business-intelligence agents. Agents:\n"
    "- sql: queries the company database and builds datasets (always first)\n"
    "- analyst: computes statistics and extracts insights from datasets\n"
    "- forecast: forecasts monthly time series (use ONLY if the question is about the future, forecast, "
    "prévision, next months or evolution over time)\n"
    "- advisor: writes the final answer and recommendations (always last)\n"
    'Return JSON only: {"steps": [{"agent": "sql", "task": "precise task"}, ...]} with 3 to 4 steps.'
)


def safe_json(text):
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text or "", re.S)
        try:
            return json.loads(m.group(0)) if m else {}
        except Exception:
            return {}


class Supervisor:
    def __init__(self, llm, conn, on_event=None, max_steps=None):
        self.llm, self.conn, self.on_event = llm, conn, on_event
        self.max_steps = max_steps or config.MAX_STEPS

    def emit(self, agent, kind, msg):
        if self.on_event:
            self.on_event({"t": time.strftime("%H:%M:%S"), "agent": agent, "kind": kind, "msg": msg})

    def make_plan(self, state):
        try:
            msg = self.llm.chat([{"role": "system", "content": PLAN_SYSTEM},
                                 {"role": "user", "content": state.question}], json_mode=True)
            raw = safe_json(msg.content).get("steps") or []
        except Exception as e:
            self.emit("supervisor", "error", f"Planification : {e}"[:200])
            raw = []
        steps = [s for s in raw if isinstance(s, dict) and s.get("agent") in AGENTS and s["agent"] != "advisor"]
        if not any(s["agent"] == "sql" for s in steps):
            steps.insert(0, {"agent": "sql", "task": f"Retrieve the data needed to answer: {state.question}"})
        steps.sort(key=lambda s: s["agent"] != "sql")  # sql toujours en premier (tri stable)
        steps = steps[:4]
        steps.append({"agent": "advisor", "task": "Answer the question and give prioritized recommendations."})
        state.plan = steps
        self.emit("supervisor", "plan", " → ".join(f"{s['agent']}" for s in steps))

    def run(self, question, lang="fr"):
        state = BIState(question=question, lang=lang)
        tk = Toolkit(self.conn, state)
        self.make_plan(state)
        for step in state.plan:
            name, task = step["agent"], step.get("task", "")
            emit = lambda kind, msg, n=name: self.emit(n, kind, msg)
            if name in ("analyst", "forecast") and not state.datasets:
                self.emit("supervisor", "skip", f"{name} ignoré : aucune donnée disponible")
                continue
            self.emit("supervisor", "dispatch", f"{name} ← {task}"[:200])
            text = AGENTS[name](self.llm, tk, state, task, emit, self.max_steps)
            if name == "sql" and not state.datasets:  # récupération d'erreur : une 2e tentative guidée
                self.emit("supervisor", "retry", "Aucune donnée obtenue : nouvelle tentative du SQL Agent")
                text = AGENTS[name](self.llm, tk, state, task, emit, self.max_steps,
                                    retry_note="Your previous attempt saved no dataset. Re-read the schema, "
                                               "simplify the query and save at least one dataset.")
            if name != "advisor":
                state.findings.append({"agent": name, "text": text})
                self.emit(name, "result", (text or "(vide)")[:300])
        if not state.answer:
            state.answer = "Je n'ai pas pu produire de réponse (voir les logs de l'agent)."
        self.emit("supervisor", "done", f"{len(state.datasets)} dataset(s), {len(state.forecasts)} prévision(s)")
        return state
