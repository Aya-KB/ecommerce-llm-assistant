# -*- coding: utf-8 -*-
import os
import pickle
import logging
import re
from typing import Optional
from pathlib import Path

import faiss
import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from groq import Groq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIM   = 384
CHUNK_SIZE  = 700
CHUNK_OVER  = 80
TOP_K       = 6
RELEVANCE_THRESHOLD = 0.25


# ─────────────────────────────────────────────
# 🧼 CLEANING ULTRA IMPORTANT (ANTI IDS)
# ─────────────────────────────────────────────
def clean_text(text: str) -> str:
    """
    Supprime tout ce qui ressemble à des IDs techniques.
    """

    # UUID / hash 24+ chars
    text = re.sub(r"\b[a-f0-9]{20,}\b", "vendeur", text)

    # seller_id / product_id etc
    text = re.sub(r"\b(seller_id|customer_id|order_id|product_id)\b", "", text, flags=re.IGNORECASE)

    # IDs alphanumériques longs
    text = re.sub(r"\b[A-Z0-9_-]{15,}\b", "vendeur", text)

    return text


def clean_output(text: str) -> str:
    """
    Nettoyage FINAL de la réponse LLM (sécurité maximale).
    """

    text = clean_text(text)

    # supprime lignes qui ne contiennent QUE des IDs
    text = re.sub(r"^.*\bvendeur\b.*$", "", text, flags=re.MULTILINE)

    # nettoyage espaces doubles
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


class RAGAgent:

    def __init__(
        self,
        groq_api_key: str,
        faiss_index_path: str = "faiss_olist_index",
        pdf_folder: str = "data/documents",
    ):
        self.groq_api_key     = groq_api_key
        self.faiss_index_path = faiss_index_path
        self.pdf_folder       = pdf_folder

        self.embedder = SentenceTransformer(EMBED_MODEL)
        self.groq = Groq(api_key=groq_api_key)

        self.index: Optional[faiss.IndexFlatIP] = None
        self.chunks: list[dict] = []

        logger.info("RAGAgent initialisé")

    # ─────────────────────────────
    @property
    def is_indexed(self) -> bool:
        return self.index is not None and len(self.chunks) > 0

    # ─────────────────────────────
    def save_index(self):
        Path(self.faiss_index_path).mkdir(parents=True, exist_ok=True)

        faiss.write_index(
            self.index,
            os.path.join(self.faiss_index_path, "index.faiss")
        )

        with open(os.path.join(self.faiss_index_path, "index.pkl"), "wb") as f:
            pickle.dump(self.chunks, f)

        logger.info("Index sauvegardé")

    # ─────────────────────────────
    def load_index(self):
        faiss_file = os.path.join(self.faiss_index_path, "index.faiss")
        pkl_file   = os.path.join(self.faiss_index_path, "index.pkl")

        if not (os.path.exists(faiss_file) and os.path.exists(pkl_file)):
            return False

        self.index = faiss.read_index(faiss_file)

        with open(pkl_file, "rb") as f:
            self.chunks = pickle.load(f)

        return True

    # ─────────────────────────────
    def clear_index(self):
        self.index = None
        self.chunks = []
        logger.info("Index reset")

    # ─────────────────────────────
    def retrieve(self, question: str, top_k: int = TOP_K):
        if not self.is_indexed:
            return []

        vec = self.embedder.encode([question], normalize_embeddings=True)
        vec = np.array(vec, dtype="float32")

        scores, indices = self.index.search(vec, min(top_k, len(self.chunks)))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0:
                chunk = self.chunks[idx].copy()

                # 🧼 CLEAN CHUNK TEXT
                chunk["text"] = clean_text(chunk["text"])

                chunk["score"] = float(score)
                results.append(chunk)

        return results

    # ─────────────────────────────
    def ask(self, question: str) -> Optional[str]:

        if not self.is_indexed:
            return None

        chunks = self.retrieve(question)

        if not chunks:
            return None

        best_score = chunks[0]["score"]

        if best_score < RELEVANCE_THRESHOLD:
            return None

        relevant = [c for c in chunks if c["score"] >= RELEVANCE_THRESHOLD]

        context = "\n\n---\n\n".join([
            c["text"] for c in relevant
        ])

        prompt = f"""
Tu es un assistant e-commerce.

RÈGLES STRICTES :
- INTERDIT ABSOLU : afficher des IDs, hashes, seller_id, product_id ou codes techniques
- Transforme toutes les données en langage humain simple
- Ne montre jamais de données techniques brutes
- Si tu vois un ID → ignore-le totalement
- Réponds naturellement

CONTEXTE :
{context}

QUESTION :
{question}

RÉPONSE :
"""

        try:
            resp = self.groq.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=500,
            )

            answer = resp.choices[0].message.content.strip()

            # 🧼 CLEAN FINAL OUTPUT (IMPORTANT)
            answer = clean_output(answer)

            return answer

        except Exception as e:
            logger.error(f"RAG error: {e}")
            return None

    # ─────────────────────────────
    def _chunk_text(self, text: str, source: str, page: int = 1):
        chunks = []
        start = 0

        while start < len(text):
            end = start + CHUNK_SIZE
            chunk = text[start:end].strip()

            if len(chunk) > 30:
                chunks.append({
                    "text": clean_text(chunk),
                    "source": source,
                    "page": page
                })

            start += CHUNK_SIZE - CHUNK_OVER

        return chunks

    # ─────────────────────────────
    def _index_chunks(self, chunks: list[dict]) -> int:
        if not chunks:
            return 0

        texts = [c["text"] for c in chunks]

        vecs = self.embedder.encode(texts, normalize_embeddings=True)
        vecs = np.array(vecs, dtype="float32")

        if self.index is None:
            self.index = faiss.IndexFlatIP(EMBED_DIM)

        self.index.add(vecs)
        self.chunks.extend(chunks)

        return len(chunks)