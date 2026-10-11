# -*- coding: utf-8 -*-
import os
import re
import random
from typing import Dict, Any

from dotenv import load_dotenv
from src.etl.core.sql_agent import NLPtoSQLAgent, AgentConfig

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise Exception("GROQ_API_KEY manquante. Verifie ton fichier .env")

agent = NLPtoSQLAgent(AgentConfig(
    db_url=os.getenv("DB_URL", "postgresql://postgres:dariaaya@localhost:5432/olist_db"),
    groq_api_key=api_key,
    model="llama-3.3-70b-versatile",
    temperature=0.0,
    verbose=True,
))

# ── Détection salutations ──
SALUTATIONS = {
    "bonjour","salut","hello","hi","hey","bonsoir","salam","labas",
    "ahlan","wakha","مرحبا","السلام عليكم","صباح الخير",
}

# ── Mots clés qui indiquent une vraie question de données ──
SQL_KEYWORDS = [
    "combien","quel","quels","quelle","quelles","montre","affiche",
    "liste","top","meilleur","total","moyenne","somme","nombre",
    "vente","commande","client","vendeur","produit","livraison",
    "paiement","note","avis","revenu","chiffre","evolution",
    "distribution","repartition","delai","retard","etat","ville",
    "how many","what","show","list","best","average","count","which",
    "orders","sales","revenue","customers","sellers","products",
    "delivery","payment","shhal","chhal","ktar","bzzaf",
    "كم","ما","اظهر","قائمة","أفضل","إجمالي","متوسط",
]

def detect_language(t):
    if len(re.findall(r'[\u0600-\u06FF]', t)) > 2: return "arabic"
    if any(w in t.lower() for w in ["labas","wach","chokran","wakha","salam","shhal","chhal"]): return "darija"
    if any(w in t.lower() for w in ["how","what","show","list","best","orders","sales"]): return "english"
    return "french"

def is_salutation(q: str) -> bool:
    q_clean = q.lower().strip().rstrip("!.,?")

    # salutation exacte
    if q_clean in SALUTATIONS:
        return True

    # salutation + petite phrase MAIS sans intention data
    words = q_clean.split()

    has_data_signal = any(kw in q_clean for kw in SQL_KEYWORDS)

    if len(words) <= 2 and not has_data_signal:
        return True

    return False

def is_data_question(q: str) -> bool:
    q = q.lower().strip()

    # si question très courte → vérifier quand même mots clés forts
    if len(q.split()) <= 2:
        return any(kw in q for kw in SQL_KEYWORDS)

    # score simple (plus robuste)
    score = sum(1 for kw in SQL_KEYWORDS if kw in q)

    return score >= 1
def get_greeting_response(question: str) -> str:
    lang = detect_language(question)
    q = question.lower()

    if any(s in q for s in ["ca va","cava","comment tu vas","how are you","labas 3lik"]):
        return {
            "french": "Je vais très bien ! Comment puis-je vous aider avec les données Olist ?",
            "english": "I'm doing great! How can I help you with Olist data?",
            "arabic": "أنا بخير! كيف يمكنني مساعدتك؟",
            "darija": "Labas hamdullah! Kifach ymkn liya n3awnak?",
        }.get(lang, "Je vais bien !")

    if any(s in q for s in ["bonjour","salut","hello","hi","hey","salam","labas","مرحبا","ahlan"]):
        opts = {
            "french": [
                "Bonjour ! Comment puis-je vous aider avec les données Olist ?",
                "Salut ! Prêt à analyser vos données e-commerce ?",
                "Bonjour ! Posez-moi une question sur les ventes, clients ou commandes.",
            ],
            "english": [
                "Hello! How can I help you with Olist data today?",
                "Hi there! Ready to explore your e-commerce data?",
            ],
            "arabic": ["مرحبا! كيف يمكنني مساعدتك في تحليل بيانات Olist؟"],
            "darija": ["Salam! Kifach ymkn liya n3awnak f analyse d'data Olist?"],
        }
        return random.choice(opts.get(lang, opts["french"]))

    if any(s in q for s in ["merci","thanks","thank","شكرا","chokran","bravo","super","parfait"]):
        return {
            "french": "Avec plaisir ! N'hésitez pas si vous avez d'autres questions.",
            "english": "You're welcome! Feel free to ask more questions.",
            "arabic": "على الرحب والسعة!",
            "darija": "Bla jmil! Suwel iya mra okhra.",
        }.get(lang, "Avec plaisir !")

    if any(s in q for s in ["qui es tu","who are you","c quoi","what is","olist"]):
        return {
            "french": "Je suis **DataOlist AI**, un assistant spécialisé dans l'analyse des données e-commerce Olist. Je réponds à vos questions sur les ventes, clients, commandes et livraisons.",
            "english": "I'm **DataOlist AI**, specialized in Olist e-commerce data analysis.",
            "arabic": "أنا **DataOlist AI**، متخصص في تحليل بيانات Olist.",
            "darija": "Ana **DataOlist AI**, mkhss f analyse d'data Olist.",
        }.get(lang, "Je suis DataOlist AI.")

    return {
        "french": "Je suis spécialisé dans l'analyse des données **Olist**. Posez-moi une question sur les ventes, clients, vendeurs ou livraisons.",
        "english": "I specialize in **Olist** data analysis. Ask me about sales, customers, or deliveries.",
        "arabic": "أنا متخصص في تحليل بيانات Olist. اسألني عن المبيعات أو العملاء.",
        "darija": "Ana mkhss f data Olist. Suwel iya!",
    }.get(lang, "Posez-moi une question sur Olist.")


def _empty_result(answer: str) -> Dict[str, Any]:
    """Réponse plate (salutation, message vague...) — pas de données associées."""
    return {
        "answer": answer,
        "chart": None,
        "needs_chart": False,
        "suggestions": [],
        "table": None,
    }


def process_question_api(question: str) -> Dict[str, Any]:
    """
    NOUVEAU (v2) : retourne désormais un dict complet (answer, chart,
    needs_chart, suggestions, table) au lieu d'une simple chaîne, pour que
    app.py puisse transmettre le graphe au frontend même quand la question
    passe par ce chemin de secours (routage 'business' sans match KB, etc).
    """
    if not question or len(question.strip()) < 2:
        return _empty_result("Pouvez-vous préciser votre question ?")

    q = question.lower().strip()

    # 1. salutation PRIORITAIRE
    if is_salutation(q):
        return _empty_result(get_greeting_response(q))

    # 2. blocage sécurité (mots trop vagues)
    vague_words = {"ventes", "clients", "produits", "commandes"}
    if q in vague_words:
        return _empty_result("Pouvez-vous préciser votre question ? (ex: top ventes, nombre de clients...)")

    # 3. question data → SQL (avec graphe + suggestions)
    if is_data_question(q):
        result = agent.query(question)
        df = result.get("dataframe")
        table = df.head(50).to_dict("records") if df is not None and not df.empty else None

        return {
            "answer": result.get("answer", "OK"),
            "chart": result.get("chart"),
            "needs_chart": result.get("needs_chart", False),
            "suggestions": result.get("suggestions", []),
            "table": table,
        }

    # 4. fallback chat
    return _empty_result(get_greeting_response(q))