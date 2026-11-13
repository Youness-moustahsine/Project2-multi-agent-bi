"""API FastAPI : exécute le superviseur en tâche de fond, expose logs, réponse, datasets et prévisions."""
import os
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config, db
from .llm import LLM
from .supervisor import Supervisor

if not os.path.exists(config.DB_PATH):
    import seed
    print("Base de démonstration créée :", seed.build(config.DB_PATH))

app = FastAPI(title="Multi-Agent Business Intelligence")
JOBS: dict = {}
STATIC = Path(__file__).parent / "static"


class Ask(BaseModel):
    question: str
    lang: str = "fr"


def _worker(job_id, question, lang):
    job = JOBS[job_id]
    try:
        conn = db.connect_ro()  # connexion propre au thread, en lecture seule
        state = Supervisor(LLM(), conn, on_event=job["events"].append).run(question, lang)
        job.update(
            status="done", answer=state.answer, plan=[s["agent"] for s in state.plan],
            datasets={k: {"columns": d["columns"], "rows": d["rows"][:60], "sql": d["sql"]}
                      for k, d in state.datasets.items()},
            forecasts=state.forecasts)
    except Exception as e:
        job["events"].append({"t": "", "agent": "supervisor", "kind": "error", "msg": str(e)})
        job.update(status="error", error=str(e))


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/schema")
def schema():
    return {"schema": db.schema_description(db.connect_ro())}


@app.post("/api/ask")
def ask(req: Ask):
    if not req.question.strip():
        raise HTTPException(400, "question vide")
    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"status": "running", "events": [], "answer": "", "datasets": {}, "forecasts": {}}
    threading.Thread(target=_worker, args=(job_id, req.question.strip(), req.lang), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "job inconnu")
    return JOBS[job_id]
