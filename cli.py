"""Usage : python cli.py "Quelle est l'évolution du CA ?" --lang fr"""
import argparse
import os

from app import config, db
from app.llm import LLM
from app.supervisor import Supervisor


def main():
    p = argparse.ArgumentParser()
    p.add_argument("question")
    p.add_argument("--lang", default="fr", choices=["fr", "en", "ar"])
    a = p.parse_args()
    if not os.path.exists(config.DB_PATH):
        import seed
        seed.build(config.DB_PATH)
    sup = Supervisor(LLM(), db.connect_ro(), on_event=lambda e: print(f"[{e['t']}] {e['agent']:<10} {e['kind']:<9} {e['msg']}"))
    state = sup.run(a.question, a.lang)
    print("\n" + state.answer)


if __name__ == "__main__":
    main()
