import sqlite3

DB_NAME = "gestion_stock.db"
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Table utilisateurs
cursor.execute("""
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    ville TEXT NOT NULL
)
""")

# Table produits (AVEC total_quantity)
cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    total_quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    username TEXT NOT NULL,
    ville TEXT NOT NULL
)
""")

# Table ventes
cursor.execute("""
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    quantity_sold INTEGER NOT NULL,
    total_price REAL NOT NULL,
    date TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
)
""")

# Utilisateurs de test
cursor.execute("INSERT OR IGNORE INTO user VALUES (NULL, ?, ?, ?)", ("admin", "admin123", "Paris"))
cursor.execute("INSERT OR IGNORE INTO user VALUES (NULL, ?, ?, ?)", ("user2", "user2123", "Lyon"))

conn.commit()
conn.close()
print("✅ Base de données créée correctement")
