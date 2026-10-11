import sys
import os
sys.path.append('.')

import pandas as pd
from src.db.connexion import get_engine

from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest

DATA_PATH = "data/raw/"


# =========================
# LOAD DATA
# =========================
def load_data():
    print("Chargement des fichiers CSV...")

    orders    = pd.read_csv(DATA_PATH + "olist_orders_dataset.csv")
    items     = pd.read_csv(DATA_PATH + "olist_order_items_dataset.csv")
    customers = pd.read_csv(DATA_PATH + "olist_customers_dataset.csv")
    products  = pd.read_csv(DATA_PATH + "olist_products_dataset.csv")
    sellers   = pd.read_csv(DATA_PATH + "olist_sellers_dataset.csv")
    payments  = pd.read_csv(DATA_PATH + "olist_order_payments_dataset.csv")
    reviews   = pd.read_csv(DATA_PATH + "olist_order_reviews_dataset.csv")
    cats      = pd.read_csv(DATA_PATH + "product_category_name_translation.csv")

    print("Fichiers chargés")
    return orders, items, customers, products, sellers, payments, reviews, cats


# =========================
# FEATURE ENGINEERING
# =========================
def feature_engineering(orders):
    orders['delivery_delay'] = (
        orders['order_delivered_customer_date'] -
        orders['order_estimated_delivery_date']
    ).dt.days

    orders['is_late'] = (orders['delivery_delay'] > 0).astype(int)

    orders['processing_time'] = (
        orders['order_approved_at'] -
        orders['order_purchase_timestamp']
    ).dt.days

    return orders


# =========================
# OUTLIERS (Isolation Forest)
# =========================
def remove_outliers_iforest(df, columns):
    df_clean = df.copy()

    model = IsolationForest(
        contamination=0.02,
        random_state=42
    )

    if len(columns) > 0:
        preds = model.fit_predict(df_clean[columns])
        df_clean = df_clean[preds == 1]

    return df_clean


# =========================
# STANDARDISATION
# =========================
def standardize_columns(df, columns):
    scaler = StandardScaler()
    df = df.copy()
    df[columns] = scaler.fit_transform(df[columns])
    return df
#Cette fonction transforme les colonnes numériques pour qu’elles soient toutes sur la même échelle (moyenne 0, variance 1).
#rendre les variabl mm echel
# =========================
# CLEAN DATA
# =========================
def clean_data(orders, products, cats):
    print("Nettoyage avancé en cours...")

    # ---- Dates ----
    date_cols = [
        'order_purchase_timestamp',
        'order_approved_at',
        'order_delivered_carrier_date',
        'order_delivered_customer_date',
        'order_estimated_delivery_date'
    ]

    for col in date_cols:
        orders[col] = pd.to_datetime(orders[col], errors='coerce')

    orders = orders.dropna(subset=['order_purchase_timestamp'])

    # ---- Feature engineering ----
    orders = feature_engineering(orders)

    # ---- Merge catégories ----
    products = products.merge(cats, on='product_category_name', how='left')

    # ---- Missing values ----
    dim_cols = [
        'product_weight_g',
        'product_length_cm',
        'product_height_cm',
        'product_width_cm'
    ]

    for col in dim_cols:
        products[col] = products[col].fillna(products[col].median())

    products['product_category_name_english'] = (
        products['product_category_name_english']
        .fillna('unknown')
        .str.replace('_', ' ')
        .str.strip()
    )

    # =========================
    # OUTLIERS DETECTION
    # =========================
    products = remove_outliers_iforest(products, dim_cols)

    orders = remove_outliers_iforest(
        orders,
        ['delivery_delay', 'processing_time']
    )

    # =========================
    # STANDARDISATION
    # =========================
    products = standardize_columns(products, dim_cols)

    orders = standardize_columns(
        orders,
        ['delivery_delay', 'processing_time']
    )

    print("Nettoyage terminé")
    return orders, products


# =========================
# SAVE TO DB
# =========================
def save_to_db(orders, items, customers, products, sellers, payments, reviews):
    engine = get_engine()

    print("Chargement customers...")
    customers.to_sql('customers', engine, if_exists='replace', index=False)

    print("Chargement orders...")
    orders.to_sql('orders', engine, if_exists='replace', index=False, chunksize=5000)

    print("Chargement products...")
    products.to_sql('products', engine, if_exists='replace', index=False)

    print("Chargement sellers...")
    sellers.to_sql('sellers', engine, if_exists='replace', index=False)

    print("Chargement order_items...")
    items.to_sql('order_items', engine, if_exists='replace', index=False, chunksize=5000)

    print("Chargement payments...")
    payments.to_sql('payments', engine, if_exists='replace', index=False)

    print("Chargement reviews...")
    reviews.to_sql('reviews', engine, if_exists='replace', index=False, chunksize=5000)

    print("Base de données remplie avec succès")


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    orders, items, customers, products, sellers, payments, reviews, cats = load_data()
    orders, products = clean_data(orders, products, cats)
    save_to_db(orders, items, customers, products, sellers, payments, reviews)