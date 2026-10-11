"""
API REST FastAPI — Moteur NLP → SQL
Expose l'agent conversationnel via HTTP pour intégration frontend.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

from nlp_sql_agent import NLPSQLAgent # type: ignore

app = FastAPI(
    title="NLP SQL Engine",
    description="Traduction langage naturel → SQL sur la base Olist",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instance unique de l'agent (mémoire partagée par session)
agent = NLPSQLAgent(memory_window=5)


class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = "default"


class QueryResponse(BaseModel):
    success: bool
    question: str
    sql: Optional[str] = None
    explication: Optional[str] = None
    confiance: Optional[str] = None
    avertissement: Optional[str] = None
    columns: Optional[list] = None
    rows: Optional[list] = None
    nb_rows: Optional[int] = None
    error: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "model": "mistral-large-latest"}


@app.get("/schema")
def get_schema():
    """Retourne le schéma de la base de données."""
    return {"schema": agent.schema}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    """
    Traduit une question en SQL, l'exécute et retourne les résultats.
    Maintient le contexte conversationnel entre les appels.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="La question ne peut pas être vide.")

    result = agent.query(request.question)
    return QueryResponse(**result)


@app.post("/reset")
def reset():
    """Réinitialise la mémoire conversationnelle."""
    agent.reset_memory()
    return {"message": "Mémoire réinitialisée avec succès."}


@app.get("/examples")
def examples():
    """Exemples de questions pour tester le moteur."""
    return {
        "examples": [
            "Quels sont les 10 produits les plus vendus ?",
            "Quel est le taux de livraison en retard par état brésilien ?",
            "Montre-moi l'évolution du chiffre d'affaires mensuel en 2018.",
            "Quels vendeurs ont la meilleure note moyenne avec plus de 50 avis ?",
            "Combien de commandes ont été annulées le mois dernier ?",
            "Quelle est la catégorie de produit la plus rentable ?",
            "Compare le délai moyen de livraison par type de paiement.",
        ]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
