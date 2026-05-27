"""app.py — Streamlit UI : analyse de dépenses CSV avec un LLM Ollama local.

Lancer :
    streamlit run csv-llm-ollama/app.py --server.port 8504
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

# csv-llm-shared est un repo SIBLING de csv-llm-ollama.
# Layout attendu : 00-dream/{csv-llm-ollama,csv-llm-shared}
HERE = Path(__file__).resolve().parent          # csv-llm-ollama/
SHARED = HERE.parent / "csv-llm-shared"
if not SHARED.exists():
    raise RuntimeError(
        f"csv-llm-shared introuvable a {SHARED}. "
        "Clone le repo csv-llm-shared a cote de csv-llm-ollama."
    )
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import dashboards
import db
import ingest
import normalize
import llm  # local


DEFAULT_DB = HERE / ".cache" / "csv-llm-ollama.sqlite"
DEFAULT_CSV = HERE.parent / "ollama-streamlit" / "site" / "data" / "data1-anonymized.csv"


st.set_page_config(
    page_title="Dépenses + LLM (Ollama)",
    page_icon="💳",
    layout="wide",
)


# ----- helpers -------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_data_into_db(csv_path: str, profile: str, db_path: str) -> int:
    """Charge un CSV dans la DB. Retourne le nb de lignes inserees."""
    df_raw = ingest.read_csv(csv_path)
    df_norm = normalize.normalize(df_raw, profile=profile)
    db.init(db_path)
    db.reset(db_path, profile=profile)
    return db.insert_dataframe(df_norm, db_path, profile=profile)


def get_data(db_path: str, profile: str | None) -> pd.DataFrame:
    return db.fetch_all(db_path, profile=profile)


# ----- sidebar -------------------------------------------------------------

with st.sidebar:
    st.title("💳 Profils & données")

    db_path = str(DEFAULT_DB)
    DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)

    st.caption("Source CSV initiale :")
    csv_input = st.text_input("Chemin CSV", value=str(DEFAULT_CSV))

    profile = st.text_input("Nom du profil", value="data1")

    col_a, col_b = st.columns(2)
    if col_a.button("📥 (Re)charger ce CSV", use_container_width=True):
        try:
            n = load_data_into_db(csv_input, profile, db_path)
            st.success(f"{n} transactions chargées dans `{profile}`.")
        except Exception as e:
            st.error(f"Erreur : {e}")

    upload = st.file_uploader("…ou téléverser un CSV", type=["csv"])
    if upload is not None:
        try:
            df_raw = ingest.read_csv(upload)
            df_norm = normalize.normalize(df_raw, profile=profile)
            db.init(db_path)
            n = db.insert_dataframe(df_norm, db_path, profile=profile)
            st.success(f"{n} transactions ajoutées à `{profile}`.")
        except Exception as e:
            st.error(f"Erreur : {e}")

    st.divider()
    db.init(db_path)
    profiles = db.list_profiles(db_path) or [profile]
    chosen = st.selectbox("Profil actif", profiles, index=0)

    if col_b.button("🗑️ Vider ce profil", use_container_width=True):
        n = db.reset(db_path, profile=chosen)
        st.warning(f"{n} lignes supprimées.")
        st.rerun()

    st.divider()
    st.caption("**Modèle Ollama**")
    model = st.text_input("Modèle", value="llama3.1:8b",
                          help="Doit supporter tool calling (llama3.1, qwen2.5, mistral...).")
    host = st.text_input("Ollama host", value="",
                         placeholder="http://127.0.0.1:11434 (laisser vide pour défaut)")


# ----- main ----------------------------------------------------------------

st.title("Analyse des dépenses par carte — parcours **Ollama** (local)")
st.caption(
    "Tes données restent sur ta machine : Ollama tourne en local et la base "
    "SQLite est créée sous `.cache/csv-llm-ollama.sqlite`."
)

df = get_data(db_path, profile=chosen)
if df.empty:
    st.info("Aucune transaction pour ce profil. Charge un CSV depuis la sidebar.")
    st.stop()


tab_dash, tab_tx, tab_chat = st.tabs(["📊 Dashboards", "📋 Transactions", "💬 Chat"])

# --- Dashboards ---------------------------------------------------------
with tab_dash:
    kpis = dashboards.kpi_totals(df)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dépense totale",
              f"{kpis['total']:,.2f} $".replace(",", " "))
    c2.metric("Dépense mensuelle moyenne",
              f"{kpis['monthly_avg']:,.2f} $".replace(",", " "))
    c3.metric("Transaction moyenne",
              f"{kpis['transaction_avg']:,.2f} $".replace(",", " "))
    c4.metric("Nb transactions (dépenses)", f"{kpis['n_transactions']}")

    st.divider()

    # Filtres
    fc1, fc2 = st.columns(2)
    with fc1:
        all_cats = sorted(c for c in df["category"].dropna().unique() if c)
        sel_cats = st.multiselect("Catégories", all_cats,
                                  default=all_cats,
                                  help="Filtre les dashboards")
    with fc2:
        min_d, max_d = df["date"].min(), df["date"].max()
        sel_dates = st.date_input(
            "Plage de dates",
            value=(min_d.date(), max_d.date()),
            min_value=min_d.date(),
            max_value=max_d.date(),
        )

    f = df.copy()
    if sel_cats:
        f = f[f["category"].isin(sel_cats)]
    if isinstance(sel_dates, tuple) and len(sel_dates) == 2:
        f = f[(f["date"] >= pd.Timestamp(sel_dates[0])) &
              (f["date"] <= pd.Timestamp(sel_dates[1]))]

    g1, g2 = st.columns(2)
    g1.plotly_chart(dashboards.fig_monthly(f), use_container_width=True)
    g2.plotly_chart(dashboards.fig_by_category(f), use_container_width=True)

    g3, g4 = st.columns(2)
    g3.plotly_chart(dashboards.fig_top_merchants(f, n=10), use_container_width=True)
    g4.plotly_chart(dashboards.fig_recurring(f, min_count=3), use_container_width=True)


# --- Transactions -------------------------------------------------------
with tab_tx:
    st.subheader(f"{len(df)} transactions  · profil `{chosen}`")
    f = df.sort_values("date", ascending=False)
    st.dataframe(
        f[["date", "card", "description", "category", "amount"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "date": st.column_config.DateColumn("Date"),
            "amount": st.column_config.NumberColumn("Montant ($)", format="%.2f"),
        },
    )


# --- Chat ----------------------------------------------------------------
with tab_chat:
    st.subheader("Chat avec mes dépenses")
    st.caption(
        f"Modèle : `{model}` (tool calling SQL en lecture seule sur "
        f"`{Path(db_path).name}`, profil `{chosen}`)"
    )

    if "history" not in st.session_state:
        st.session_state.history = []

    with st.expander("💡 Exemples de questions"):
        st.markdown(
            "- *Combien j'ai dépensé en épicerie le mois dernier ?*\n"
            "- *Quelle est ma plus grosse catégorie de dépenses ?*\n"
            "- *Combien de fois suis-je allé chez Coffee Gossip cette année et combien j'ai dépensé au total ?*\n"
            "- *Liste mes 5 plus gros marchands.*"
        )

    for h in st.session_state.history:
        with st.chat_message(h["role"]):
            st.markdown(h["content"])
            for c in h.get("calls", []):
                with st.expander(f"🔧 SQL #{c['step']+1}"):
                    st.code(c["sql"], language="sql")
                    if c.get("error"):
                        st.error(c["error"])
                    elif c.get("result") is not None:
                        st.dataframe(c["result"], use_container_width=True, hide_index=True)

    question = st.chat_input("Pose ta question…")
    if question:
        st.session_state.history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("⏳ Le modèle réfléchit…")
            t0 = time.time()
            try:
                trace = llm.ask(
                    question=question,
                    db_path=db_path,
                    model=model,
                    host=host or None,
                )
                dt = time.time() - t0
                placeholder.empty()
                st.markdown(trace.final_text or "_(réponse vide)_")
                st.caption(f"⏱️ {dt:.1f} s · {len(trace.sql_calls)} appel(s) SQL")
                for c in trace.sql_calls:
                    with st.expander(f"🔧 SQL #{c['step']+1}"):
                        st.code(c["sql"], language="sql")
                        if c.get("error"):
                            st.error(c["error"])
                        elif c.get("result") is not None:
                            st.dataframe(c["result"], use_container_width=True, hide_index=True)
                st.session_state.history.append({
                    "role": "assistant",
                    "content": trace.final_text or "_(réponse vide)_",
                    "calls": trace.sql_calls,
                })
            except Exception as e:
                placeholder.empty()
                st.error(f"Erreur Ollama : {e}\n\n"
                         f"Vérifie que `ollama serve` tourne et que le modèle "
                         f"est installé (`ollama pull {model}`).")
