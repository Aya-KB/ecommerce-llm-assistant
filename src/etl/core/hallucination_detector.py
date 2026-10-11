# -*- coding: utf-8 -*-
"""
Module de detection des hallucinations et post-traitement des requetes SQL
Couche de securite entre le LLM et la base de donnees
"""

import re
import logging
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Types d'anomalies detectees
# ─────────────────────────────────────────────

@dataclass
class ValidationResult:
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    cleaned_sql: str = ""
    confidence: float = 1.0

    def add_issue(self, msg: str):
        self.issues.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)
        self.confidence = max(0.0, self.confidence - 0.1)

    def __str__(self):
        status = "Valide" if self.is_valid else "Invalide"
        parts = [f"Statut: {status} (confiance: {self.confidence:.0%})"]
        if self.issues:
            parts.append("Problemes: " + "; ".join(self.issues))
        if self.warnings:
            parts.append("Avertissements: " + "; ".join(self.warnings))
        return "\n".join(parts)


# ─────────────────────────────────────────────
#  Hallucination Detector
# ─────────────────────────────────────────────

class HallucinationDetector:
    """
    Detecte les hallucinations courantes du LLM dans les requetes SQL generees.
    """

    # Tables reelles dans la base Olist
    KNOWN_TABLES = {
        "orders", "customers", "order_items", "payments",
        "reviews", "products", "sellers",
        "product_category_name_translation", "geolocation"
    }

    # Alias SQL courants a ignorer (pas des tables)
    KNOWN_ALIASES = {
        "o", "c", "oi", "op", "or", "p", "s", "r", "t",
        "ord", "cus", "ite", "pay", "rev", "pro", "sel"
    }

    # Colonnes connues par table
    KNOWN_COLUMNS: Dict[str, List[str]] = {
        "orders": [
            "order_id", "customer_id", "order_status",
            "order_purchase_timestamp", "order_approved_at",
            "order_delivered_carrier_date", "order_delivered_customer_date",
            "order_estimated_delivery_date"
        ],
        "customers": [
            "customer_id", "customer_unique_id", "customer_zip_code_prefix",
            "customer_city", "customer_state"
        ],
        "order_items": [
            "order_id", "order_item_id", "product_id", "seller_id",
            "shipping_limit_date", "price", "freight_value"
        ],
        "payments": [
            "order_id", "payment_sequential", "payment_type",
            "payment_installments", "payment_value"
        ],
        "reviews": [
            "review_id", "order_id", "review_score",
            "review_comment_title", "review_comment_message",
            "review_creation_date", "review_answer_timestamp"
        ],
        "products": [
            "product_id", "product_category_name",
            "product_name_lenght", "product_description_lenght",
            "product_photos_qty", "product_weight_g",
            "product_length_cm", "product_height_cm", "product_width_cm"
        ],
        "sellers": [
            "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"
        ],
        "product_category_name_translation": [
            "product_category_name", "product_category_name_english"
        ],
        "geolocation": [
            "geolocation_zip_code_prefix", "geolocation_lat",
            "geolocation_lng", "geolocation_city", "geolocation_state"
        ],
    }

    # Mots-cles interdits
    FORBIDDEN_KEYWORDS = re.compile(
        r'\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|'
        r'EXEC|EXECUTE|CALL|MERGE|REPLACE|LOAD|IMPORT)\b',
        re.IGNORECASE
    )

    # Patterns suspects
    SUSPICIOUS_PATTERNS = [
        re.compile(r';\s*SELECT', re.IGNORECASE),
        re.compile(r'/\*.*?\*/', re.DOTALL),
        re.compile(r'UNION\s+ALL?\s+SELECT', re.IGNORECASE),
    ]

    def __init__(self, known_tables: Optional[set] = None,
                 known_columns: Optional[Dict] = None):
        if known_tables:
            self.KNOWN_TABLES = known_tables
        if known_columns:
            self.KNOWN_COLUMNS = known_columns

    def check_destructive_keywords(self, sql: str, result: ValidationResult):
        match = self.FORBIDDEN_KEYWORDS.search(sql)
        if match:
            result.add_issue(
                f"Mot-cle dangereux detecte: '{match.group()}'. "
                "Seules les requetes SELECT sont autorisees."
            )

    def check_suspicious_patterns(self, sql: str, result: ValidationResult):
        for pattern in self.SUSPICIOUS_PATTERNS:
            if pattern.search(sql):
                result.add_issue(f"Pattern suspect detecte.")
                break

    def check_select_start(self, sql: str, result: ValidationResult):
        stripped = sql.strip().upper()
        if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
            result.add_issue(
                f"La requete doit commencer par SELECT ou WITH. "
                f"Debut actuel: '{sql[:40]}'"
            )

    def check_table_names(self, sql: str, result: ValidationResult):
        """Detecte les tables hallucinees en ignorant les alias courts."""
        from_pattern = re.compile(
            r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            re.IGNORECASE
        )
        found_tables = from_pattern.findall(sql)
        for table in found_tables:
            table_lower = table.lower()
            # Ignore les alias courts (1-3 lettres) et alias connus
            if len(table) <= 3:
                continue
            if table_lower in self.KNOWN_ALIASES:
                continue
            if table_lower not in self.KNOWN_TABLES:
                result.add_warning(
                    f"Table inconnue detectee: '{table}'. "
                    f"Tables valides: {', '.join(sorted(self.KNOWN_TABLES))}"
                )

    def check_common_column_typos(self, sql: str, result: ValidationResult):
        """Detecte les fautes de frappe courantes dans les noms de colonnes."""
        COMMON_TYPOS = {
            "product_name_length": "product_name_lenght",
            "product_description_length": "product_description_lenght",
            "order_date": "order_purchase_timestamp",
            "customer_name": "(non disponible)",
            "seller_name": "(non disponible)",
            "total_price": "price (dans order_items)",
            "amount": "payment_value (dans payments)",
            "rating": "review_score (dans reviews)",
        }
        sql_lower = sql.lower()
        for wrong, correct in COMMON_TYPOS.items():
            if wrong in sql_lower:
                result.add_warning(
                    f"Colonne '{wrong}' incorrecte. Utilisez: '{correct}'"
                )

    def check_missing_join_conditions(self, sql: str, result: ValidationResult):
        join_count = len(re.findall(r'\bJOIN\b', sql, re.IGNORECASE))
        on_count = len(re.findall(r'\bON\b', sql, re.IGNORECASE))
        if join_count > on_count:
            result.add_warning(
                f"Possible jointure sans condition ON "
                f"({join_count} JOIN(s) mais {on_count} ON clause(s))"
            )

    def check_missing_group_by(self, sql: str, result: ValidationResult):
        has_agg = bool(re.search(
            r'\b(COUNT|SUM|AVG|MAX|MIN)\s*\(', sql, re.IGNORECASE
        ))
        has_group = bool(re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE))
        has_subquery = "(" in sql

        if has_agg and not has_group and not has_subquery:
            select_part = re.search(
                r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL
            )
            if select_part:
                select_content = select_part.group(1)
                non_agg_cols = re.sub(
                    r'\b(COUNT|SUM|AVG|MAX|MIN)\s*\([^)]*\)(\s+AS\s+\w+)?',
                    '', select_content, flags=re.IGNORECASE
                ).strip().strip(',').strip()
                if non_agg_cols and non_agg_cols not in ('*', ''):
                    result.add_warning(
                        "Colonnes non agregees detectees sans GROUP BY."
                    )

    def validate(self, sql: str) -> ValidationResult:
        result = ValidationResult(is_valid=True, cleaned_sql=sql)

        self.check_select_start(sql, result)
        self.check_destructive_keywords(sql, result)
        self.check_suspicious_patterns(sql, result)
        self.check_table_names(sql, result)
        self.check_common_column_typos(sql, result)
        self.check_missing_join_conditions(sql, result)
        self.check_missing_group_by(sql, result)

        if result.warnings:
            logger.warning(f"Avertissements SQL: {result.warnings}")
        if not result.is_valid:
            logger.error(f"Validation SQL echouee: {result.issues}")

        return result


# ─────────────────────────────────────────────
#  SQL Post-Processor
# ─────────────────────────────────────────────

class SQLPostProcessor:

    @staticmethod
    def remove_markdown(sql: str) -> str:
        sql = re.sub(r"```(?:sql|SQL)?", "", sql)
        sql = sql.replace("`", "")
        return sql.strip()

    @staticmethod
    def remove_llm_preamble(sql: str) -> str:
        prefixes = [
            r"^(?:voici|here is|voila)\s+(?:la\s+)?(?:requete|query|sql)\s*:?\s*",
            r"^sql\s*:\s*",
            r"^requete\s*:\s*",
        ]
        for prefix in prefixes:
            sql = re.sub(prefix, "", sql, flags=re.IGNORECASE).strip()
        return sql

    @staticmethod
    def ensure_semicolon(sql: str) -> str:
        sql = sql.rstrip()
        if not sql.endswith(";"):
            sql += ";"
        return sql

    @staticmethod
    def add_limit_if_missing(sql: str, max_rows: int = 500) -> str:
        sql_upper = sql.upper()
        has_limit = "LIMIT" in sql_upper
        is_count_only = (
            bool(re.search(r"SELECT\s+COUNT\s*\(", sql_upper))
            and "GROUP BY" not in sql_upper
            and sql_upper.count("SELECT") == 1
        )
        if not has_limit and not is_count_only:
            sql = sql.rstrip(";")
            sql += f"\nLIMIT {max_rows};"
        return sql

    @staticmethod
    def fix_postgres_date_syntax(sql: str) -> str:
        sql = re.sub(r'\bYEAR\((\w+)\)', r'EXTRACT(YEAR FROM \1)',
                     sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bMONTH\((\w+)\)', r'EXTRACT(MONTH FROM \1)',
                     sql, flags=re.IGNORECASE)
        sql = re.sub(r"DATE_FORMAT\((\w+),\s*'%Y-%m'\)",
                     r"TO_CHAR(\1, 'YYYY-MM')", sql, flags=re.IGNORECASE)
        return sql

    @classmethod
    def process(cls, raw_sql: str, max_rows: int = 500) -> str:
        sql = cls.remove_markdown(raw_sql)
        sql = cls.remove_llm_preamble(sql)
        sql = cls.fix_postgres_date_syntax(sql)
        sql = cls.add_limit_if_missing(sql, max_rows)
        sql = cls.ensure_semicolon(sql)
        return sql