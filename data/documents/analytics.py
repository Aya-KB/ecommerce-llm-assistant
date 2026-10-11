import pandas as pd

class AnalyticsEngine:

    def __init__(self, df_orders, df_items):
        self.orders = df_orders
        self.items = df_items

    def top_products(self, n=5):
        df = self.items.groupby("product_id")["price"].sum().reset_index()
        return df.sort_values("price", ascending=False).head(n)

    def top_sellers(self, n=5):
        df = self.items.groupby("seller_id")["price"].sum().reset_index()
        return df.sort_values("price", ascending=False).head(n)

    def revenue(self):
        return self.items["price"].sum()