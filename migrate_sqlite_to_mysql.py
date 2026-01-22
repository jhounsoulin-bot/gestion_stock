import sqlite3
import mysql.connector

# Connexion à la base SQLite
sqlite_conn = sqlite3.connect("gestion_stock.db")
sqlite_cursor = sqlite_conn.cursor()

# Connexion à la base MySQL
mysql_conn = mysql.connector.connect(
    host="localhost",
    user="root",                # ou ton utilisateur MySQL
    password="ton_mot_de_passe",# ⚠️ mets ton vrai mot de passe
    database="gestion_stock"
)
mysql_cursor = mysql_conn.cursor()

# Création des tables si elles n'existent pas
mysql_cursor.execute("""
CREATE TABLE IF NOT EXISTS user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    ville VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user'
)
""")

mysql_cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    quantity INT NOT NULL,
    total_quantity INT NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    username VARCHAR(255) NOT NULL,
    ville VARCHAR(255) NOT NULL
)
""")

mysql_cursor.execute("""
CREATE TABLE IF NOT EXISTS sales (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    username VARCHAR(255) NOT NULL,
    quantity_sold INT NOT NULL,
    total_price DECIMAL(10,2) NOT NULL,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id)
)
""")

# Migration des utilisateurs
sqlite_cursor.execute("SELECT * FROM user")
for row in sqlite_cursor.fetchall():
    mysql_cursor.execute(
        "INSERT INTO user (id, username, password, ville, role) VALUES (%s, %s, %s, %s, %s)",
        row
    )

# Migration des produits
sqlite_cursor.execute("SELECT * FROM products")
for row in sqlite_cursor.fetchall():
    mysql_cursor.execute(
        "INSERT INTO products (id, name, quantity, total_quantity, price, username, ville) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        row
    )

# Migration des ventes avec vérification des produits
sqlite_cursor.execute("SELECT * FROM sales")
for row in sqlite_cursor.fetchall():
    sale_id, product_id, username, qty_sold, total_price, date = row

    # Vérifier si le produit existe
    mysql_cursor.execute("SELECT id FROM products WHERE id = %s", (product_id,))
    if not mysql_cursor.fetchone():
        # Créer un produit placeholder
        mysql_cursor.execute(
            "INSERT INTO products (id, name, quantity, total_quantity, price, username, ville) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (product_id, f'Produit_{product_id}_placeholder', 0, 0, 0.00, username, 'Inconnu')
        )
        print(f"⚠️ Produit {product_id} manquant → créé automatiquement")

    # Insérer la vente
    mysql_cursor.execute(
        "INSERT INTO sales (id, product_id, username, quantity_sold, total_price, date) VALUES (%s, %s, %s, %s, %s, %s)",
        (sale_id, product_id, username, qty_sold, total_price, date)
    )

# Valider et fermer
mysql_conn.commit()
sqlite_conn.close()
mysql_conn.close()

print("✅ Migration terminée avec succès (avec gestion des produits manquants) !")
