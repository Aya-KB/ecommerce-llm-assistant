# -*- coding: utf-8 -*-
"""
Gestionnaire du schema de la base de donnees Olist E-commerce
"""

from typing import Dict, List, Optional
from sqlalchemy import create_engine, inspect, text


# ─────────────────────────────────────────────
#  Noms reels des tables dans votre base
# ─────────────────────────────────────────────

OLIST_TABLES = [
    "orders",
    "customers",
    "order_items",
    "payments",
    "reviews",
    "products",
    "sellers",
]


# ─────────────────────────────────────────────
#  Questions de demonstration pre-definies
# ─────────────────────────────────────────────

SAMPLE_QUESTIONS = {
    "Ventes & Revenus": [
        "Quel est le chiffre d'affaires total de la plateforme ?",
        "Montre l'evolution mensuelle des ventes en 2017",
        "Quels sont les 10 produits les plus vendus ?",
        "Quelle est la valeur moyenne d'une commande ?",
    ],
    "Clients": [
        "Quels etats ont le plus de clients ?",
        "Combien de clients ont commande plus d'une fois ?",
        "Quelle est la ville avec le plus grand nombre de commandes ?",
    ],
    "Vendeurs": [
        "Quels sont les 5 meilleurs vendeurs par revenu ?",
        "Combien de vendeurs actifs y a-t-il par etat ?",
        "Quel est le vendeur avec la meilleure note moyenne ?",
    ],
    "Livraisons": [
        "Quel est le delai moyen de livraison en jours ?",
        "Combien de commandes ont ete livrees en retard ?",
        "Quels etats ont les delais de livraison les plus longs ?",
    ],
    "Satisfaction Clients": [
        "Quelle est la note moyenne des avis clients ?",
        "Montre la distribution des notes de 1 a 5",
        "Quelles categories de produits ont les meilleures notes ?",
    ],
    "Paiements": [
        "Quelle est la repartition des modes de paiement ?",
        "Quel est le nombre moyen de mensualites pour les paiements par carte ?",
        "Combien de commandes ont ete payees en plusieurs fois ?",
    ],
}


# ─────────────────────────────────────────────
#  Contexte metier pour le LLM
# ─────────────────────────────────────────────

OLIST_BUSINESS_CONTEXT = """
=== BASE DE DONNEES E-COMMERCE OLIST (Bresil) ===

Tables disponibles et leurs colonnes importantes :

TABLE orders (commandes):
  - order_id : identifiant unique
  - customer_id : FK -> customers
  - order_status : 'delivered', 'shipped', 'canceled', 'processing'
  - order_purchase_timestamp : date de commande
  - order_delivered_customer_date : date de livraison effective
  - order_estimated_delivery_date : date de livraison estimee

TABLE customers (clients):
  - customer_id : identifiant unique
  - customer_unique_id : id consolide
  - customer_city : ville
  - customer_state : etat bresilien (SP, RJ, MG...)

TABLE order_items (lignes de commande):
  - order_id : FK -> orders
  - product_id : FK -> products
  - seller_id : FK -> sellers
  - price : prix unitaire en BRL
  - freight_value : cout de livraison en BRL

TABLE payments (paiements):
  - order_id : FK -> orders
  - payment_type : 'credit_card', 'boleto', 'voucher', 'debit_card'
  - payment_installments : nombre de mensualites
  - payment_value : montant paye en BRL

TABLE reviews (avis clients):
  - order_id : FK -> orders
  - review_score : note de 1 a 5
  - review_comment_message : texte de l'avis

TABLE products (produits):
  - product_id : identifiant unique
  - product_category_name : categorie en portugais

TABLE sellers (vendeurs):
  - seller_id : identifiant unique
  - seller_city : ville
  - seller_state : etat bresilien

=== JOINTURES IMPORTANTES ===
orders o JOIN customers c ON o.customer_id = c.customer_id
orders o JOIN order_items oi ON o.order_id = oi.order_id
orders o JOIN payments p ON o.order_id = p.order_id
orders o JOIN reviews r ON o.order_id = r.order_id
order_items oi JOIN products p ON oi.product_id = p.product_id
order_items oi JOIN sellers s ON oi.seller_id = s.seller_id

=== PERIODE DES DONNEES ===
2016 a 2018.
"""


# ─────────────────────────────────────────────
#  Schema Manager
# ─────────────────────────────────────────────

class SchemaManager:

    def __init__(self, engine):
        self.engine = engine
        self._inspector = inspect(engine)
        self._full_context: Optional[str] = None

    def get_table_names(self) -> List[str]:
        return self._inspector.get_table_names()

    def get_columns(self, table_name: str) -> List[Dict]:
        return self._inspector.get_columns(table_name)

    def build_schema_summary(self) -> str:
        lines = ["=== SCHEMA SQL ===\n"]
        for table in OLIST_TABLES:
            try:
                cols = self.get_columns(table)
                col_defs = ", ".join(f"{c['name']} ({str(c['type'])})" for c in cols)
                lines.append(f"TABLE {table}:\n  Colonnes: {col_defs}\n")
            except Exception:
                pass
        return "\n".join(lines)

    def get_full_context(self) -> str:
        if self._full_context:
            return self._full_context
        self._full_context = OLIST_BUSINESS_CONTEXT + "\n\n" + self.build_schema_summary()
        return self._full_context

    def get_row_counts(self) -> Dict[str, int]:
        counts = {}
        with self.engine.connect() as conn:
            for table in OLIST_TABLES:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    counts[table] = result.scalar()
                except Exception:
                    counts[table] = -1
        return counts

    def to_dict(self) -> Dict:
        schema = {}
        for table in OLIST_TABLES:
            try:
                schema[table] = {
                    "columns": [
                        {"name": c["name"], "type": str(c["type"])}
                        for c in self.get_columns(table)
                    ],
                }
            except Exception:
                pass
        return schema