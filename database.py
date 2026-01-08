import sqlite3

DB_NAME = "gestion_stock.db"

def get_db():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_db()
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

    # Table produits
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
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

    # Ajouter un admin par défaut
    cursor.execute("""
    INSERT OR IGNORE INTO user (username, password, ville)
    VALUES (?, ?, ?)
    """, ("admin", "admin123", "Paris"))

    conn.commit()
    conn.close()
