"""smoke_chat.py — pose une question canonique au LLM Ollama et vérifie la réponse.

Utilisé par verify.ps1.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent          # csv-llm-ollama/
SHARED = HERE.parent / "csv-llm-shared"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(HERE))

import llm  # noqa: E402


def main() -> int:
    db_path = SHARED / ".cache" / "verify.sqlite"
    if not db_path.exists():
        print(f"Base introuvable : {db_path}. Lance d'abord csv-llm-shared/smoke_pipeline.py.")
        return 1

    question = "Quelle est ma plus grosse catégorie de dépenses ?"
    print(f"Q : {question}")
    t0 = time.time()
    trace = llm.ask(question, db_path=db_path, model="llama3.1:8b", max_steps=4)
    elapsed = time.time() - t0

    print(f"Réponse en {elapsed:.1f}s, {len(trace.sql_calls)} appel(s) SQL :")
    print(trace.final_text)

    assert trace.sql_calls, "Aucun appel SQL"
    txt = trace.final_text.lower()
    ok = ("électroniques" in txt) or ("electroniques" in txt) or ("logiciels" in txt)
    assert ok, f"Réponse inattendue : {trace.final_text}"
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
