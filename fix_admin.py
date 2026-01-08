# fix_admin.py
import sqlite3

DB_NAME = "gestion_stock.db"

def fix_admin_roles():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Vérifie les comptes admin
    cursor.execute("SELECT id, username, role FROM user")
    users = cursor.fetchall()
    print("Avant correction :")
    for u in users:
        print(u)
    
    # Mets à jour le rôle de l'utilisateur admin
    cursor.execute("UPDATE user SET role='admin' WHERE username='admin'")
    conn.commit()
    
    print("\nAprès correction :")
    cursor.execute("SELECT id, username, role FROM user")
    users = cursor.fetchall()
    for u in users:
        print(u)
    
    conn.close()
    print("\nRôle admin corrigé !")

if __name__ == "__main__":
    fix_admin_roles()
