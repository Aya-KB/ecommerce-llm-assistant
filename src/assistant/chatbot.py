# -*- coding: utf-8 -*-
"""
DataOlist AI — Interface premium style Claude
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys, os, re, io, hashlib, json, sqlite3, random
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'etl'))
from core.sql_agent import NLPtoSQLAgent, AgentConfig  # type: ignore
from core.schema_manager import SAMPLE_QUESTIONS  # type: ignore

# ─────────────────────────────────────────────
#  Config centralisee (lue depuis .env — JAMAIS de cle en dur)
# ─────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
DATABASE_URL = os.getenv("DATABASE_URL") or (
    f"postgresql://{os.getenv('DB_USER','postgres')}:{os.getenv('DB_PASSWORD','')}"
    f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}"
    f"/{os.getenv('DB_NAME','olist_db')}?client_encoding=utf8"
)

def get_groq_llm(temperature: float = 0.0):
    """Cree un client Groq a partir de la config .env. Leve une erreur claire si la cle manque."""
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY manquante. Ajoutez-la dans votre fichier .env "
            "(voir .env.example) — obtenez une cle sur https://console.groq.com/keys"
        )
    from langchain_groq import ChatGroq
    return ChatGroq(model=GROQ_MODEL, groq_api_key=GROQ_API_KEY, temperature=temperature)


st.set_page_config(
    page_title="DataOlist AI",
    page_icon="🛍",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&display=swap');

:root {
    --bg: #ffffff;
    --bg-sidebar: #f9f8f6;
    --bg-hover: rgba(0,0,0,0.055);
    --bg-active: rgba(0,0,0,0.09);
    --border: #e8e5e0;
    --border-light: #f0ede8;
    --text-primary: #111110;
    --text-secondary: #6f6e69;
    --text-muted: #a8a39a;
    --accent: #111110;
    --radius: 8px;
    --radius-lg: 14px;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04);
}

* {
    font-family: 'Geist', -apple-system, BlinkMacSystemFont, sans-serif;
    box-sizing: border-box;
    -webkit-font-smoothing: antialiased;
}

.stApp { background: var(--bg); color: var(--text-primary); }

.main .block-container {
    max-width: 740px;
    margin: 0 auto;
    padding: 0 1.5rem 6rem;
}

/* Header */
header[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
}
#MainMenu, footer { visibility: hidden; }

/* ═══════════════ SIDEBAR ═══════════════ */
[data-testid="stSidebar"] {
    background: var(--bg-sidebar) !important;
    border-right: 1px solid var(--border) !important;
    width: 252px !important;
    min-width: 252px !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding: 0 !important;
    height: 100vh;
    display: flex;
    flex-direction: column;
}
[data-testid="stSidebar"] * { color: var(--text-primary) !important; }

/* Tous les boutons sidebar */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: none !important;
    color: var(--text-primary) !important;
    font-size: 0.835rem !important;
    font-weight: 400 !important;
    text-align: left !important;
    padding: 0.32rem 0.7rem !important;
    border-radius: 6px !important;
    box-shadow: none !important;
    width: 100% !important;
    line-height: 1.5 !important;
    transition: background 0.12s ease !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    margin: 0 !important;
    min-height: 0 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: var(--bg-hover) !important;
    transform: none !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] .stButton > button:focus {
    box-shadow: none !important;
    outline: none !important;
}
[data-testid="stSidebar"] .stButton { margin: 0 !important; }
[data-testid="stSidebar"] .element-container { margin: 0 !important; }
[data-testid="stSidebar"] div[data-testid="column"] { padding: 0 !important; }
[data-testid="stSidebar"] hr {
    margin: 0.35rem 0 !important;
    border-color: var(--border) !important;
    opacity: 1 !important;
}

/* ═══════════════ BOUTONS GLOBAUX ═══════════════ */
.stButton > button {
    background: var(--accent) !important;
    color: #fff !important;
    border: none !important;
    border-radius: var(--radius) !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    padding: 0.55rem 1.1rem !important;
    transition: all 0.15s ease !important;
    box-shadow: var(--shadow-sm) !important;
    letter-spacing: -0.01em !important;
}
.stButton > button:hover {
    background: #2a2a28 !important;
    transform: none !important;
    box-shadow: var(--shadow-md) !important;
}

/* ═══════════════ CHAT ═══════════════ */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 1.1rem 0 !important;
    margin: 0 !important;
    border-bottom: 1px solid var(--border-light) !important;
}
[data-testid="stChatMessage"]:last-child {
    border-bottom: none !important;
}
[data-testid="stChatMessageContent"] {
    font-size: 0.92rem !important;
    line-height: 1.7 !important;
    color: var(--text-primary) !important;
}

/* Chat input */
[data-testid="stChatInput"] {
    background: #faf9f7 !important;
    border: 1.5px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: var(--shadow-sm) !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #888580 !important;
    box-shadow: 0 0 0 3px rgba(0,0,0,0.06), var(--shadow-sm) !important;
}
[data-testid="stChatInput"] textarea {
    font-size: 0.9rem !important;
    color: var(--text-primary) !important;
}

/* ═══════════════ INPUTS ═══════════════ */
.stTextInput > div > div > input {
    background: #faf9f7 !important;
    border: 1.5px solid var(--border) !important;
    border-radius: var(--radius) !important;
    color: var(--text-primary) !important;
    font-size: 0.875rem !important;
    padding: 0.45rem 0.75rem !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
.stTextInput > div > div > input:focus {
    border-color: #888580 !important;
    box-shadow: 0 0 0 3px rgba(0,0,0,0.06) !important;
    outline: none !important;
}
.stTextInput > label {
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    color: var(--text-secondary) !important;
}

/* ═══════════════ TABS ═══════════════ */
.stTabs [data-baseweb="tab-list"] {
    background: #f0ede8 !important;
    border-radius: var(--radius) !important;
    padding: 3px !important;
    border: none !important;
    gap: 2px !important;
}
.stTabs [data-baseweb="tab"] {
    color: var(--text-secondary) !important;
    border-radius: 6px !important;
    font-size: 0.845rem !important;
    font-weight: 500 !important;
    padding: 0.35rem 0.9rem !important;
}
.stTabs [aria-selected="true"] {
    background: #ffffff !important;
    color: var(--text-primary) !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ═══════════════ EXPANDER ═══════════════ */
.stExpander {
    background: #faf9f7 !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    box-shadow: none !important;
}
.stExpander summary {
    font-size: 0.845rem !important;
    color: var(--text-secondary) !important;
    font-weight: 500 !important;
}

/* ═══════════════ DATAFRAME ═══════════════ */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    overflow: hidden !important;
}

/* ═══════════════ TOGGLE ═══════════════ */
.stToggle { accent-color: var(--accent); }
.stToggle > label {
    font-size: 0.82rem !important;
    color: var(--text-secondary) !important;
}

/* ═══════════════ SCROLLBAR ═══════════════ */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #d4cfc8; border-radius: 99px; }
::-webkit-scrollbar-thumb:hover { background: #b8b3ac; }

/* ═══════════════ SELECTBOX ═══════════════ */
.stSelectbox > div > div {
    background: #faf9f7 !important;
    border: 1.5px solid var(--border) !important;
    border-radius: var(--radius) !important;
    font-size: 0.875rem !important;
}

/* ═══════════════ SIDEBAR COMPONENTS ═══════════════ */
.sb-logo {
    padding: 1rem 0.85rem 0.6rem;
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.02em;
    display: flex;
    align-items: center;
    gap: 0.45rem;
}
.sb-logo .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #2a9d5c;
    flex-shrink: 0;
}
.sb-section {
    font-size: 0.65rem;
    color: var(--text-muted) !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    padding: 0.55rem 0.85rem 0.18rem;
    display: block;
}
.sb-new-chat button {
    font-weight: 600 !important;
    font-size: 0.835rem !important;
    color: var(--text-primary) !important;
    padding: 0.4rem 0.7rem !important;
}
.sb-nav button {
    font-size: 0.825rem !important;
    color: var(--text-secondary) !important;
    padding: 0.28rem 0.85rem !important;
}
.sb-nav button:hover { color: var(--text-primary) !important; }
.sb-session button {
    font-size: 0.81rem !important;
    color: var(--text-primary) !important;
    padding: 0.25rem 0.5rem !important;
}
.sb-dots button {
    padding: 0.18rem 0.3rem !important;
    font-size: 1rem !important;
    color: var(--text-muted) !important;
    line-height: 1 !important;
    min-width: 22px !important;
    width: 22px !important;
}
.sb-dots button:hover { color: var(--text-primary) !important; background: var(--bg-active) !important; }
.sb-menu-btn button {
    font-size: 0.775rem !important;
    padding: 0.2rem 0.5rem !important;
    background: var(--bg-hover) !important;
    border-radius: 5px !important;
}
.sb-menu-btn button:hover { background: var(--bg-active) !important; }
.sb-profile {
    padding: 0.6rem 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    border-top: 1px solid var(--border);
}
.sb-avatar {
    width: 27px; height: 27px;
    border-radius: 50%;
    background: var(--accent);
    color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.72rem; font-weight: 700;
    flex-shrink: 0;
    letter-spacing: 0;
}
.sb-user-name { font-size: 0.8rem; font-weight: 600; }
.sb-user-plan { font-size: 0.67rem; color: var(--text-muted); }
.sb-logout button {
    font-size: 0.78rem !important;
    color: var(--text-secondary) !important;
    padding: 0.28rem 0.7rem !important;
    border: 1px solid var(--border) !important;
    background: transparent !important;
    box-shadow: none !important;
}
.sb-logout button:hover { background: var(--bg-hover) !important; }

/* ═══════════════ MAIN AREA ═══════════════ */
.chat-welcome {
    text-align: center;
    padding: 5rem 0 2.5rem;
}
.chat-welcome h1 {
    font-size: 1.75rem;
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: -0.03em;
    margin-bottom: 0.4rem;
    line-height: 1.2;
}
.chat-welcome p {
    font-size: 0.92rem;
    color: var(--text-secondary);
    margin: 0;
}

.disclaimer {
    text-align: center;
    font-size: 0.71rem;
    color: var(--text-muted);
    padding: 0.75rem 0 0.25rem;
    letter-spacing: -0.005em;
}

.upload-panel {
    background: #faf9f7;
    border: 1.5px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 0.9rem 1rem;
    margin: 0.4rem 0;
}
.upload-panel-title {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

/* Plus button */
.plus-btn button {
    background: #f0ede8 !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border) !important;
    border-radius: 50% !important;
    width: 32px !important;
    height: 32px !important;
    padding: 0 !important;
    font-size: 1.1rem !important;
    line-height: 1 !important;
    box-shadow: none !important;
    min-height: 0 !important;
    margin-top: 0.3rem !important;
}
.plus-btn button:hover {
    background: var(--bg-active) !important;
    color: var(--text-primary) !important;
    box-shadow: none !important;
}

/* Export buttons */
.export-btn button {
    background: #f0ede8 !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    font-size: 0.78rem !important;
    padding: 0.3rem 0.7rem !important;
    box-shadow: none !important;
}
.export-btn button:hover { background: var(--bg-active) !important; box-shadow: none !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  Multilingue
# ─────────────────────────────────────────────

CORRECTIONS = {
    "cmd":"commandes","comb":"combien","cmb":"combien",
    "nb":"nombre","comm":"commandes","livr":"livraisons",
    "paiem":"paiements","chif":"chiffre d affaires",
    "vendeur":"vendeurs","client":"clients","produit":"produits",
    "shhal":"combien","chhal":"combien","fin":"quels",
    "wach":"est-ce que","bzzaf":"beaucoup","ktar":"plus",
}
SALUTATIONS_SET = {
    "bonjour","salut","hello","hi","hey","bonsoir","ca va","merci",
    "thanks","thank you","ok","salam","labas","la bas","ahlan",
    "wakha","chokran","مرحبا","السلام عليكم","شكرا","صباح الخير",
}
FORMAT_KEYWORDS = {
    "court":"court","courte":"court","bref":"court","breve":"court",
    "resume":"resume","résumé":"resume","resumé":"resume","résume":"resume",
    "synthese":"resume","synthèse":"resume",
    "explique":"explique","expliquer":"explique","explication":"explique",
    "qu'est-ce que tu vois":"explique","quest-ce que tu vois":"explique",
    "que vois-tu":"explique","detaille":"explique","détaille":"explique",
    "pdf":"export_pdf","excel":"export_excel","csv":"export_csv",
    "telecharge":"export_csv","exporte":"export_csv",
    "genere":"export","génère":"export","fichier":"export","rapport":"export_pdf",
}
SQL_KEYWORDS = [
    "combien","quel","quels","quelle","quelles","montre","affiche",
    "liste","top","meilleur","total","moyenne","somme","nombre",
    "vente","commande","client","vendeur","produit","livraison",
    "paiement","note","avis","revenu","chiffre","evolution",
    "distribution","repartition","delai","retard","etat","ville",
    "how many","what","show","list","best","top","total",
    "average","count","which","orders","sales","revenue",
    "customers","sellers","products","delivery","payment",
    "shhal","chhal","fin","ktar","bzzaf",
    "كم","ما","اظهر","قائمة","أفضل","إجمالي","متوسط",
    "cmd","comb","cmb","genere","génère","pdf","excel","csv","rapport",
]

def detect_language(t):
    if len(re.findall(r'[\u0600-\u06FF]',t))>2: return "arabic"
    if any(w in t.lower() for w in ["labas","wach","bghit","chokran","wakha","salam","shhal","chhal","ktar","bzzaf","dyal"]): return "darija"
    if any(w in t.lower() for w in ["how","what","show","list","best","top","total","average","count","which","orders","sales"]): return "english"
    return "french"

def detect_format(q):
    ql=q.lower()
    for kw,fmt in FORMAT_KEYWORDS.items():
        if kw in ql: return fmt
    return "normal"

def correct_typos(q):
    return " ".join([CORRECTIONS.get(w,w) for w in q.lower().split()])

def is_data_q(q):
    return any(kw in q.lower() for kw in SQL_KEYWORDS)

def get_session_name(msg):
    q=msg.strip()
    return q[:38]+"..." if len(q)>38 else q

def get_conv_response(question,lang):
    q=question.lower().strip()
    if any(s in q for s in ["ca va","cava","comment tu vas","how are you","labas 3lik","kif dayr","kif nta"]):
        return {"french":"Je vais tres bien ! Et vous ?","english":"I'm doing great! And you?",
                "arabic":"انا بخير!","darija":"Labas, hamdullah!"}.get(lang,"Je vais bien !")
    if any(s in q for s in ["bonjour","salut","hello","hi","hey","salam","labas","مرحبا","ahlan"]):
        opts={"french":["Bonjour ! Comment puis-je vous aider ?","Salut ! Pret a explorer les donnees Olist ?"],
              "english":["Hello! How can I help?","Hi there! Ready to explore Olist data?"],
              "arabic":["مرحبا! كيف يمكنني مساعدتك؟"],
              "darija":["Salam! Kifach ymkn liya n3awnak?","Labas! Wach bghiti tchalel data d'Olist?"]}
        return random.choice(opts.get(lang,opts["french"]))
    if any(s in q for s in ["qui es tu","who are you","ecommerce","olist","c quoi","cest quoi","what is"]):
        return {"french":"Je suis **DataOlist AI** — connecte a la base **Olist** avec 97 000+ commandes, 100 000 clients et 3 000 vendeurs au Bresil. Posez-moi une question sur vos donnees.",
                "english":"I'm **DataOlist AI** — connected to **Olist** with 97,000+ orders in Brazil.",
                "arabic":"انا **DataOlist AI** — متصل بقاعدة Olist البرازيلية.",
                "darija":"Ana **DataOlist AI** — mwsl b Olist: 97,000+ commandes f Bresil."}.get(lang,"Je suis DataOlist AI.")
    if any(s in q for s in ["merci","thanks","thank","شكرا","chokran","bravo","super"]):
        return {"french":"Avec plaisir !","english":"You're welcome!","arabic":"على الرحب!","darija":"Bla jmil!"}.get(lang,"Avec plaisir !")
    return {"french":"Je suis specialise dans l'analyse des donnees **Olist**. Posez-moi une question sur les ventes, clients, vendeurs ou livraisons.",
            "english":"I specialize in **Olist** data. Ask me about sales, customers or deliveries.",
            "arabic":"انا متخصص في تحليل بيانات Olist.",
            "darija":"Ana mkhss f analyse d'data Olist. Suwel iya 3la ventes wla livraisons."}.get(lang,"Posez-moi une question sur Olist.")


# ─────────────────────────────────────────────
#  Export
# ─────────────────────────────────────────────

def export_excel(df):
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as w:
        df.to_excel(w,index=False,sheet_name='Resultats')
        ws=w.sheets['Resultats']
        for col in ws.columns:
            ml=max(len(str(c.value) or "") for c in col)
            ws.column_dimensions[col[0].column_letter].width=min(ml+4,40)
    return out.getvalue()

def export_pdf_report(df,title="Rapport DataOlist AI"):
    try:
        from fpdf import FPDF
        pdf=FPDF(); pdf.add_page()
        pdf.set_font("Helvetica","B",15)
        pdf.cell(0,11,title,ln=True,align="C")
        pdf.set_font("Helvetica","",9)
        pdf.cell(0,7,f"Genere le {datetime.now().strftime('%d/%m/%Y %H:%M')}",ln=True,align="C")
        pdf.ln(4)
        cols=df.columns.tolist()
        cw=min(180//max(len(cols),1),48)
        pdf.set_fill_color(17,17,16); pdf.set_text_color(255,255,255)
        pdf.set_font("Helvetica","B",7)
        for c in cols: pdf.cell(cw,7,str(c)[:16],border=1,fill=True,align="C")
        pdf.ln()
        pdf.set_text_color(0,0,0); pdf.set_font("Helvetica","",7)
        for i,row in df.head(50).iterrows():
            pdf.set_fill_color(250,249,247) if i%2==0 else pdf.set_fill_color(255,255,255)
            for c in cols: pdf.cell(cw,6,str(row[c])[:16],border=1,fill=True)
            pdf.ln()
        pdf.ln(4); pdf.set_font("Helvetica","I",7)
        pdf.cell(0,5,"DataOlist AI est une IA et peut faire des erreurs.",align="C")
        return bytes(pdf.output())
    except: return b""

def analyze_file(uf, question):
    """
    Analyse un fichier (image ou PDF) et retourne (reponse, contenu_extrait).
    contenu_extrait est stocke en memoire de session pour que le chat normal
    puisse ensuite repondre a 'resume-le', 'explique-le', etc. sur CE fichier.
    """
    try:
        if uf.type.startswith("image/"):
            anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not anthropic_key:
                return (
                    "Je n'ai pas pu analyser cette image : la cle ANTHROPIC_API_KEY "
                    "n'est pas configuree dans le fichier .env.", None
                )
            import base64, requests
            b64 = base64.b64encode(uf.getvalue()).decode()
            try:
                r = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={"model": "claude-sonnet-4-6", "max_tokens": 1000,
                          "messages": [{"role": "user", "content": [
                              {"type": "image", "source": {"type": "base64", "media_type": uf.type, "data": b64}},
                              {"type": "text", "text": question or "Decris cette image en francais, avec les details visibles (chiffres, axes, legendes si c'est un graphe)."}
                          ]}]},
                    timeout=30,
                )
                r.raise_for_status()
                content = r.json().get("content", [{}])
                text_out = content[0].get("text", "") if content else ""
                if not text_out:
                    return "Je n'ai pas pu extraire de description pour cette image.", None
                return text_out, text_out
            except requests.RequestException as e:
                return f"Je n'ai pas pu analyser cette image pour l'instant (erreur reseau/API : {e}).", None

        elif uf.type == "application/pdf":
            try:
                import PyPDF2
            except ImportError:
                return "Le module PyPDF2 n'est pas installe (pip install PyPDF2).", None
            reader = PyPDF2.PdfReader(uf)
            text = "\n".join(p.extract_text() or "" for p in reader.pages[:20])
            if not text.strip():
                return "Ce PDF ne contient pas de texte extractible (probablement scanne en image).", None
            try:
                llm = get_groq_llm(temperature=0.0)
            except RuntimeError as e:
                # Pas de cle LLM : on retourne quand meme le texte brut extrait, c'est mieux que rien
                return (
                    f"Je n'ai pas pu generer de resume ({e}). "
                    f"Voici les premiers caracteres extraits du document :\n\n{text[:800]}...",
                    text,
                )
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import PromptTemplate
            pt = f"{question or 'Resume ce document en francais.'}\n\nDocument:\n{text[:6000]}"
            try:
                answer = (PromptTemplate.from_template("{p}") | llm | StrOutputParser()).invoke({"p": pt})
                return answer, text
            except Exception as e:
                return f"Je n'ai pas pu generer de resume pour ce document (erreur technique : {e}).", text

        return "Format non supporte (PNG, JPG, PDF uniquement).", None
    except Exception as e:
        return f"Une erreur est survenue pendant l'analyse du fichier : {e}", None


# ─────────────────────────────────────────────
#  SQLite
# ─────────────────────────────────────────────

DB_PATH=os.path.join(os.path.dirname(__file__),'..','..','users.db')

def init_db():
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,created_at TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_sessions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,session_name TEXT NOT NULL,
        created_at TEXT NOT NULL,messages TEXT DEFAULT "[]")''')
    try:
        c.execute("INSERT INTO users(username,email,password_hash,created_at) VALUES(?,?,?,?)",
                  ("admin","admin@olist.com",hp("admin123"),datetime.now().isoformat()))
    except: pass
    conn.commit(); conn.close()

def hp(p: str) -> str:
    """Hash securise avec sel (bcrypt). Remplace l'ancien SHA-256 sans sel."""
    import bcrypt # type: ignore
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _verify_password(p: str, stored_hash: str) -> bool:
    """Verifie un mot de passe contre un hash. Supporte les anciens hash SHA-256
    (migration douce : si ca matche l'ancien format, on le requalifie en bcrypt)."""
    import bcrypt # type: ignore
    if stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$"):
        try:
            return bcrypt.checkpw(p.encode("utf-8"), stored_hash.encode("utf-8"))
        except ValueError:
            return False
    # Ancien format SHA-256 (comptes crees avant la migration securite)
    legacy = hashlib.sha256(p.encode()).hexdigest()
    return legacy == stored_hash

def register_user(u,e,p):
    try:
        conn=sqlite3.connect(DB_PATH); c=conn.cursor()
        c.execute("INSERT INTO users(username,email,password_hash,created_at) VALUES(?,?,?,?)",
                  (u.strip(),e.strip().lower(),hp(p),datetime.now().isoformat()))
        conn.commit(); uid=c.lastrowid; conn.close()
        return True,uid,"Compte cree !"
    except sqlite3.IntegrityError: return False,None,"Nom ou email deja utilise."

def login_user(u,p):
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT id,username,email,password_hash FROM users WHERE username=?",(u.strip(),))
    row=c.fetchone()
    if not row:
        conn.close()
        return False,None
    if not _verify_password(p, row[3]):
        conn.close()
        return False,None
    # Migration douce : si l'ancien hash SHA-256 a matche, on le met a niveau vers bcrypt
    if not (row[3].startswith("$2b$") or row[3].startswith("$2a$")):
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (hp(p), row[0]))
        conn.commit()
    conn.close()
    return True,{"id":row[0],"username":row[1],"email":row[2]}

def get_sessions(uid):
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("SELECT id,session_name,created_at,messages FROM chat_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT 20",(uid,))
    rows=c.fetchall(); conn.close()
    result=[]
    for r in rows:
        try: msgs=json.loads(r[3])
        except: msgs=[]
        result.append({"id":r[0],"name":r[1],"date":r[2],"messages":msgs})
    return result

def save_session(uid,messages):
    if not messages: return
    first=next((m["content"] for m in messages if m.get("role")=="user"),"Conversation")
    name=get_session_name(first)
    safe=[{"role":m.get("role",""),"content":m.get("content",""),"sql":m.get("sql","")} for m in messages]
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("INSERT INTO chat_sessions(user_id,session_name,created_at,messages) VALUES(?,?,?,?)",
              (uid,name,datetime.now().isoformat(),json.dumps(safe,ensure_ascii=False)))
    conn.commit(); conn.close()

def rename_session(sid,name):
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("UPDATE chat_sessions SET session_name=? WHERE id=?",(name,sid))
    conn.commit(); conn.close()

def delete_session(sid):
    conn=sqlite3.connect(DB_PATH); c=conn.cursor()
    c.execute("DELETE FROM chat_sessions WHERE id=?",(sid,))
    conn.commit(); conn.close()

def search_sessions(uid,q):
    s=get_sessions(uid)
    return [x for x in s if q.lower() in x["name"].lower()] if q else s


# ─────────────────────────────────────────────
#  Agent
# ─────────────────────────────────────────────

@st.cache_resource
def load_agent():
    if not GROQ_API_KEY:
        st.error(
            "GROQ_API_KEY manquante. Ajoutez-la dans le fichier .env "
            "(copiez .env.example) puis relancez l'application."
        )
        st.stop()
    return NLPtoSQLAgent(AgentConfig(
        db_url=DATABASE_URL,
        groq_api_key=GROQ_API_KEY,
        model=GROQ_MODEL,
        max_rows_returned=int(os.getenv("MAX_ROWS_RETURNED", "100")),
        temperature=0.0, verbose=True,
    ))


# ─────────────────────────────────────────────
#  Session state
# ─────────────────────────────────────────────

def init_session():
    defaults={"authenticated":False,"user":None,"messages":[],
               "query_count":0,"show_chart":True,"current_view":"chat",
               "rename_id":None,"show_upload":False,"open_menu":None,
               "last_file_context":None,"last_data_context":None,
               "context_order":0}
    for k,v in defaults.items():
        if k not in st.session_state: st.session_state[k]=v


# ─────────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────────

def render_auth():
    col1,col2,col3=st.columns([1,1.05,1])
    with col2:
        st.markdown("""
        <div style="text-align:center;padding:3.5rem 0 2rem;">
            <div style="font-size:1.9rem;font-weight:700;color:#111110;margin-bottom:0.3rem;letter-spacing:-0.04em;">
                DataOlist AI
            </div>
            <div style="color:#6f6e69;font-size:0.87rem;font-weight:400;">
                Assistant intelligent d'analyse e-commerce
            </div>
        </div>""",unsafe_allow_html=True)

        t1,t2=st.tabs(["Connexion","Inscription"])
        with t1:
            st.markdown("<br>",unsafe_allow_html=True)
            u=st.text_input("Nom d'utilisateur",key="lu",placeholder="votre_nom")
            p=st.text_input("Mot de passe",type="password",key="lp",placeholder="••••••••")
            if st.button("Se connecter",use_container_width=True,key="btn_login"):
                if not u or not p: st.error("Remplissez tous les champs.")
                else:
                    ok,user=login_user(u,p)
                    if ok:
                        st.session_state.authenticated=True
                        st.session_state.user=user
                        st.session_state.messages=[]
                        st.rerun()
                    else: st.error("Identifiants incorrects.")
            st.markdown('<p style="text-align:center;font-size:0.77rem;color:#a8a39a;margin-top:0.6rem;">Demo : admin / admin123</p>',unsafe_allow_html=True)
        with t2:
            st.markdown("<br>",unsafe_allow_html=True)
            nu=st.text_input("Nom d'utilisateur",key="ru")
            ne=st.text_input("Email",key="re")
            np=st.text_input("Mot de passe",type="password",key="rp")
            np2=st.text_input("Confirmer",type="password",key="rp2")
            if st.button("Creer mon compte",use_container_width=True,key="btn_reg"):
                if not all([nu,ne,np,np2]): st.error("Remplissez tous les champs.")
                elif len(np)<6: st.error("Mot de passe trop court.")
                elif np!=np2: st.error("Mots de passe differents.")
                elif "@" not in ne: st.error("Email invalide.")
                else:
                    ok,_,msg=register_user(nu,ne,np)
                    st.success(msg) if ok else st.error(msg)


# ─────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────

def render_sidebar(agent):
    with st.sidebar:
        user=st.session_state.user

        # Logo avec indicateur online
        st.markdown("""
        <div class="sb-logo">
            <div class="dot"></div>
            DataOlist AI
        </div>""",unsafe_allow_html=True)

        # Nouvelle conversation
        st.markdown('<div class="sb-new-chat">',unsafe_allow_html=True)
        if st.button("+ Nouvelle conversation",use_container_width=True,key="new_chat"):
            if st.session_state.messages: save_session(user["id"],st.session_state.messages)
            st.session_state.messages=[]
            st.session_state.query_count=0
            st.session_state.current_view="chat"
            st.session_state.open_menu=None
            agent.reset_memory()
            st.rerun()
        st.markdown('</div>',unsafe_allow_html=True)

        # Navigation
        nav=[("nav_search","Rechercher","search"),
             ("nav_disc","Discussions","discussions"),
             ("nav_ex","Questions exemples","examples")]
        for key,label,view in nav:
            st.markdown('<div class="sb-nav">',unsafe_allow_html=True)
            if st.button(label,key=key,use_container_width=True):
                st.session_state.current_view=view; st.rerun()
            st.markdown('</div>',unsafe_allow_html=True)

        st.divider()

        # Recents
        sessions=get_sessions(user["id"])
        if sessions:
            st.markdown('<span class="sb-section">Recents</span>',unsafe_allow_html=True)
            for s in sessions[:12]:
                label=s["name"][:24]+"..." if len(s["name"])>24 else s["name"]
                is_open=st.session_state.open_menu==s["id"]

                col_n,col_d=st.columns([11,1])
                with col_n:
                    st.markdown('<div class="sb-session">',unsafe_allow_html=True)
                    if st.button(label,key=f"s_{s['id']}",use_container_width=True,
                                 help=s["date"][:16].replace("T"," ")):
                        st.session_state.messages=s["messages"]
                        st.session_state.query_count=len([m for m in s["messages"] if m.get("role")=="user"])
                        st.session_state.current_view="chat"
                        st.session_state.open_menu=None
                        st.rerun()
                    st.markdown('</div>',unsafe_allow_html=True)
                with col_d:
                    st.markdown('<div class="sb-dots">',unsafe_allow_html=True)
                    if st.button("⋮",key=f"dots_{s['id']}"):
                        st.session_state.open_menu=None if is_open else s["id"]
                        st.rerun()
                    st.markdown('</div>',unsafe_allow_html=True)

                if is_open:
                    c1,c2=st.columns(2)
                    with c1:
                        st.markdown('<div class="sb-menu-btn">',unsafe_allow_html=True)
                        if st.button("Renommer",key=f"ren_{s['id']}",use_container_width=True):
                            st.session_state.rename_id=s["id"]
                            st.session_state.open_menu=None; st.rerun()
                        st.markdown('</div>',unsafe_allow_html=True)
                    with c2:
                        st.markdown('<div class="sb-menu-btn">',unsafe_allow_html=True)
                        if st.button("Supprimer",key=f"del_{s['id']}",use_container_width=True):
                            delete_session(s["id"])
                            st.session_state.open_menu=None; st.rerun()
                        st.markdown('</div>',unsafe_allow_html=True)

                if st.session_state.rename_id==s["id"]:
                    new_name=st.text_input("Nouveau nom",value=s["name"],key=f"ri_{s['id']}")
                    c1,c2=st.columns(2)
                    with c1:
                        if st.button("OK",key=f"rok_{s['id']}",use_container_width=True):
                            if new_name.strip(): rename_session(s["id"],new_name.strip())
                            st.session_state.rename_id=None; st.rerun()
                    with c2:
                        if st.button("Annuler",key=f"rcan_{s['id']}",use_container_width=True):
                            st.session_state.rename_id=None; st.rerun()

        st.divider()

        # Options
        st.session_state.show_chart=st.toggle("Graphiques automatiques",value=st.session_state.show_chart)

        st.divider()

        # Profil
        st.markdown(f"""
        <div class="sb-profile">
            <div class="sb-avatar">{user['username'][0].upper()}</div>
            <div>
                <div class="sb-user-name">{user['username'].upper()}</div>
                <div class="sb-user-plan">Forfait Free</div>
            </div>
        </div>""",unsafe_allow_html=True)

        st.markdown('<div class="sb-logout">',unsafe_allow_html=True)
        if st.button("Se deconnecter",use_container_width=True,key="logout"):
            if st.session_state.messages: save_session(user["id"],st.session_state.messages)
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
        st.markdown('</div>',unsafe_allow_html=True)


# ─────────────────────────────────────────────
#  Vues
# ─────────────────────────────────────────────

def render_discussions():
    user=st.session_state.user
    st.markdown("## Discussions"); st.divider()
    sessions=get_sessions(user["id"])
    if not sessions: st.info("Aucune conversation pour l'instant."); return
    for s in sessions:
        nb=len([m for m in s["messages"] if m.get("role")=="user"])
        c1,c2,c3=st.columns([6,2,1])
        with c1:
            if st.button(s["name"],key=f"disc_{s['id']}",use_container_width=True):
                st.session_state.messages=s["messages"]
                st.session_state.current_view="chat"; st.rerun()
        with c2: st.caption(f"{s['date'][:10]} · {nb} msg")
        with c3:
            if st.button("×",key=f"ddel_{s['id']}"): delete_session(s["id"]); st.rerun()
        st.divider()

def render_search():
    user=st.session_state.user
    st.markdown("## Rechercher")
    query=st.text_input("",placeholder="Rechercher dans vos conversations...",key="search_q")
    if query:
        results=search_sessions(user["id"],query)
        if results:
            st.markdown(f"**{len(results)} resultat(s) pour « {query} »**"); st.divider()
            for s in results:
                c1,c2=st.columns([7,2])
                with c1:
                    if st.button(s["name"],key=f"sr_{s['id']}",use_container_width=True):
                        st.session_state.messages=s["messages"]
                        st.session_state.current_view="chat"; st.rerun()
                with c2: st.caption(s["date"][:10])
        else: st.info(f"Aucun resultat pour « {query} ».")

def render_examples():
    st.markdown("## Questions exemples"); st.divider()
    for cat,questions in SAMPLE_QUESTIONS.items():
        st.markdown(f"**{cat}**")
        cols=st.columns(2)
        for i,q in enumerate(questions):
            with cols[i%2]:
                if st.button(q,key=f"ex_{cat}_{i}",use_container_width=True):
                    st.session_state["pending_question"]=q
                    st.session_state.current_view="chat"; st.rerun()
        st.markdown("")


# ─────────────────────────────────────────────
#  Visualisation
# ─────────────────────────────────────────────

def auto_visualize(df,question):
    if df is None or df.empty or len(df.columns)<2: return None
    nc=df.select_dtypes(include='number').columns.tolist()
    cc=df.select_dtypes(exclude='number').columns.tolist()
    ql=question.lower()
    fig=None
    tc=[c for c in df.columns if any(kw in c.lower() for kw in ['month','year','date','mois','annee'])]

    PALETTE=["#111110","#3d3d3b","#6b6b68","#999994","#c7c7c2"]

    if tc and nc:
        fig=px.line(df,x=tc[0],y=nc[0],markers=True,color_discrete_sequence=["#111110"])
    elif any(kw in ql for kw in ['top','meilleur','best','plus vendu','vendeur']) and nc and cc:
        df_s=df.sort_values(nc[0],ascending=True).tail(10)
        fig=px.bar(df_s,x=nc[0],y=cc[0],orientation='h',color_discrete_sequence=["#111110"])
    elif any(kw in ql for kw in ['paiement','payment','mode','type','repartition']) and cc and nc:
        fig=px.pie(df,names=cc[0],values=nc[0],hole=0.52,color_discrete_sequence=PALETTE)
    elif any(kw in ql for kw in ['etat','state','ville','city']) and cc and nc:
        df_s=df.sort_values(nc[0],ascending=False).head(15)
        fig=px.bar(df_s,x=cc[0],y=nc[0],color_discrete_sequence=["#111110"])
    elif nc and cc:
        df_s=df.head(15)
        fig=px.bar(df_s,x=cc[0],y=nc[0],color_discrete_sequence=["#111110"])
    elif len(nc)>=2:
        fig=px.scatter(df,x=nc[0],y=nc[1],color_discrete_sequence=["#111110"])

    if fig:
        fig.update_layout(
            plot_bgcolor='#ffffff',paper_bgcolor='#ffffff',
            font=dict(family="Geist",size=11,color="#6f6e69"),
            margin=dict(l=24,r=16,t=28,b=24),
            xaxis=dict(gridcolor="#f0ede8",linecolor="#e8e5e0",tickfont=dict(size=10)),
            yaxis=dict(gridcolor="#f0ede8",linecolor="#e8e5e0",tickfont=dict(size=10)),
            showlegend=False,
        )
    return fig


# ─────────────────────────────────────────────
#  Messages
# ─────────────────────────────────────────────

def has_df(msg):
    df=msg.get("dataframe")
    return df is not None and isinstance(df,pd.DataFrame) and not df.empty and len(df.columns)>0

def render_chat_messages():
    for i,msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if has_df(msg):
                df=msg["dataframe"]
                with st.expander(f"Tableau de donnees · {len(df)} lignes",expanded=False):
                    st.dataframe(df,use_container_width=True,hide_index=True)
                if msg.get("show_export"):
                    st.markdown('<div style="display:flex;gap:0.4rem;margin-top:0.3rem;">',unsafe_allow_html=True)
                    c1,c2,c3=st.columns([1,1,1])
                    with c1:
                        st.markdown('<div class="export-btn">',unsafe_allow_html=True)
                        st.download_button("Telecharger CSV",df.to_csv(index=False).encode('utf-8'),
                                           "resultats.csv","text/csv",key=f"csv_{i}")
                        st.markdown('</div>',unsafe_allow_html=True)
                    with c2:
                        st.markdown('<div class="export-btn">',unsafe_allow_html=True)
                        xl=export_excel(df)
                        st.download_button("Telecharger Excel",xl,"resultats.xlsx",
                                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                           key=f"xl_{i}")
                        st.markdown('</div>',unsafe_allow_html=True)
                    with c3:
                        st.markdown('<div class="export-btn">',unsafe_allow_html=True)
                        pdf=export_pdf_report(df)
                        if pdf: st.download_button("Telecharger PDF",pdf,"resultats.pdf","application/pdf",key=f"pdf_{i}")
                        st.markdown('</div>',unsafe_allow_html=True)
            if msg.get("figure") and st.session_state.show_chart:
                st.plotly_chart(msg["figure"],use_container_width=True)


# ─────────────────────────────────────────────
#  Traitement question
# ─────────────────────────────────────────────

def get_recent_context():
    """
    Retourne le contexte le plus pertinent pour 'resume/explique-le' :
    le dernier fichier analyse OU la derniere reponse data (SQL),
    selon lequel des deux est le plus recent (via 'order').
    """
    file_ctx = st.session_state.get("last_file_context")
    data_ctx = st.session_state.get("last_data_context")

    file_order = file_ctx.get("order", -1) if file_ctx else -1
    data_order = data_ctx.get("order", -1) if data_ctx else -1

    if file_order < 0 and data_order < 0:
        return None, None

    if data_order >= file_order:
        text = f"Question posee : {data_ctx['question']}\nReponse : {data_ctx['summary']}\nAperçu des donnees :\n{data_ctx['table_preview']}"
        return text, "la derniere reponse/graphique"
    else:
        text = file_ctx.get("extracted_text") or file_ctx.get("last_answer")
        return text, f"le fichier « {file_ctx.get('name','')} »"

def no_data_message(reason, lang="french"):
    """Message honnete quand on n'a pas l'information demandee."""
    base = {
        "french": "Je n'ai pas cette donnee pour l'instant.",
        "english": "I don't have that data available right now.",
        "arabic": "ليست لدي هذه المعلومة حاليا.",
        "darija": "Ma3ndi machi had l'data daba.",
    }.get(lang, "Je n'ai pas cette donnee pour l'instant.")
    return f"{base} ({reason})" if reason else base

def condense(text, fmt):
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import PromptTemplate
    try:
        llm = get_groq_llm(temperature=0.0)
    except RuntimeError as e:
        return f"Je ne peux pas resumer pour l'instant : {e}"
    instructions = {
        "court": "Resume en 1 phrase tres courte avec les chiffres essentiels:\n{p}",
        "explique": "Explique clairement et simplement, en francais, ce contenu (s'il s'agit d'un graphe, decris les axes, la tendance et les valeurs cles):\n{p}",
    }
    pt = instructions.get(fmt, "Fais un resume structure en 3-5 bullet points:\n{p}")
    try:
        return (PromptTemplate.from_template(pt) | llm | StrOutputParser()).invoke({"p": text})
    except Exception as e:
        return f"Je n'ai pas pu generer cette reponse pour l'instant (erreur technique : {e})."

def process_question(question,agent):
    lang=detect_language(question)
    fmt=detect_format(question)
    q_corr=correct_typos(question)
    is_fmt_only=fmt in ["court","resume","explique"] and not is_data_q(q_corr)

    st.session_state.messages.append({"role":"user","content":question})
    with st.chat_message("user"): st.markdown(question)

    if len(question.strip())<3:
        r="Pouvez-vous preciser votre question ?"
        with st.chat_message("assistant"): st.markdown(r)
        st.session_state.messages.append({"role":"assistant","content":r,"figure":None,"show_export":False})
        st.session_state.query_count+=1
        return

    q_lower=question.lower().strip()
    if q_lower in SALUTATIONS_SET or (not is_data_q(q_corr) and fmt=="normal"):
        r=get_conv_response(question,lang)
        with st.chat_message("assistant"): st.markdown(r)
        st.session_state.messages.append({"role":"assistant","content":r,"figure":None,"show_export":False})
        st.session_state.query_count+=1
        return

    # "Resume-le / explique-le / en court" -> priorite au dernier fichier/graphe en memoire,
    # sinon on retombe sur la derniere reponse texte de l'assistant.
    if is_fmt_only:
        file_text, file_label = get_recent_context()
        if file_text:
            r = condense(file_text, fmt)
            if file_label:
                r = f"À propos de {file_label} :\n\n{r}"
            with st.chat_message("assistant"): st.markdown(r)
            st.session_state.messages.append({"role":"assistant","content":r,"figure":None,"show_export":False})
            st.session_state.query_count+=1
            return

        last=next((m["content"] for m in reversed(st.session_state.messages[:-1])
                   if m.get("role")=="assistant" and m.get("content")),None)
        if last:
            r=condense(last,fmt)
            with st.chat_message("assistant"): st.markdown(r)
            st.session_state.messages.append({"role":"assistant","content":r,"figure":None,"show_export":False})
            st.session_state.query_count+=1
            return

        # Rien a resumer/expliquer : aucun fichier, aucune reponse precedente
        r = no_data_message("aucun fichier ou reponse precedente n'a ete trouve dans cette conversation", lang)
        with st.chat_message("assistant"): st.markdown(r)
        st.session_state.messages.append({"role":"assistant","content":r,"figure":None,"show_export":False})
        st.session_state.query_count+=1
        return

    show_export=fmt in ["export_pdf","export_excel","export_csv","export"]

    with st.chat_message("assistant"):
        with st.spinner("Analyse en cours..."):
            result=agent.query(q_corr)

        answer=result["answer"]

        df_check = result.get("dataframe", pd.DataFrame())
        df_is_empty = df_check is None or not isinstance(df_check, pd.DataFrame) or df_check.empty

        if result.get("error"):
            # Echec SQL meme apres retries : on est honnete plutot que de laisser le LLM divaguer
            answer = no_data_message(
                "la requete sur la base de donnees a echoue malgre les tentatives de correction",
                lang,
            )
        elif df_is_empty and not result.get("error"):
            # Requete executee avec succes mais aucune ligne -> pas de donnees correspondantes,
            # on ne laisse pas le LLM inventer une reponse a partir de rien.
            answer = no_data_message(
                "la base de donnees ne contient aucun resultat correspondant a cette question",
                lang,
            )
        elif fmt=="court" and len(answer)>150:
            try: answer=condense(answer,"court")
            except: pass

        st.markdown(answer)

        df=result.get("dataframe",pd.DataFrame())
        valid=df is not None and isinstance(df,pd.DataFrame) and not df.empty and len(df.columns)>0
        fig=None

        if valid:
            with st.expander(f"Tableau de donnees · {len(df)} lignes",expanded=len(df)<=5):
                st.dataframe(df,use_container_width=True,hide_index=True)

            if show_export:
                st.markdown('<p style="font-size:0.8rem;font-weight:600;color:#6f6e69;margin:0.4rem 0 0.2rem;">Telecharger les donnees</p>',unsafe_allow_html=True)
                c1,c2,c3=st.columns(3)
                with c1:
                    st.markdown('<div class="export-btn">',unsafe_allow_html=True)
                    st.download_button("CSV",df.to_csv(index=False).encode('utf-8'),"resultats.csv","text/csv",key="csv_n")
                    st.markdown('</div>',unsafe_allow_html=True)
                with c2:
                    st.markdown('<div class="export-btn">',unsafe_allow_html=True)
                    xl=export_excel(df)
                    st.download_button("Excel",xl,"resultats.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key="xl_n")
                    st.markdown('</div>',unsafe_allow_html=True)
                with c3:
                    st.markdown('<div class="export-btn">',unsafe_allow_html=True)
                    pdf=export_pdf_report(df)
                    if pdf: st.download_button("PDF",pdf,"resultats.pdf","application/pdf",key="pdf_n")
                    st.markdown('</div>',unsafe_allow_html=True)

            fig=auto_visualize(df,question)
            if fig: st.plotly_chart(fig,use_container_width=True)

        if result.get("error"):
            st.error(f"Erreur : {result['error']}")

    st.session_state.messages.append({
        "role":"assistant","content":answer,
        "dataframe":df if valid else pd.DataFrame(),
        "figure":fig,"show_export":show_export,
    })
    # Memorise cette reponse data comme contexte le plus recent, pour
    # que "resume-le"/"explique-le" puisse s'y referer ensuite.
    if valid:
        st.session_state.context_order += 1
        st.session_state.last_data_context = {
            "question": question,
            "summary": answer,
            "table_preview": df.head(10).to_string(index=False),
            "order": st.session_state.context_order,
        }
    st.session_state.query_count+=1


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

def main():
    init_db(); init_session()

    if not st.session_state.authenticated:
        render_auth(); return

    try: agent=load_agent()
    except Exception as e: st.error(f"Erreur agent : {e}"); st.stop()

    render_sidebar(agent)

    view=st.session_state.current_view
    if view=="discussions": render_discussions(); return
    elif view=="search": render_search(); return
    elif view=="examples": render_examples(); return

    # ── Messages AU-DESSUS ──
    if not st.session_state.messages:
        user=st.session_state.user
        st.markdown(f"""
        <div class="chat-welcome">
            <h1>Bonjour, {user['username']} 👋</h1>
            <p>Comment puis-je vous aider avec les donnees Olist aujourd'hui ?</p>
        </div>""",unsafe_allow_html=True)
    else:
        render_chat_messages()

    pending=st.session_state.pop("pending_question",None)
    if pending: process_question(pending,agent)

    # ── Barre de saisie EN BAS ──
    col_plus,col_chat=st.columns([1,22])
    with col_plus:
        st.markdown('<div class="plus-btn">',unsafe_allow_html=True)
        if st.button("+",key="toggle_upload",help="Joindre une image ou un PDF"):
            st.session_state.show_upload=not st.session_state.get("show_upload",False)
            st.rerun()
        st.markdown('</div>',unsafe_allow_html=True)
    with col_chat:
        if prompt:=st.chat_input("Posez votre question / Ask / اسأل / Suwel..."):
            process_question(prompt,agent)

    # Panel upload
    if st.session_state.get("show_upload",False):
        st.markdown("""
        <div class="upload-panel">
            <div class="upload-panel-title">📎 Joindre un fichier</div>
        </div>""",unsafe_allow_html=True)
        uf=st.file_uploader("Choisissez un fichier",type=["png","jpg","jpeg","pdf"],
                            key="fup",label_visibility="collapsed")
        fq=st.text_input("Votre question sur ce fichier (optionnel)",
                         placeholder="Ex: Resume ce document, Qu'est-ce que tu vois ?",key="fq")
        c1,c2=st.columns([3,1])
        with c1:
            if uf and st.button("Analyser le fichier",use_container_width=True,key="analyze_file"):
                with st.spinner("Analyse en cours..."):
                    r, extracted = analyze_file(uf,fq)
                label=f"[{uf.name}] {fq}" if fq else f"[{uf.name}]"
                st.session_state.messages.append({"role":"user","content":label})
                st.session_state.messages.append({"role":"assistant","content":r,"figure":None,"show_export":False})
                # Memorise le contenu pour que "resume-le" / "explique-le" fonctionnent ensuite
                st.session_state.context_order += 1
                st.session_state.last_file_context = {
                    "name": uf.name,
                    "extracted_text": extracted,
                    "last_answer": r,
                    "order": st.session_state.context_order,
                }
                st.session_state.show_upload=False; st.rerun()
        with c2:
            if st.button("Fermer",use_container_width=True,key="close_upload"):
                st.session_state.show_upload=False; st.rerun()

    # Disclaimer
    st.markdown("""
    <div class="disclaimer">
        DataOlist AI est une IA et peut faire des erreurs. Veuillez verifier les reponses importantes.
    </div>""",unsafe_allow_html=True)


if __name__=="__main__":
    main()