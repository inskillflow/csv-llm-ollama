"""llm.py — agent Ollama avec tool-calling SQL.

Le modèle reçoit un seul outil `query_sql(sql)` qui exécute un SELECT en
lecture seule sur la base SQLite locale. Le modèle écrit le SQL, on
l'exécute, on lui renvoie le résultat sous forme de texte tabulaire, il
formule la réponse en langage naturel.

Boucle de l'agent :
    1. user message -> ollama.chat(model, messages, tools)
    2. si la réponse contient `tool_calls`, on appelle l'outil correspondant
       et on injecte la réponse dans `messages`, on reboucle.
    3. sinon, on renvoie le contenu textuel.

Le modèle par défaut est `llama3.1:8b` (~4.7 Go, supporte tool calling).
Tu peux aussi essayer `qwen2.5:7b` ou `mistral` qui supportent les outils.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ollama
import pandas as pd

import db


SYSTEM_PROMPT = """Tu es un assistant qui répond à des questions en langage \
naturel sur les transactions bancaires de l'utilisateur.

La base de données SQLite contient une table unique :

    transactions(
        id INTEGER PRIMARY KEY,
        date TEXT,                 -- ISO 'YYYY-MM-DD'
        card TEXT,                 -- numéro de carte masqué
        description TEXT,          -- libellé du marchand
        category TEXT,             -- catégorie en français (ex: 'Cafés', 'Épicerie')
        amount REAL,               -- montant signé : positif = dépense, négatif = remboursement
        profile TEXT               -- identifiant de la carte
    )

Pour répondre, utilise toujours l'outil `query_sql(sql)` qui exécute un \
SELECT en lecture seule. Ne fais JAMAIS de calculs à la main : passe par SQL.

Conventions importantes :
- Les dépenses sont les lignes où `amount > 0`.
- Pour 'le mois dernier' relatif à la date du jour, utilise \
  `date >= date('now', 'start of month', '-1 month')` et \
  `date < date('now', 'start of month')`.
- Pour 'cette année', utilise `strftime('%Y', date) = strftime('%Y', 'now')`.
- Les catégories portent des accents : 'Cafés', 'Épicerie', 'Hébergement web', \
  'Vêtements', 'Salle d'entraînement', 'Rénovations', 'Éducation', 'Hôtel', \
  'Publicité', 'Optométriste', 'Paiement carte de crédit', 'Électroniques et logiciels'.
- Toujours arrondir les montants avec `ROUND(x, 2)`.
- Si la question demande un total ou un montant, montre la valeur en dollars \
  avec deux décimales et explique brièvement la requête.
- Quand on parle de **marchands** (« top marchands », « les plus gros \
  marchands », « chez qui je dépense le plus »), il faut **agréger par \
  `description`** avec `GROUP BY description` puis `SUM(amount)`, et exclure \
  les paiements de carte (`category != 'Paiement carte de crédit'` et \
  `amount > 0`).

Quand tu reçois le résultat de `query_sql`, analyse-le et réponds en français \
avec un ton concis et clair. La devise est le dollar canadien.
"""


SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "query_sql",
        "description": "Execute a SELECT (read-only) on the local SQLite "
                       "transactions table and return up to 1000 rows.",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "Valid SQLite SELECT statement against table `transactions`."
                }
            },
            "required": ["sql"],
        },
    },
}


@dataclass
class Trace:
    """Trace d'un échange : utile pour afficher dans l'UI."""
    sql_calls: list[dict[str, Any]] = field(default_factory=list)
    final_text: str = ""
    raw_messages: list[dict[str, Any]] = field(default_factory=list)


def _format_result_for_llm(df: pd.DataFrame, max_rows: int = 30) -> str:
    """Convertit un DataFrame en texte tabulaire compact pour le LLM."""
    if df.empty:
        return "(aucune ligne)"
    head = df.head(max_rows)
    s = head.to_string(index=False)
    if len(df) > max_rows:
        s += f"\n... ({len(df) - max_rows} lignes de plus, total {len(df)})"
    return s


DEFAULT_HOST = "http://127.0.0.1:11434"


def ask(
    question: str,
    db_path: str | Path,
    model: str = "llama3.1:8b",
    host: str | None = None,
    max_steps: int = 5,
) -> Trace:
    """Pose une question au LLM avec accès à l'outil `query_sql`. Retourne une Trace."""
    client = ollama.Client(host=host or DEFAULT_HOST)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    trace = Trace()

    for step in range(max_steps):
        response = client.chat(
            model=model,
            messages=messages,
            tools=[SQL_TOOL],
        )
        msg = response["message"]
        messages.append(msg)
        trace.raw_messages.append(dict(msg))

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            trace.final_text = msg.get("content", "").strip()
            return trace

        for call in tool_calls:
            fn = call["function"]
            name = fn["name"]
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"sql": args}
            sql = args.get("sql", "")

            entry = {"step": step, "name": name, "sql": sql, "result": None, "error": None}
            try:
                if name == "query_sql":
                    df = db.safe_query(sql, db_path, max_rows=1000)
                    entry["result"] = df
                    tool_text = _format_result_for_llm(df)
                else:
                    tool_text = f"Outil inconnu : {name}"
                    entry["error"] = tool_text
            except Exception as e:
                tool_text = f"Erreur d'exécution SQL : {e}"
                entry["error"] = str(e)
            trace.sql_calls.append(entry)

            messages.append({
                "role": "tool",
                "content": tool_text,
                "name": name,
            })

    trace.final_text = "(le modèle a dépassé le nombre maximum d'appels d'outils)"
    return trace
