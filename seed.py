"""Génère une base de démonstration réaliste (ventes B2B, MAD) : python seed.py"""
import os
import random
import sqlite3
from datetime import date

SEASON = [0.85, 0.85, 0.95, 1.0, 1.0, 0.95, 0.8, 0.75, 1.05, 1.1, 1.2, 1.3]
PRODUCTS = [  # nom, catégorie, prix, coût, poids de vente
    ("Laptop Pro 15", "Informatique", 9500, 7200, 3), ("Laptop Essentiel", "Informatique", 5200, 4100, 5),
    ("Écran 27 pouces", "Informatique", 2100, 1500, 6), ("Imprimante laser", "Informatique", 2800, 2100, 3),
    ("Bureau ergonomique", "Mobilier", 3200, 2000, 2), ("Fauteuil de direction", "Mobilier", 2400, 1500, 2),
    ("Armoire de rangement", "Mobilier", 1800, 1200, 2), ("Ramette papier A4", "Fournitures", 45, 32, 10),
    ("Stylos (boîte de 50)", "Fournitures", 90, 55, 8), ("Cartouches d'encre", "Fournitures", 420, 310, 6),
    ("Licence bureautique", "Services", 1200, 300, 4), ("Contrat maintenance", "Services", 3500, 1400, 2),
]
DRIFT = {"Informatique": 0.020, "Mobilier": 0.004, "Fournitures": -0.012, "Services": 0.015}
REGIONS = ["Casablanca", "Rabat", "Marrakech", "Tanger", "Oujda", "Fès"]
SEGMENTS = ["PME", "Grand compte", "Particulier"]
CHANNELS = ["En ligne", "Magasin", "Commercial"]


def build(path="data/demo.db", start=(2024, 1), months=34, seed=42):
    rnd = random.Random(seed)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, segment TEXT, region TEXT);
    CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT, category TEXT, unit_price REAL, cost REAL);
    CREATE TABLE orders(id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TEXT, channel TEXT);
    CREATE TABLE order_items(id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER,
                             quantity INTEGER, discount REAL);
    """)
    customers = [(i + 1, f"Client {i + 1:03d}", rnd.choices(SEGMENTS, [5, 2, 3])[0], rnd.choice(REGIONS))
                 for i in range(150)]
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?)", customers)
    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?)",
                     [(i + 1, p[0], p[1], p[2], p[3]) for i, p in enumerate(PRODUCTS)])
    cust_w = [1 / (i + 1) ** 0.7 for i in range(150)]
    oid = iid = 0
    for t in range(months):
        y, m = start[0] + (start[1] - 1 + t) // 12, (start[1] - 1 + t) % 12 + 1
        n_orders = int(60 * (1 + 0.012 * t) * SEASON[m - 1] * rnd.uniform(0.9, 1.1))
        weights = [p[4] * max(0.05, 1 + DRIFT[p[1]] * t) for p in PRODUCTS]
        for _ in range(n_orders):
            oid += 1
            cust = rnd.choices(customers, cust_w)[0]
            conn.execute("INSERT INTO orders VALUES (?,?,?,?)",
                         (oid, cust[0], date(y, m, rnd.randint(1, 28)).isoformat(), rnd.choice(CHANNELS)))
            for pid in set(rnd.choices(range(1, len(PRODUCTS) + 1), weights, k=rnd.randint(1, 4))):
                iid += 1
                disc = 0.10 if cust[2] == "Grand compte" else rnd.choice([0, 0, 0.05, 0.1])
                conn.execute("INSERT INTO order_items VALUES (?,?,?,?,?)",
                             (iid, oid, pid, rnd.randint(1, 5), disc))
    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("customers", "products", "orders", "order_items")}
    conn.close()
    return counts


if __name__ == "__main__":
    print("Base créée :", build())
