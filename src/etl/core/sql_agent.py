# -*- coding: utf-8 -*-
"""
sql_agent.py — VERSION CORRIGÉE v5
Corrections v2 (conservées) :
1. ANSWER_SYNTHESIS_PROMPT : priorité absolue aux données brutes, pas aux définitions
2. synthesize() : formate le DataFrame proprement avant injection dans le prompt
3. Ajout de to_sql_with_schema_hint() pour forcer l'année dans le SQL

Ajouts v3 (conservés) :
4. build_chart()        → décide si un graphe est pertinent + le construit (type, x_key, y_keys, data)
5. generate_suggestions() → génère 2-3 questions de suivi via le LLM
6. query() retourne désormais "chart", "needs_chart" et "suggestions"

Corrections v4 (conservées) :
7. build_chart() / bloc PIE : suppression des NaN dans la clé catégorielle
   AVANT le groupby (sinon "x_key": NaN casse JSON.parse côté frontend).
8. build_chart() / bloc PIE : conversion propre des libellés numériques
   (ex: numéro de mois 1.0/2.0/...) en chaînes "1", "2"... sans ".0",
   et tri numérique de l'axe x quand c'est pertinent (au lieu du tri
   alphabétique "1.0, 10.0, 11.0, 12.0, 2.0..." observé en prod).
9. build_chart() / bloc 8 : nettoyage final qui distingue valeur manquante
   numérique (-> 0) vs catégorielle (-> "N/A"), et neutralise tout résidu
   "1.0" dans la clé catégorielle.
10. Tous les messages d'erreur visibles par l'utilisateur ("Requête
    invalide.", "Je n'ai pas pu exécuter la requête correctement.") sont
    remplacés par un message neutre unique, sans jargon technique
    (pas de "requête", "SQL", "base de données").

Correction v5 (CETTE VERSION) :
11. AJOUT de _wants_chart() et EXPLICIT_CHART_KEYWORDS — ces éléments
    étaient référencés dans build_chart() mais jamais définis, ce qui
    provoquait un NameError dès qu'une requête SQL réussissait. Cette
    fonction impose une porte d'entrée STRICTE : le graphe n'est généré
    QUE si la question contient un mot-clé explicite de visualisation
    (graphique, courbe, camembert...) ou un mot-clé de cas évident déjà
    existant (évolution, répartition, comparaison...). Sans cela, même
    avec des données numériques exploitables, AUCUN graphe n'est généré.
"""
import math
import re
import os
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from sqlalchemy import create_engine, text
import pandas as pd
import numpy as np

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Message neutre unique affiché à l'utilisateur en cas d'échec, quel que
# soit le point de défaillance (SQL invalide, erreur d'exécution, aucun
# résultat...). Ne jamais mentionner "requête", "SQL" ou "base de données".
NO_DATA_MESSAGE = "Je n'ai pas cette information pour le moment."


def _jsonify_value(v):
    if v is None:
        return 0
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return 0
    return v


def safe_df(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace({
        np.nan: None,
        np.inf: None,
        -np.inf: None
    })


# ───────────────────────── CLEANER ─────────────────────────
def clean_final_answer(text: str) -> str:
    if not text:
        return text
    import re as _re

    # ── Masquer tout ID technique brut (hash/UUID 20+ caractères) ──
    text = _re.sub(r"\b[a-f0-9]{20,}\b", "", text, flags=_re.IGNORECASE)
    text = _re.sub(r"\s{2,}", " ", text)

    # Supprimer les lignes brutes (un chiffre seul sans contexte)
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if _re.match(r"^[\d\s.,]+$", stripped) and len(stripped) < 25:
            continue
        cleaned.append(line)
    text = "\n".join(cleaned).strip()

    # Supprimer les phrases dupliquées
    sentences = _re.split(r"(?<=[.!?])\s+", text)
    seen, unique = set(), []
    for s in sentences:
        key = _re.sub(r"\s+", " ", s.strip().lower())
        if key not in seen and key:
            seen.add(key)
            unique.append(s.strip())
    text = " ".join(unique)

    text = text.replace("gmv:", "").replace("revenue:", "")
    text = text.replace("|", " ").replace("•", "")
    text = _re.sub(r" {2,}", " ", text)
    return text.strip()


# ───────────────────────── CONFIG ─────────────────────────
@dataclass
class AgentConfig:
    db_url: str = "postgresql://user:password@localhost:5432/ecommerce"
    groq_api_key: str = ""
    model: str = "llama-3.3-70b-versatile"
    max_retries: int = 2
    max_rows_returned: int = 100
    temperature: float = 0.0
    verbose: bool = True


# ───────────────────────── SCHEMA ─────────────────────────
OLIST_SCHEMA_MINIMAL = """
TABLES:
orders(order_id, customer_id, order_status, order_purchase_timestamp,
       order_delivered_customer_date, order_estimated_delivery_date)
customers(customer_id, customer_unique_id, customer_city, customer_state)
order_items(order_id, product_id, seller_id, price, freight_value)
payments(order_id, payment_type, payment_installments, payment_value)
reviews(order_id, review_score, review_comment_message)
products(product_id, product_category_name)
sellers(seller_id, seller_city, seller_state)

NOMS EXACTS (ne jamais dévier) :
- Table avis        → reviews       (PAS order_reviews)
- Table paiements   → payments      (PAS order_payments)

RÈGLE AFFICHAGE PRODUITS/VENDEURS/CLIENTS (TOUJOURS RESPECTER) :
- Ne jamais SELECT product_id, seller_id, customer_id ou order_id seuls dans
  le résultat final visible par l'utilisateur.
- Pour "top produits" → utiliser products.product_category_name (PAS product_id)
- Pour "top vendeurs" → utiliser sellers.seller_city ou seller_state, jamais seller_id seul
  (sauf si la question demande explicitement un identifiant technique)
- Si aucune colonne lisible n'existe pour identifier l'entité, regrouper par
  catégorie ou localisation plutôt que par identifiant brut

FONCTIONS PostgreSQL :
- DATEDIFF interdit → utiliser EXTRACT(DAY FROM (date1 - date2))
- YEAR(col)  → EXTRACT(YEAR FROM col)
- MONTH(col) → EXTRACT(MONTH FROM col)
- Arrondi    → ROUND(x::numeric, 2)
- GROUP BY obligatoire si colonnes non agrégées dans SELECT

DONNÉES : couvre 2016–2018
DÉFINITIONS MÉTIER CRITIQUES (toujours respecter) :
- GMV    = SUM(order_items.price + order_items.freight_value)
           pour les commandes WHERE order_status = 'delivered'
- Revenue = SUM(payments.payment_value)
            pour les commandes WHERE order_status = 'delivered'
- Vente comptabilisée UNIQUEMENT si order_status = 'delivered'
- Commandes annulées (canceled), en attente (processing) → EXCLURE des KPI

EXEMPLES DE REQUÊTES CORRECTES :

-- Ventes totales 2017 (GMV)
SELECT ROUND(SUM(oi.price + oi.freight_value)::numeric, 2) AS gmv_2017
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
  AND EXTRACT(YEAR FROM o.order_purchase_timestamp) = 2017;

-- Revenue 2017
SELECT ROUND(SUM(p.payment_value)::numeric, 2) AS revenue_2017
FROM orders o
JOIN payments p ON o.order_id = p.order_id
WHERE o.order_status = 'delivered'
  AND EXTRACT(YEAR FROM o.order_purchase_timestamp) = 2017;
"""


# ───────────────────────── PROMPTS ─────────────────────────
TEXT_TO_SQL_PROMPT = PromptTemplate.from_template(
    "Tu es un expert PostgreSQL e-commerce Olist.\n"
    "SCHEMA ET RÈGLES MÉTIER :\n{schema}\n\n"
    "HISTORIQUE RÉCENT DE LA CONVERSATION (peut être vide) :\n{history}\n\n"
    "QUESTION ACTUELLE :\n{question}\n\n"
    "Si la question actuelle fait référence à une question précédente "
    "(ex: \"et pour les vendeurs ?\", \"montre la même chose par mois\", "
    "\"et en 2018 ?\"), utilise l'historique ci-dessus pour comprendre "
    "précisément ce qui est demandé. Si la question est autonome, ignore "
    "l'historique.\n\n"
    "RÈGLE IMPORTANTE SUR LE NIVEAU DE DÉTAIL :\n"
    "- Si la question demande explicitement un 'détail', 'liste détaillée', "
    "'chaque commande', 'chaque vente', 'ligne par ligne', 'toutes les colonnes' "
    "→ NE PAS AGRÉGER. Pas de GROUP BY, pas de SUM/COUNT/AVG. Retourne les lignes "
    "brutes avec un JOIN approprié entre orders, order_items, payments, customers.\n"
    "- Si la question demande un 'résumé', 'total', 'évolution', 'par mois', "
    "'par année', 'top N' → AGRÉGER normalement avec GROUP BY.\n"
    "- Si la question est vague (ex: 'montre les ventes' sans précision) "
    "→ par défaut, retourne les lignes détaillées (pas d'agrégation), "
    "limitées à {max_rows} lignes, avec les colonnes les plus pertinentes "
    "(date, montant, statut, ville client).\n\n"
    "Retourne UNIQUEMENT le SQL PostgreSQL valide.\n"
    "LIMIT {max_rows} si nécessaire.\n\nSQL :"
)
SQL_CORRECTION_PROMPT = PromptTemplate.from_template(
    "Corrige ce SQL PostgreSQL.\n"
    "Erreur : {error}\n"
    "SQL    : {sql_query}\n"
    "Schema : {schema}\n\nSQL corrigé :"
)

# ── PROMPT v3 : réponse naturelle, une seule phrase, sans répétition ──
ANSWER_SYNTHESIS_PROMPT = PromptTemplate.from_template(
"""Tu es un assistant e-commerce spécialisé dans l'analyse des données Olist.

DONNÉES ISSUES DE LA BASE DE DONNÉES :
{results}

QUESTION :
{question}

CONSIGNES :

- Réponds en français.
- Utilise uniquement les données fournies.
- Mentionne les chiffres importants.
- Donne une analyse métier courte et utile.
- Maximum 2 phrases.

INTERDIT :
- écrire "Voici le graphique"
- écrire "Le graphique montre"
- écrire "[Graphique ...]"
- décrire un graphique
- inventer des données absentes
- répéter plusieurs fois la même information
- expliquer GMV ou Revenue sauf si la question le demande
- mentionner "base de données"
- mentionner "SQL"
- mentionner "requête"
- mentionner "aucune donnée retournée"
- afficher un product_id, seller_id, customer_id, order_id ou tout identifiant
  technique brut (chaîne alphanumérique longue type hash/UUID)
- si la donnée n'a que des IDs sans nom lisible, parle de "catégorie de produit"
  ou "ce produit" sans citer l'identifiant

SI AUCUN RESULTAT :
→ dire uniquement : "Je n'ai pas cette information pour le moment."
IMPORTANT :
Le graphique est généré automatiquement par l'application.
Tu dois uniquement analyser les résultats.

EXEMPLE :
"En 2017, le chiffre d'affaires total des commandes livrées atteint 6 791 996,62 $, ce qui représente une forte activité commerciale sur cette période."

RÉPONSE :
"""
)
# ── Génération de questions de suivi ──
SUGGESTIONS_PROMPT = PromptTemplate.from_template(
"""Tu es un assistant e-commerce Olist.

L'utilisateur vient de poser cette question :
"{question}"

Et a obtenu cette réponse :
"{answer}"

Propose 3 questions de suivi courtes et pertinentes, en français, que l'utilisateur
pourrait poser ensuite pour approfondir son analyse des données Olist (ventes,
clients, vendeurs, produits, paiements, livraisons, avis).

RÈGLES STRICTES :
- Réponds UNIQUEMENT avec un tableau JSON valide, rien d'autre
- Pas de markdown, pas de ```json, pas de texte avant ou après
- Format EXACT : ["question 1", "question 2", "question 3"]
- Les questions doivent être différentes de la question initiale
- Les questions doivent être concrètes et exploitables en SQL

JSON :"""
)


# ───────────────────────── MEMORY ─────────────────────────
@dataclass
class ConversationMemory:
    max_history: int = 3
    messages: List[Dict] = field(default_factory=list)

    def add(self, q: str, a: str, sql: str):
        self.messages.append({"question": q, "answer": a, "sql": sql})
        self.messages = self.messages[-self.max_history:]

    def clear(self):
        self.messages.clear()

    def get(self):
        return self.messages.copy()


# ───────────────────────── VALIDATOR ─────────────────────────
class SQLValidator:
    FORBIDDEN      = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]
    ALLOWED_STARTS = ["SELECT", "WITH"]

    @classmethod
    def clean(cls, sql: str) -> str:
        sql = re.sub(r"```sql|```", "", sql, flags=re.IGNORECASE)
        sql = sql.replace("`", "")
        match = re.search(r"(WITH|SELECT)\b.*", sql, re.IGNORECASE | re.DOTALL)
        if match:
            sql = match.group(0)
        return sql.split(";")[0].strip()

    @classmethod
    def validate(cls, sql: str) -> Tuple[bool, str]:
        if not sql:
            return False, "SQL vide"
        su = sql.upper()
        if not any(su.startswith(k) for k in cls.ALLOWED_STARTS):
            return False, "SQL invalide"
        for kw in cls.FORBIDDEN:
            if kw in su:
                return False, f"Interdit: {kw}"
        return True, ""

    @classmethod
    def add_limit(cls, sql: str, limit: int) -> str:
        if "LIMIT" not in sql.upper():
            sql += f"\nLIMIT {limit}"
        return sql


# ───────────────────────── CHART BUILDER ─────────────────────────
CHART_PALETTE = ["#111110", "#3d3d3b", "#6b6b68", "#16a34a",
                  "#dc2626", "#2563eb", "#f59e0b", "#9ca3af"]

TIME_KEYWORDS = [
    "évolution", "evolution", "tendance", "par mois", "mensuel", "mensuelle",
    "par an", "annuel", "annuelle", "dans le temps", "au fil du temps",
    "trend", "over time", "monthly", "yearly",
]
SHARE_KEYWORDS = [
    "répartition", "repartition", "part de marché", "parts de marché",
    "pourcentage", "proportion", "distribution", "breakdown",
]
COMPARE_KEYWORDS = [
    "corrélation", "correlation", "comparer", "comparaison", " vs ",
    "relation entre", "par rapport",
]

# ── NOUVEAU v5 : mots-clés explicites de demande de visualisation ──
EXPLICIT_CHART_KEYWORDS = [
    "graphique", "graphe", "visualise", "visualiser", "visualisation",
    "courbe", "camembert", "diagramme", "histogramme",
    "bar chart", "pie chart", "scatter", "nuage de points",
    "chart", "plot", "trace", "dessine",
]


def _wants_chart(question: str) -> bool:
    """
    Détermine si la question justifie l'affichage d'un graphe.
    Combine : mots-clés explicites + cas évidents déjà détectés par
    TIME_KEYWORDS / SHARE_KEYWORDS / COMPARE_KEYWORDS.
    Sans correspondance → pas de graphe, même si les données s'y prêteraient.
    """
    q = question.lower()

    if any(kw in q for kw in EXPLICIT_CHART_KEYWORDS):
        return True
    if any(kw in q for kw in TIME_KEYWORDS):
        return True
    if any(kw in q for kw in SHARE_KEYWORDS):
        return True
    if any(kw in q for kw in COMPARE_KEYWORDS):
        return True

    return False


def _detect_chart_type(question: str, n_rows: int) -> str:
    q = question.lower()

    # PRIORITÉ AU CHOIX UTILISATEUR

    if any(x in q for x in [
        "camembert",
        "pie"
    ]):
        return "pie"

    if any(x in q for x in [
        "scatter",
        "nuage de points"
    ]):
        return "scatter"

    if any(x in q for x in [
        "courbe",
        "ligne",
        "line"
    ]):
        return "line"

    if any(x in q for x in [
        "bar",
        "barres",
        "histogramme"
    ]):
        return "bar"

    # comportement actuel conservé
    if any(k in q for k in TIME_KEYWORDS):
        return "line"

    if any(k in q for k in SHARE_KEYWORDS) and n_rows <= 8:
        return "pie"

    if any(k in q for k in COMPARE_KEYWORDS):
        return "scatter"

    return "bar"


def _jsonify_value(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if pd.isna(v) if not isinstance(v, (list, dict)) else False:
        return None
    return v


def _format_label(v) -> str:
    """
    Convertit une valeur de clé catégorielle en libellé propre.
    Évite les "1.0", "2.0"... pour des entiers stockés en float
    (ex: EXTRACT(MONTH FROM ...) qui renvoie un float en PostgreSQL).
    """
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def build_chart(question: str, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Construit un objet "chart" compatible avec ChartBlock.jsx.
    Le graphe n'est généré QUE si _wants_chart(question) renvoie True —
    sinon, même avec des données numériques parfaitement exploitables,
    aucun graphe n'est produit.
    """

    if df is None or df.empty:
        return None

    # 1. Pas de graphe inutile
    if len(df) <= 1 and len(df.columns) <= 1:
        return None

    # 2. Porte d'entrée STRICTE : graphe seulement si la question le demande
    if not _wants_chart(question):
        return None

    # 3. Détection colonnes numériques / catégorielles
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    other_cols   = [c for c in df.columns if c not in numeric_cols]

    if not numeric_cols:
        return None

    # 4. Détection type graphe
    chart_type = _detect_chart_type(question, len(df))

    # 5. Choix axes par défaut
    x_key = other_cols[0] if other_cols else df.columns[0]

    y_keys = [c for c in numeric_cols if c != x_key][:3]
    if not y_keys:
        y_keys = numeric_cols[:1]

    # 6. SCATTER
    if chart_type == "scatter":
        if len(numeric_cols) < 2:
            chart_type = "bar"
        else:
            x_key = numeric_cols[0]
            y_keys = [numeric_cols[1]]

    # 7. PIE (CAMEMBERT)
    if chart_type == "pie":

        if len(numeric_cols) >= 1:

            # Choix de la clé catégorielle : colonne non-numérique si elle
            # existe, sinon la première colonne numérique (ex: numéro de
            # mois) qui devra être traitée comme catégorie de toute façon.
            pie_x_key = other_cols[0] if other_cols else df.columns[0]

            # La clé de valeur doit être une colonne numérique
            # DIFFÉRENTE de la clé catégorielle, sinon (cas fréquent : mois
            # + total numériques tous les deux, x_key = la 1ère colonne
            # numérique) x_key et y_key pointent sur la même colonne, ce qui
            # produit un DataFrame à colonnes dupliquées et casse l'agrégat.
            pie_y_candidates = [c for c in numeric_cols if c != pie_x_key]
            pie_y_key = pie_y_candidates[0] if pie_y_candidates else None

            if pie_y_key is None:
                # aucune colonne numérique distincte de x_key disponible
                chart_type = "bar"
            else:
                # Éliminer les NaN de la clé catégorielle AVANT de
                # tester le nombre de catégories, sinon une seule ligne
                # polluée par un NaN fait basculer à tort en "bar" alors
                # que les vraies catégories tiennent largement dans un
                # camembert. Et surtout, une catégorie nulle produirait
                # "x_key": NaN dans le JSON final, ce qui casse JSON.parse
                # côté frontend.
                pie_df = df.dropna(subset=[pie_x_key])

                if pie_df.empty:
                    chart_type = "bar"
                else:
                    # Normaliser la clé catégorielle en libellé
                    # propre ("1.0" -> "1") AVANT le groupby, pour éviter
                    # le tri alphabétique foireux
                    # ("1.0, 10.0, 11.0, 12.0, 2.0...") observé en prod et
                    # le rendu vide côté ChartBlock.jsx qui attend des
                    # libellés textuels cohérents.
                    original_was_numeric = pd.api.types.is_numeric_dtype(pie_df[pie_x_key])
                    pie_df[pie_x_key] = pie_df[pie_x_key].apply(_format_label)

                    pie_df = pie_df.groupby(pie_x_key, as_index=False)[pie_y_key].sum()

                    # trop de catégories (après nettoyage) → fallback bar
                    if len(pie_df) > 12:
                        chart_type = "bar"
                    else:
                        # Si la clé d'origine était numérique (mois,
                        # année...), on retrie dans l'ordre numérique
                        # plutôt qu'alphabétique
                        if original_was_numeric:
                            try:
                                pie_df = pie_df.sort_values(
                                    by=pie_x_key,
                                    key=lambda col: col.astype(int)
                                ).reset_index(drop=True)
                            except (ValueError, TypeError):
                                pass

                        df = pie_df
                        x_key = pie_x_key
                        y_keys = [pie_y_key]

        else:
            chart_type = "bar"

    # 8. LINE
    if chart_type == "line" and len(df) < 2:
        chart_type = "bar"

    # 9. Construction dataset propre
    chart_df = df.head(30)[[x_key] + y_keys].copy()

    data = []
    for row in chart_df.to_dict("records"):
        clean_row = {}

        for k, v in row.items():
            is_missing = (
                v is None
                or (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))
                or pd.isna(v)
            )

            if is_missing:
                clean_row[k] = 0 if k in y_keys else "N/A"
            elif k == x_key and isinstance(v, float):
                # Sécurité supplémentaire : si x_key contient encore un
                # float à ce stade (chemins bar/line/scatter), on évite le
                # suffixe ".0" inutile dans le libellé affiché.
                clean_row[k] = _format_label(v)
            else:
                clean_row[k] = v

        data.append(clean_row)

    # 10. Titre propre
    title = question.strip().capitalize()
    if len(title) > 70:
        title = title[:67] + "…"

    # 11. RETURN FINAL
    return {
        "type": chart_type,
        "title": title,
        "data": data,
        "x_key": x_key,
        "y_keys": y_keys,
        "colors": CHART_PALETTE,
    }


# ───────────────────────── AGENT ─────────────────────────
class NLPtoSQLAgent:

    def __init__(self, config: AgentConfig):
        self.config = config
        self.memory = ConversationMemory()
        self.engine = create_engine(config.db_url)

        api_key = config.groq_api_key or os.getenv("GROQ_API_KEY", "")
        self._api_key = api_key
        self._models = [
            config.model,
            "llama-3.1-8b-instant",
            "gemma2-9b-it",
        ]
        self._model_idx = 0
        self.llm = self._make_llm(self._models[0])
        self.schema = OLIST_SCHEMA_MINIMAL

    def _make_llm(self, model: str):
        return ChatGroq(
            model=model,
            groq_api_key=self._api_key,
            temperature=self.config.temperature
        )

    def _rotate_llm(self):
        self._model_idx += 1
        new_model = self._models[self._model_idx % len(self._models)]
        print(f"[SQLAgent] Rotation modèle → {new_model}")
        self.llm = self._make_llm(new_model)
        return new_model

    def _invoke_with_fallback(self, chain_template, **kwargs):
        """Invoque une chain LangChain avec rotation automatique si rate limit."""
        for attempt in range(len(self._models)):
            try:
                chain = chain_template | self.llm | StrOutputParser()
                return chain.invoke(kwargs)
            except Exception as e:
                msg = str(e)
                if "429" in msg or "rate_limit_exceeded" in msg or "Rate limit" in msg:
                    if attempt < len(self._models) - 1:
                        self._rotate_llm()
                        continue
                raise
        raise Exception("Tous les modèles Groq ont atteint leur quota.")

    def _format_history(self) -> str:
        hist = self.memory.get()
        if not hist:
            return "(Aucun historique, c'est la première question.)"
        lines = []
        for h in hist:
            lines.append(f"- Question : {h['question']}\n  SQL utilisé : {h['sql']}")
        return "\n".join(lines)

    def to_sql(self, question: str) -> str:
        raw = self._invoke_with_fallback(
            TEXT_TO_SQL_PROMPT,
            schema=self.schema,
            question=question,
            history=self._format_history(),
            max_rows=self.config.max_rows_returned
        )
        sql = SQLValidator.clean(raw)
        return SQLValidator.add_limit(sql, self.config.max_rows_returned)

    def execute(self, sql: str):
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
            return df, None
        except Exception as e:
            return pd.DataFrame(), str(e)

    def correct(self, question: str, sql: str, error: str) -> str:
        raw = self._invoke_with_fallback(
            SQL_CORRECTION_PROMPT,
            question=question,
            sql_query=sql,
            error=error,
            schema=self.schema
        )
        sql = SQLValidator.clean(raw)
        return SQLValidator.add_limit(sql, self.config.max_rows_returned)

    def synthesize(self, question: str, df: pd.DataFrame) -> str:
        """
        Formate le DataFrame en texte lisible avant injection dans le prompt.
        Évite que le LLM ignore les données à cause d'un JSON mal formaté.
        """
        if df.empty:
            results_text = NO_DATA_MESSAGE
        else:
            table_str = df.head(20).to_string(index=False)
            clean_df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

            json_str = clean_df.head(5).to_json(
                orient="records",
                force_ascii=False
            )
            results_text = f"TABLEAU :\n{table_str}\n\nJSON (5 premières lignes) :\n{json_str}"

        return self._invoke_with_fallback(
            ANSWER_SYNTHESIS_PROMPT,
            question=question,
            results=results_text
        )

    def generate_suggestions(self, question: str, answer: str) -> List[str]:
        """
        Génère 2-3 questions de suivi via le LLM.
        En cas d'échec (quota, JSON invalide...), retourne une liste vide
        plutôt que de faire planter la requête principale.
        """
        try:
            raw = self._invoke_with_fallback(
                SUGGESTIONS_PROMPT,
                question=question,
                answer=answer,
            )
            raw = re.sub(r"```json|```", "", raw).strip()

            # Au cas où le LLM ajoute du texte autour du JSON
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                raw = match.group(0)

            suggestions = json.loads(raw)
            if isinstance(suggestions, list):
                return [str(s).strip() for s in suggestions if str(s).strip()][:3]
        except Exception as e:
            logger.warning(f"Génération suggestions échouée: {e}")
        return []

    def query(self, question: str) -> Dict[str, Any]:
        sql = self.to_sql(question)

        if self.config.verbose:
            logger.info(f"SQL: {sql}")

        ok, err = SQLValidator.validate(sql)
        if not ok:
            if self.config.verbose:
                logger.warning(f"SQL invalide rejeté: {err} | sql={sql}")
            return {
                "question": question,
                "sql": sql,
                "answer": NO_DATA_MESSAGE,
                "chart": None,
                "needs_chart": False,
                "suggestions": [],
            }

        df, error = self.execute(sql)
        retries = 0

        while error and retries < self.config.max_retries:
            retries += 1
            if self.config.verbose:
                logger.warning(f"Erreur d'exécution (tentative {retries}): {error}")
            sql = self.correct(question, sql, error)
            if self.config.verbose:
                logger.info(f"SQL corrigé: {sql}")
            df, error = self.execute(sql)

        if error:
            if self.config.verbose:
                logger.error(f"Échec définitif après {retries} tentative(s): {error}")
            return {
                "question": question,
                "sql": sql,
                "answer": NO_DATA_MESSAGE,
                "chart": None,
                "needs_chart": False,
                "suggestions": [],
            }

        answer = self.synthesize(question, df)
        answer = clean_final_answer(answer)

        chart = build_chart(question, df)
        suggestions = self.generate_suggestions(question, answer)

        self.memory.add(question, answer, sql)

        return {
            "question": question,
            "sql": sql,
            "dataframe": df,
            "answer": answer,
            "chart": chart,
            "needs_chart": chart is not None,
            "suggestions": suggestions,
            "error": None,
            "retries": retries
        }

    def reset_memory(self):
        self.memory.clear()

    def history(self):
        return self.memory.get()