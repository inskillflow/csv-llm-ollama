# csv-llm-ollama

Application Streamlit qui analyse un CSV de transactions bancaires et te
laisse poser des questions en langage naturel, **100 % local** via Ollama.

- Port : **8504**
- LLM : `llama3.1:8b` (par défaut, modifiable dans la sidebar)
- DB : SQLite locale (`.cache/csv-llm-ollama.sqlite`)
- Données : tes transactions ne sortent jamais de la machine.

## Prérequis

```powershell
# 1. Ollama
winget install Ollama.Ollama       # ou https://ollama.com/download
ollama serve                        # à laisser tourner dans une fenêtre

# 2. Modèle (tool-calling)
ollama pull llama3.1:8b

# 3. Dépendances Python (depuis la racine du repo)
pip install -r csv-llm-ollama/requirements.txt
```

## Lancement

```powershell
# Méthode courte
.\csv-llm-ollama\start.ps1

# Méthode manuelle
streamlit run csv-llm-ollama/app.py --server.port 8504
```

Ouvre http://127.0.0.1:8504.

## Premier import

Dans la sidebar, le chemin par défaut est
`site/data/data1-anonymized.csv` (734 lignes anonymisées). Clique sur
**(Re)charger ce CSV** : 733 transactions seront chargées dans le profil
`data1`.

## Questions canoniques à essayer

- *Combien j'ai dépensé en épicerie le mois dernier ?*
- *Quelle est ma plus grosse catégorie de dépenses ?*
- *Combien de fois suis-je allé chez Coffee Gossip cette année et combien j'ai dépensé au total ?*
- *Liste mes 5 plus gros marchands.*

Chaque réponse affiche :
- la requête SQL générée par le modèle,
- les lignes retournées par SQLite,
- la réponse en français.
