print("APP.PY EXECUTE")

import sys
import os
import re
import math
import difflib
from typing import Optional

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Rate limit Groq
# ─────────────────────────────────────────────
def is_rate_limit_error(exception: Exception) -> bool:
    msg = str(exception)
    return "429" in msg or "rate_limit_exceeded" in msg or "Rate limit reached" in msg


def extract_retry_delay(exception: Exception) -> str:
    match = re.search(r"try again in ([\d.]+m)?([\d.]+s)?", str(exception))
    if match:
        return f"{match.group(1) or ''}{match.group(2) or ''}".strip()
    return "quelques minutes"


def get_rate_limit_message(exception: Exception) -> str:
    delay = extract_retry_delay(exception)
    return (
        " Le quota quotidien de l'API Groq est temporairement épuisé. "
        f"Réessayez dans environ {delay}."
    )


from src.etl.core.sql_agent import NLPtoSQLAgent, AgentConfig
from chatbot_backend import process_question_api
from src.etl.core.rag_agent import RAGAgent
from file_analyzer import analyze_uploaded_file

from werkzeug.utils import secure_filename
import tempfile


# ─────────────────────────────────────────────
# Flask setup
# ─────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret")
CORS(app, supports_credentials=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

DB_URL = os.getenv(
    "DB_URL",
    f"postgresql://{os.getenv('DB_USER','postgres')}:{os.getenv('DB_PASSWORD','')}@"
    f"{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','olist_db')}"
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAISS_PATH = os.path.join(BASE_DIR, "faiss_olist_index")


# ─────────────────────────────────────────────
# Agents
# ─────────────────────────────────────────────
sql_agent = NLPtoSQLAgent(AgentConfig(
    db_url=DB_URL,
    groq_api_key=GROQ_API_KEY,
    model="llama-3.3-70b-versatile",
    max_rows_returned=100,
    temperature=0.0,
    max_retries=1,
    verbose=True,
))

rag_agent = RAGAgent(
    groq_api_key=GROQ_API_KEY,
    pdf_folder=os.path.join(BASE_DIR, "data", "documents"),
    faiss_index_path=FAISS_PATH,
)

if not rag_agent.load_index():
    print("Index RAG introuvable → création depuis PDFs")
    rag_agent.load_pdfs_from_folder()
    rag_agent.save_index()
else:
    print("Index RAG chargé")

print(f"[STARTUP] chunks={len(rag_agent.chunks)}")


# ─────────────────────────────────────────────
# BUSINESS KNOWLEDGE BASE
# ─────────────────────────────────────────────
BUSINESS_KNOWLEDGE = {
    "calcul_revenue": {
        "keywords": ["calculer le revenu", "calcul revenue", "chiffre d'affaires"],
        "answer": "Le revenu correspond aux commandes livrées et payées..."
    },
    "gmv_vs_revenue": {
        "keywords": ["gmv", "difference gmv", "gmv vs revenue"],
        "answer": "GMV = valeur totale commandée, Revenue = encaissé réel."
    }
}


def check_business_knowledge(q: str) -> Optional[str]:
    q = q.lower()
    best_key, best_score = None, 0

    for key, entry in BUSINESS_KNOWLEDGE.items():
        score = sum(1 for kw in entry["keywords"] if kw in q)
        if score > best_score:
            best_key, best_score = key, score

    if best_key:
        return BUSINESS_KNOWLEDGE[best_key]["answer"]
    return None


# ─────────────────────────────────────────────
# ROUTING INTELLIGENT
# ─────────────────────────────────────────────
SQL_ROUTE_KEYWORDS = [
    "combien", "quel", "quels", "quelle", "quelles", "montre", "affiche",
    "liste", "top", "meilleur", "total", "moyenne", "somme", "nombre",
    "vente", "ventes", "commande", "client", "vendeur", "produit",
    "livraison", "paiement", "note", "avis", "revenu", "revenue",
    "chiffre", "gmv", "evolution", "évolution", "distribution",
    "repartition", "répartition", "camembert", "graphe", "graphique",
    "courbe", "histogramme", "pie", "bar", "chart",
]


def route_question(msg: str) -> str:
    msg = msg.lower()
    if any(k in msg for k in SQL_ROUTE_KEYWORDS):
        return "sql"
    return "rag"


# ─────────────────────────────────────────────
# HELPERS — safe_json CORRIGÉ (NaN/Inf → None)
# ─────────────────────────────────────────────
def safe_json(obj):
    """
    Sérialise récursivement un objet Python en structure JSON-compatible.
    Convertit NaN, Infinity et -Infinity en None (→ null en JSON) pour éviter
    l'erreur "Unexpected token 'N'... is not valid JSON" côté frontend.
    Gère également les types NumPy et les Timestamps pandas.
    """
    if obj is None:
        return None

    # ── Dictionnaire ──────────────────────────────────────────────────────────
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}

    # ── Liste / tuple ─────────────────────────────────────────────────────────
    if isinstance(obj, (list, tuple)):
        return [safe_json(x) for x in obj]

    # ── Entiers NumPy ─────────────────────────────────────────────────────────
    if isinstance(obj, (np.integer,)):
        return int(obj)

    # ── Flottants NumPy et Python natifs ──────────────────────────────────────
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        # NaN ou Infini → null JSON (évite "Unexpected token 'N'")
        if math.isnan(f) or math.isinf(f):
            return None
        return f

    # ── Booléens NumPy ────────────────────────────────────────────────────────
    if isinstance(obj, (np.bool_,)):
        return bool(obj)

    # ── Timestamps pandas → chaîne ISO ───────────────────────────────────────
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()

    # ── Tableau NumPy → liste ────────────────────────────────────────────────
    if isinstance(obj, np.ndarray):
        return [safe_json(x) for x in obj.tolist()]

    # ── Valeurs NaN de Python (float natif déjà traité, mais sécurité) ────────
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass

    return obj


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────
@app.route("/")
def home():
    return "API OK"


@app.route("/health")
def health():
    return jsonify({
        "rag_chunks": len(rag_agent.chunks),
        "rag_ready": rag_agent.is_indexed
    })


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json or {}
        msg = data.get("message", "").strip()

        if not msg:
            return jsonify({"error": "empty message"}), 400

        print("\nUSER:", msg)

        session.setdefault("history", [])
        session["history"].append(msg)

        route = route_question(msg)
        print("ROUTE:", route)

        # ─────────────────────────────
        # 1. BUSINESS KB
        # ─────────────────────────────
        kb = check_business_knowledge(msg)
        if kb:
            return jsonify({"answer": kb, "source": "kb"})

        # ─────────────────────────────
        # 2. SQL
        # ─────────────────────────────
        if route == "sql":
            result = sql_agent.query(msg)
            df = result.get("dataframe", pd.DataFrame())

            # Nettoyage DataFrame : NaN → None avant sérialisation
            if df is not None and not df.empty:
                df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
                table_data = safe_json(df.head(50).to_dict("records"))
            else:
                table_data = []

            return jsonify({
                "answer":      result.get("answer", "OK"),
                "table":       table_data,
                "chart":       safe_json(result.get("chart")),
                "needs_chart": result.get("needs_chart", False),
                "suggestions": result.get("suggestions", []),
                "source":      "sql",
            })

        # ─────────────────────────────
        # 3. RAG
        # ─────────────────────────────
        if route == "rag" and rag_agent.is_indexed:
            rag = rag_agent.ask(msg)
            if rag:
                return jsonify({"answer": rag, "source": "rag"})

        # ─────────────────────────────
        # 4. FALLBACK CHAT
        # ─────────────────────────────
        fallback = process_question_api(msg)

        # Nettoyage table fallback si présente
        fallback_table = fallback.get("table")
        if isinstance(fallback_table, list):
            fallback_table = safe_json(fallback_table)

        return jsonify({
            "answer":      fallback.get("answer", "OK"),
            "table":       fallback_table,
            "chart":       safe_json(fallback.get("chart")),
            "needs_chart": fallback.get("needs_chart", False),
            "suggestions": fallback.get("suggestions", []),
            "source":      "chat",
        })

    except Exception as e:
        print("ERROR:", e)
        if is_rate_limit_error(e):
            return jsonify({
                "answer": get_rate_limit_message(e),
                "source": "error",
            }), 200
        return jsonify({
            "answer": "Une erreur est survenue. Veuillez réessayer.",
            "error":  str(e),
            "source": "error",
        }), 200


@app.route("/upload-file", methods=["POST"])
def upload_file():
    try:
        if "file" not in request.files:
            return jsonify({"answer": "Aucun fichier reçu.", "source": "file"}), 400

        uploaded = request.files["file"]
        if not uploaded.filename:
            return jsonify({"answer": "Aucun fichier reçu.", "source": "file"}), 400

        allowed_ext = (".csv", ".xlsx", ".xls", ".pdf")
        filename = secure_filename(uploaded.filename)

        if not filename.lower().endswith(allowed_ext):
            return jsonify({
                "answer": "Seuls les fichiers CSV, Excel (.xlsx/.xls) et PDF sont acceptés.",
                "source": "file",
            }), 400

        suffix = os.path.splitext(filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            uploaded.save(tmp.name)
            tmp_path = tmp.name

        try:
            result = analyze_uploaded_file(tmp_path, filename, GROQ_API_KEY)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        # Nettoyage du résultat avant envoi JSON
        return jsonify(safe_json(result))

    except Exception as e:
        print("ERROR upload-file:", e)
        return jsonify({
            "answer": "Je n'ai pas pu analyser ce fichier pour le moment.",
            "source": "file",
            "error":  str(e),
        }), 200


@app.route("/reset", methods=["POST"])
def reset():
    session.clear()
    sql_agent.reset_memory()
    return jsonify({"status": "reset ok"})


@app.route("/rebuild-index", methods=["POST"])
def rebuild():
    rag_agent.clear_index()
    rag_agent.load_pdfs_from_folder()
    rag_agent.save_index()
    return jsonify({"status": "index rebuilt"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)