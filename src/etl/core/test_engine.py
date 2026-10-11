"""
Tests de validation du moteur NLP â SQL
Lance avec : python test_engine.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hallucination_detector import HallucinationDetector, SQLPostProcessor

def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


# âââââââââââââââââââââââââââââââââââââââââââââ
#  Tests du Post-Processor
# âââââââââââââââââââââââââââââââââââââââââââââ

def test_post_processor():
    separator("Tests du SQLPostProcessor")
    p = SQLPostProcessor()

    cases = [
        (
            "Suppression markdown",
            "```sql\nSELECT * FROM orders;\n```",
            "SELECT * FROM orders"  # LIMIT peut Ãªtre ajoutÃ©, on vÃ©rifie juste le dÃ©but
        ),
        (
            "Suppression prÃ©ambule",
            "Voici la requÃªte : SELECT COUNT(*) FROM orders",
            "SELECT COUNT(*) FROM orders;"
        ),
        (
            "Ajout LIMIT manquant",
            "SELECT * FROM orders WHERE order_status = 'delivered'",
            "LIMIT"  # on vÃ©rifie juste la prÃ©sence
        ),
        (
            "Pas de LIMIT sur COUNT global",
            "SELECT COUNT(*) AS nb FROM orders",
            None  # pas de LIMIT attendu
        ),
        (
            "Fix syntaxe date MySQL â PG",
            "SELECT YEAR(order_purchase_timestamp) FROM orders",
            "EXTRACT(YEAR FROM"
        ),
    ]

    passed = 0
    for name, input_sql, expected in cases:
        result = p.process(input_sql)
        if expected is None:
            ok = "LIMIT" not in result
        else:
            ok = expected in result
        status = "" if ok else ""
        print(f"  {status} {name}")
        if not ok:
            print(f"     EntrÃ©e  : {input_sql[:60]}")
            print(f"     RÃ©sultat: {result[:80]}")
            print(f"     Attendu : {expected}")
        else:
            passed += 1

    print(f"\n  RÃ©sultat: {passed}/{len(cases)} tests passÃ©s")
    return passed == len(cases)


# âââââââââââââââââââââââââââââââââââââââââââââ
#  Tests du Hallucination Detector
# âââââââââââââââââââââââââââââââââââââââââââââ

def test_hallucination_detector():
    separator("Tests du HallucinationDetector")
    d = HallucinationDetector()

    cases = [
        # (description, sql, expect_valid, expect_warning_contains)
        (
            "SELECT valide simple",
            "SELECT COUNT(*) FROM orders;",
            True, None
        ),
        (
            "SELECT avec jointure valide",
            "SELECT o.order_id, c.customer_city FROM orders o JOIN customers c ON o.customer_id = c.customer_id LIMIT 10;",
            True, None
        ),
        (
            "DROP TABLE interdit",
            "DROP TABLE orders;",
            False, None
        ),
        (
            "DELETE interdit",
            "DELETE FROM customers WHERE customer_id = '123';",
            False, None
        ),
        (
            "Table hallucinÃ©e",
            "SELECT * FROM order_details LIMIT 10;",
            True, "hallucinÃ©e"  # warning attendu
        ),
        (
            "Colonne typo courante",
            "SELECT product_name_length FROM products LIMIT 5;",
            True, "product_name_lenght"  # warning typo
        ),
        (
            "RequÃªte sans FROM valide (WITH)",
            "WITH t AS (SELECT 1) SELECT * FROM t;",
            True, None
        ),
        (
            "Double requÃªte (injection)",
            "SELECT 1; SELECT * FROM customers;",
            False, None
        ),
    ]

    passed = 0
    for name, sql, expect_valid, expect_warning in cases:
        result = d.validate(sql)
        valid_ok = result.is_valid == expect_valid
        warning_ok = (
            expect_warning is None
            or any(expect_warning.lower() in w.lower() for w in result.warnings)
        )
        ok = valid_ok and warning_ok
        status = "" if ok else ""
        print(f"  {status} {name}")
        if not ok:
            print(f"     SQL     : {sql[:60]}")
            print(f"     Valide  : {result.is_valid} (attendu: {expect_valid})")
            if result.issues:
                print(f"     Issues  : {result.issues}")
            if result.warnings:
                print(f"     Warnings: {result.warnings}")
        else:
            passed += 1

    print(f"\n  RÃ©sultat: {passed}/{len(cases)} tests passÃ©s")
    return passed == len(cases)


# âââââââââââââââââââââââââââââââââââââââââââââ
#  Tests de requÃªtes SQL representatifs Olist
# âââââââââââââââââââââââââââââââââââââââââââââ

OLIST_SQL_SAMPLES = {
    "CA total": """
        SELECT ROUND(SUM(payment_value), 2) AS chiffre_affaires_total
        FROM order_payments;
    """,
    "Top 5 vendeurs": """
        SELECT s.seller_id,
               s.seller_city,
               s.seller_state,
               ROUND(SUM(oi.price), 2) AS revenu_total,
               COUNT(DISTINCT oi.order_id) AS nb_commandes
        FROM order_items oi
        JOIN sellers s ON oi.seller_id = s.seller_id
        GROUP BY s.seller_id, s.seller_city, s.seller_state
        ORDER BY revenu_total DESC
        LIMIT 5;
    """,
    "Ãvolution mensuelle 2017": """
        SELECT TO_CHAR(order_purchase_timestamp, 'YYYY-MM') AS mois,
               COUNT(*) AS nb_commandes,
               ROUND(AVG(payment_value), 2) AS panier_moyen
        FROM orders o
        JOIN order_payments op ON o.order_id = op.order_id
        WHERE EXTRACT(YEAR FROM order_purchase_timestamp) = 2017
        GROUP BY mois
        ORDER BY mois;
    """,
    "Distribution notes": """
        SELECT review_score,
               COUNT(*) AS nombre_avis,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pourcentage
        FROM order_reviews
        GROUP BY review_score
        ORDER BY review_score;
    """,
    "DÃ©lai moyen livraison par Ã©tat": """
        SELECT c.customer_state,
               ROUND(AVG(
                   EXTRACT(DAY FROM (
                       o.order_delivered_customer_date - o.order_purchase_timestamp
                   ))
               ), 1) AS delai_moyen_jours,
               COUNT(*) AS nb_commandes
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        WHERE o.order_status = 'delivered'
          AND o.order_delivered_customer_date IS NOT NULL
        GROUP BY c.customer_state
        ORDER BY delai_moyen_jours DESC
        LIMIT 10;
    """,
}


def test_sql_samples():
    separator("Validation des requÃªtes SQL exemples Olist")
    d = HallucinationDetector()
    p = SQLPostProcessor()
    passed = 0

    for name, sql in OLIST_SQL_SAMPLES.items():
        processed = p.process(sql)
        validation = d.validate(processed)
        ok = validation.is_valid
        status = "" if ok else ""
        print(f"  {status} {name}")
        if validation.warnings:
            for w in validation.warnings:
                print(f"       {w}")
        if not ok:
            for issue in validation.issues:
                print(f"      {issue}")
        else:
            passed += 1

    print(f"\n  RÃ©sultat: {passed}/{len(OLIST_SQL_SAMPLES)} requÃªtes valides")
    return passed == len(OLIST_SQL_SAMPLES)


# âââââââââââââââââââââââââââââââââââââââââââââ
#  Main
# âââââââââââââââââââââââââââââââââââââââââââââ

if __name__ == "__main__":
    print("\nð¬ Suite de Tests â Moteur NLPâSQL Olist")
    print("=" * 60)

    results = []
    results.append(test_post_processor())
    results.append(test_hallucination_detector())
    results.append(test_sql_samples())

    separator("RÃ©sumÃ© Final")
    total = len(results)
    passed = sum(results)
    status = " TOUS LES TESTS PASSÃS" if passed == total else f" {total-passed} groupe(s) en Ã©chec"
    print(f"  {status} ({passed}/{total} groupes)")

    if passed == total:
        print("\n   Votre moteur NLPâSQL est prÃªt !")
        print("  DÃ©marrez l'interface avec : streamlit run app.py")
    else:
        print("\n  ð§ Corrigez les erreurs avant de lancer l'application.")

    sys.exit(0 if passed == total else 1)