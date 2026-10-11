# -*- coding: utf-8 -*-
"""
file_analyzer.py — Analyse de fichiers uploadés avec validation e-commerce.

Retourne un dict :
  {
    "answer": str,
    "source": "file",
    "is_ecommerce": bool,        ← True si le fichier est e-commerce
    "chart": dict | None,
    "table": list | None,
    "suggestions": list[str],
  }

Si le fichier n'est pas e-commerce → "answer" contient le message de refus
et "is_ecommerce" = False.
"""

import os
import json
import re
import math
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np
from groq import Groq

# ─────────────────────────────────────────────────────────────
# MOTS-CLÉS E-COMMERCE
# ─────────────────────────────────────────────────────────────
ECOMMERCE_COLUMN_KEYWORDS = [
    # Commandes / Orders
    "order", "commande", "purchase", "achat", "invoice", "facture",
    # Produits
    "product", "produit", "item", "article", "sku", "référence", "category",
    "catégorie",
    # Ventes / Prix
    "price", "prix", "sale", "vente", "revenue", "revenu", "amount", "montant",
    "total", "subtotal", "discount", "remise", "tax", "tva", "freight",
    "shipping", "livraison",
    # Clients
    "customer", "client", "buyer", "acheteur", "user", "utilisateur",
    # Vendeurs
    "seller", "vendeur", "merchant", "boutique", "store",
    # Paiements
    "payment", "paiement", "transaction", "installment",
    # Statuts
    "status", "statut", "delivered", "livré", "canceled", "annulé",
    "processing", "approved",
    # Avis / Reviews
    "review", "avis", "rating", "note", "score",
    # Stock / Inventory
    "stock", "inventory", "inventaire", "quantity", "quantité", "qty",
    # Logistique
    "delivery", "tracking", "carrier", "transporteur", "warehouse", "entrepôt",
    # Marketplace
    "marketplace", "platform", "olist", "shopify", "amazon", "ebay",
]

ECOMMERCE_CONTENT_KEYWORDS = [
    "order_id", "product_id", "customer_id", "seller_id", "payment_value",
    "freight_value", "review_score", "order_status", "purchase_timestamp",
    "delivered", "canceled", "boleto", "credit_card", "voucher",
]

REFUSAL_MESSAGE = (
    "Je suis spécialisé en e-commerce et analyse de données de vente, "
    "commandes, produits et clients. Ce fichier ne semble pas lié à "
    "l'e-commerce. Envoyez-moi un fichier contenant des données de ventes, "
    "commandes, produits ou clients."
)


def _normalize(text: str) -> str:
    return text.lower().replace("_", " ").replace("-", " ").strip()


def _score_ecommerce(columns: List[str], sample_values: List[str]) -> int:
    """Retourne un score de pertinence e-commerce (0 = hors sujet)."""
    score = 0
    col_text = " ".join(_normalize(c) for c in columns)
    val_text = " ".join(str(v).lower() for v in sample_values[:200])

    for kw in ECOMMERCE_COLUMN_KEYWORDS:
        if kw in col_text:
            score += 2

    for kw in ECOMMERCE_CONTENT_KEYWORDS:
        if kw in col_text or kw in val_text:
            score += 3

    # Bonus : plusieurs colonnes financières ensemble
    financial = sum(1 for kw in ["price", "prix", "amount", "total", "revenue", "payment"]
                    if kw in col_text)
    if financial >= 2:
        score += 4

    return score



# Mots-clés signalant un PDF THÉORIQUE (cours, rapport académique, documentation)
PDF_THEORY_KEYWORDS = [
    "chapitre", "chapter", "introduction", "conclusion", "sommaire",
    "table des matières", "abstract", "résumé", "bibliographie", "références",
    "figure", "tableau", "section", "partie", "cours", "module", "leçon",
    "exercice", "tp ", "td ", "master", "licence", "université", "école",
    "étudiant", "professeur", "auteur", "pages", "isbn", "éditeur",
    "copyright ©", "all rights reserved",
]

# Mots-clés signalant des DONNÉES e-commerce réelles dans un PDF
PDF_DATA_SIGNALS = [
    # Identifiants structurels
    "order_id", "product_id", "customer_id", "seller_id",
    # Valeurs financières avec symboles
    "r$", "brl", "usd", "$", "€", "eur",
    # Statuts de commande réels
    "delivered", "canceled", "processing", "approved", "invoiced",
    # Modes de paiement
    "boleto", "credit_card", "debit_card", "voucher",
    # Structure tabulaire (données CSV-like dans PDF)
    "payment_value", "freight_value", "review_score",
    # Rapports commerciaux
    "chiffre d'affaires", "revenu total", "taux de conversion",
    "panier moyen", "taux de livraison", "rapport de ventes",
    "sales report", "revenue report", "monthly sales",
]


def _is_ecommerce_pdf(text: str, filename: str) -> bool:
    """
    Détection stricte pour PDF : distingue un PDF de DONNÉES e-commerce
    d'un PDF THÉORIQUE (cours, documentation, rapport académique).
    """
    text_lower = text.lower()
    fname_lower = filename.lower()

    # 1. Bonus nom de fichier explicitement e-commerce
    fname_score = sum(2 for kw in [
        "rapport", "report", "sales", "ventes", "commandes", "orders",
        "revenue", "chiffre", "olist", "ecommerce", "e-commerce",
        "invoice", "facture", "dashboard",
    ] if kw in fname_lower)

    # 2. Signal de données réelles
    data_score = sum(3 for kw in PDF_DATA_SIGNALS if kw in text_lower)

    # 3. Pénalité si contenu théorique
    theory_penalty = sum(2 for kw in PDF_THEORY_KEYWORDS if kw in text_lower)

    # 4. Présence de nombres financiers (montants, pourcentages nombreux)
    import re as _re
    # Cherche des patterns type "1 234,56" ou "12345.67" (montants)
    money_patterns = len(_re.findall(r"\b\d{1,3}[.,]\d{2}\b", text))
    if money_patterns > 10:
        data_score += 4

    total = fname_score + data_score - theory_penalty
    return total >= 4


def is_ecommerce_file(
    columns: List[str],
    sample_values: List[str],
    filename: str,
) -> bool:
    """Décide si le fichier est e-commerce (seuil : score >= 4)."""
    score = _score_ecommerce(columns, sample_values)
    # Nom de fichier bonus
    fname = _normalize(filename)
    for kw in ["order", "sale", "vente", "product", "customer", "olist",
               "invoice", "commande", "payment"]:
        if kw in fname:
            score += 2
    return score >= 4


# ─────────────────────────────────────────────────────────────
# ANALYSE PRINCIPALE
# ─────────────────────────────────────────────────────────────
def analyze_uploaded_file(
    file_path: str,
    original_filename: str,
    groq_api_key: str,
) -> Dict[str, Any]:
    """
    Analyse un fichier CSV / Excel / PDF uploadé.
    Retourne un dict compatible avec la réponse /upload-file.
    """
    ext = os.path.splitext(original_filename)[1].lower()

    # ── Lecture du fichier ────────────────────────────────
    df: Optional[pd.DataFrame] = None
    pdf_text: Optional[str] = None

    try:
        if ext == ".csv":
            df = pd.read_csv(file_path, nrows=500)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, nrows=500)
        elif ext == ".pdf":
            pdf_text = _extract_pdf_text(file_path)
        else:
            return {
                "answer": "Format non supporté. Envoyez un CSV, Excel ou PDF.",
                "source": "file",
                "is_ecommerce": False,
                "chart": None,
                "table": None,
                "suggestions": [],
            }
    except Exception as e:
        return {
            "answer": f"Impossible de lire le fichier : {e}",
            "source": "file",
            "is_ecommerce": False,
            "chart": None,
            "table": None,
            "suggestions": [],
        }

    # ── Détection PDF illisible (scanné/image) ────────────
    if pdf_text == PDF_EXTRACTION_FAILED:
        return {
            "answer": (
                "Je n'ai pas pu lire le contenu de ce PDF (probablement un "
                "document scanné ou une image). Essayez un PDF avec du texte "
                "sélectionnable, ou un fichier CSV/Excel."
            ),
            "source": "file",
            "is_ecommerce": False,
            "chart": None,
            "table": None,
            "suggestions": [],
        }

    # ── Validation e-commerce ────────────────────────────
    if df is not None:
        columns = list(df.columns)
        sample_values = df.head(20).astype(str).values.flatten().tolist()
        if not is_ecommerce_file(columns, sample_values, original_filename):
            return {
                "answer": REFUSAL_MESSAGE,
                "source": "file",
                "is_ecommerce": False,
                "chart": None,
                "table": None,
                "suggestions": [],
            }

    elif pdf_text is not None:
        # Pour les PDF : détection stricte basée sur des signaux de DONNÉES
        # (tableaux, chiffres, IDs) et non de contenu théorique/cours
        if not _is_ecommerce_pdf(pdf_text, original_filename):
            return {
                "answer": REFUSAL_MESSAGE,
                "source": "file",
                "is_ecommerce": False,
                "chart": None,
                "table": None,
                "suggestions": [],
            }

    # ── Analyse LLM ──────────────────────────────────────
    try:
        if df is not None:
            return _analyze_dataframe(df, original_filename, groq_api_key)
        elif pdf_text:
            return _analyze_pdf_text(pdf_text, original_filename, groq_api_key)
    except Exception as e:
        err_str = str(e)
        # Message utilisateur propre selon le type d'erreur
        if "429" in err_str or "rate_limit" in err_str.lower() or "Rate limit" in err_str or _RATE_LIMIT_MESSAGE in err_str:
            user_msg = _RATE_LIMIT_MESSAGE
        else:
            user_msg = "Je n'ai pas pu analyser ce fichier pour le moment. Réessayez."
        return {
            "answer": user_msg,
            "source": "file",
            "is_ecommerce": True,
            "chart": None,
            "table": None,
            "suggestions": [],
        }

    return {
        "answer": "Fichier vide ou illisible.",
        "source": "file",
        "is_ecommerce": False,
        "chart": None,
        "table": None,
        "suggestions": [],
    }

# ─────────────────────────────────────────────────────────────
# ANALYSE DATAFRAME (CSV / EXCEL)
# ─────────────────────────────────────────────────────────────
def _analyze_dataframe(
    df: pd.DataFrame,
    filename: str,
    groq_api_key: str,
) -> Dict[str, Any]:
    """Analyse un DataFrame e-commerce et retourne réponse + graphe éventuel."""

    n_rows, n_cols = df.shape
    columns = list(df.columns)

    # Stats descriptives rapides
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    stats_lines = []
    for col in numeric_cols[:6]:
        s = df[col].dropna()
        if len(s):
            stats_lines.append(
                f"  - {col}: min={s.min():.2f}, max={s.max():.2f}, "
                f"mean={s.mean():.2f}, sum={s.sum():.2f}"
            )

    stats_text = "\n".join(stats_lines) if stats_lines else "  (aucune colonne numérique)"

    # Aperçu JSON (10 lignes)
    preview_json = df.head(10).fillna("").to_json(orient="records", force_ascii=False)

    prompt = f"""Tu es un expert e-commerce. Analyse ce fichier de données.

Fichier : {filename}
Lignes : {n_rows} | Colonnes : {n_cols}
Colonnes : {', '.join(columns)}

Statistiques clés :
{stats_text}

Aperçu (10 premières lignes) :
{preview_json}

Fournis :
1. Un résumé clair en 3-4 phrases (chiffres clés, tendances, insights e-commerce)
2. 3 questions analytiques pertinentes que l'utilisateur pourrait poser

RÉPONDS UNIQUEMENT en JSON valide, sans markdown, sans texte avant/après :
{{
  "answer": "...",
  "suggestions": ["...", "...", "..."]
}}"""

    result = _call_groq(prompt, groq_api_key)

    answer = result.get("answer", "Analyse terminée.")
    suggestions = result.get("suggestions", [])

    # Graphe automatique si données numériques disponibles
    chart = _auto_chart(df, filename)

    # Table (50 premières lignes)
    table = (
        df.head(50)
        .replace({np.nan: None, np.inf: None, -np.inf: None})
        .to_dict("records")
    )

    return {
        "answer": answer,
        "source": "file",
        "is_ecommerce": True,
        "chart": chart,
        "table": table,
        "suggestions": suggestions,
    }


# ─────────────────────────────────────────────────────────────
# ANALYSE PDF
# ─────────────────────────────────────────────────────────────
PDF_EXTRACTION_FAILED = "__PDF_EXTRACTION_FAILED__"


def _extract_pdf_text(path: str) -> str:
    """
    Retourne le texte extrait, ou le sentinel PDF_EXTRACTION_FAILED si
    le PDF n'a produit aucun texte exploitable (scanné/image, corrompu...).
    Ne JAMAIS retourner "" silencieusement : ça ferait passer un PDF
    illisible pour un PDF "non e-commerce" alors qu'on ne sait juste pas.
    """
    text = ""
    try:
        import pdfplumber  # type: ignore[import]
        with pdfplumber.open(path) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages[:10]]
        text = "\n".join(pages)[:8000]
    except ImportError:
        pass
    except Exception:
        text = ""

    if not text.strip():
        try:
            import PyPDF2
            with open(path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                texts = [reader.pages[i].extract_text() or ""
                         for i in range(min(10, len(reader.pages)))]
            text = "\n".join(texts)[:8000]
        except Exception:
            text = ""

    if not text.strip():
        return PDF_EXTRACTION_FAILED

    return text


def _analyze_pdf_text(
    text: str,
    filename: str,
    groq_api_key: str,
) -> Dict[str, Any]:
    prompt = f"""Tu es un expert e-commerce. Analyse ce document PDF lié au commerce en ligne.

Fichier : {filename}

Contenu (extrait) :
{text[:5000]}

Fournis :
1. Un résumé clair en 3-4 phrases (données clés, insights e-commerce)
2. 3 questions analytiques que l'utilisateur pourrait poser sur ce document

RÉPONDS UNIQUEMENT en JSON valide, sans markdown :
{{
  "answer": "...",
  "suggestions": ["...", "...", "..."]
}}"""

    result = _call_groq(prompt, groq_api_key)
    return {
        "answer": result.get("answer", "Document analysé."),
        "source": "file",
        "is_ecommerce": True,
        "chart": None,
        "table": None,
        "suggestions": result.get("suggestions", []),
    }


# ─────────────────────────────────────────────────────────────
# GRAPHE AUTO
# ─────────────────────────────────────────────────────────────
CHART_PALETTE = ["#111110", "#3d3d3b", "#16a34a", "#2563eb",
                 "#f59e0b", "#dc2626", "#9ca3af", "#6b6b68"]


def _auto_chart(df: pd.DataFrame, filename: str) -> Optional[Dict[str, Any]]:
    """Construit un graphe automatique à partir du DataFrame."""
    if df is None or df.empty:
        return None

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    other_cols = [c for c in df.columns if c not in numeric_cols]

    if not numeric_cols:
        return None

    # Cherche une colonne temporelle ou catégorielle pertinente
    x_key = None
    for col in other_cols:
        col_lower = col.lower()
        if any(k in col_lower for k in ["date", "month", "mois", "year", "an",
                                          "period", "week", "semaine"]):
            x_key = col
            break
    if x_key is None and other_cols:
        x_key = other_cols[0]
    if x_key is None:
        x_key = df.columns[0]

    y_key = numeric_cols[0]
    if y_key == x_key and len(numeric_cols) > 1:
        y_key = numeric_cols[1]

    # Agrégation si trop de lignes
    chart_df = df[[x_key, y_key]].dropna()
    if len(chart_df) > 30:
        chart_df = (
            chart_df.groupby(x_key, as_index=False)[y_key]
            .sum()
            .head(20)
        )

    data = []
    for row in chart_df.to_dict("records"):
        clean = {}
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                clean[k] = 0 if k == y_key else "N/A"
            elif isinstance(v, float) and v == int(v):
                clean[k] = str(int(v)) if k == x_key else v
            else:
                clean[k] = v
        data.append(clean)

    if not data:
        return None

    chart_type = "bar"
    col_lower = x_key.lower()
    if any(k in col_lower for k in ["date", "month", "mois", "year", "an",
                                      "period", "week", "semaine"]):
        chart_type = "line"

    return {
        "type": chart_type,
        "title": f"Analyse — {filename}",
        "data": data,
        "x_key": x_key,
        "y_keys": [y_key],
        "colors": CHART_PALETTE,
    }


# ─────────────────────────────────────────────────────────────
# GROQ HELPER — avec rotation de modèles si rate limit (429)
# ─────────────────────────────────────────────────────────────

# Modèles de secours dans l'ordre de préférence
_FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

_RATE_LIMIT_MESSAGE = (
    "Le quota de l'API est temporairement épuisé. "
    "Réessayez dans quelques minutes."
)


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc)
    return "429" in msg or "rate_limit_exceeded" in msg or "Rate limit" in msg


def _call_groq(prompt: str, api_key: str) -> Dict[str, Any]:
    """
    Appelle Groq avec rotation automatique de modèles en cas de rate limit.
    Ne laisse jamais remonter le message d'erreur brut de l'API à l'utilisateur.
    """
    client = Groq(api_key=api_key)
    last_exc: Optional[Exception] = None

    for model in _FALLBACK_MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=800,
            )
            raw = resp.choices[0].message.content.strip()

            # Nettoyer les balises markdown éventuelles
            raw = re.sub(r"```json|```", "", raw).strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                raw = match.group(0)

            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"answer": raw, "suggestions": []}

        except Exception as e:
            last_exc = e
            if _is_rate_limit(e):
                # Tenter le modèle suivant
                continue
            # Erreur non liée au rate limit → on remonte proprement
            raise

    # Tous les modèles ont échoué (rate limit généralisé)
    raise Exception(_RATE_LIMIT_MESSAGE)