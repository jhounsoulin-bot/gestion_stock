
import sqlite3

DB_NAME = "gestion_stock.db"

def verify_user(username: str, password: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM user WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0] == password:
        return True
    return False

