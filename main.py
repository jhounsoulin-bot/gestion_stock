# main.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from typing import List
import sqlite3, io
from datetime import datetime, timedelta
from auth import verify_user
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="super-secret-key")
templates = Jinja2Templates(directory="templates")
DB_NAME = "gestion_stock.db"

# ---------------- DATABASE ----------------
def get_db():
    return sqlite3.connect(DB_NAME)

# ---------------- PDF FACTURE ----------------
def generate_invoice_pdf(client_name: str, items: list):
    buffer = io.BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>FACTURE</b>", styles["Title"]))
    elements.append(Paragraph(f"Client : {client_name}", styles["Normal"]))
    elements.append(Paragraph(f"Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    table_data = [["Produit", "Quantité", "Prix unitaire", "Total"]]
    total_general = 0
    for item in items:
        table_data.append([item["name"], str(item["quantity"]),
                           f'{item["price"]:.2f} FCFA',
                           f'{item["total"]:.2f} FCFA'])
        total_general += item["total"]

    table_data.append(["", "", "TOTAL", f"{total_general:.2f} FCFA"])
    table = Table(table_data, colWidths=[6*cm, 3*cm, 4*cm, 4*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightblue),
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (1,1), (-1,-1), "CENTER"),
        ("FONT", (-2,-1), (-1,-1), "Helvetica-Bold"),
        ("BACKGROUND", (-2,-1), (-1,-1), colors.lightgrey),
    ]))
    elements.append(table)
    pdf.build(elements)
    buffer.seek(0)
    return buffer

# ---------------- LOGIN ----------------
@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not verify_user(username, password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Identifiants incorrects"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM user WHERE username=?", (username,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Utilisateur introuvable"})
    request.session["user"] = username
    request.session["role"] = row[0]
    return RedirectResponse("/dashboard", status_code=303)

# ---------------- LOGOUT ----------------
@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

# ---------------- DASHBOARD ----------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    if "user" not in request.session:
        return RedirectResponse("/login", status_code=303)
    username = request.session["user"]
    role = request.session.get("role")
    conn = get_db()
    cursor = conn.cursor()

    if role == "admin":
        # Statistiques admin
        today = datetime.now().strftime("%Y-%m-%d")
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
        month_start = datetime.now().strftime("%Y-%m-01")

        cursor.execute("SELECT SUM(total_price) FROM sales WHERE DATE(date)=?", (today,))
        total_today = cursor.fetchone()[0] or 0
        cursor.execute("SELECT SUM(total_price) FROM sales WHERE DATE(date)>=?", (week_start,))
        total_week = cursor.fetchone()[0] or 0
        cursor.execute("SELECT SUM(total_price) FROM sales WHERE DATE(date)>=?", (month_start,))
        total_month = cursor.fetchone()[0] or 0

        cursor.execute("SELECT name, quantity FROM products WHERE quantity < 5")
        low_stock = cursor.fetchall()

        cursor.execute("""
            SELECT p.name, COALESCE(SUM(s.quantity_sold),0) AS total_sold
            FROM products p
            LEFT JOIN sales s ON s.product_id = p.id
            GROUP BY p.id
            ORDER BY total_sold DESC
            LIMIT 3
        """)
        top_sold = cursor.fetchall()

        cursor.execute("""
            SELECT p.name, COALESCE(SUM(s.quantity_sold),0) AS total_sold
            FROM products p
            LEFT JOIN sales s ON s.product_id = p.id
            GROUP BY p.id
            ORDER BY total_sold ASC
            LIMIT 3
        """)
        least_sold = cursor.fetchall()
        conn.close()
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "role": role,
            "username": username,
            "total_today": total_today,
            "total_week": total_week,
            "total_month": total_month,
            "low_stock": low_stock,
            "top_sold": top_sold,
            "least_sold": least_sold
        })
    else:
        # Dashboard utilisateur
        cursor.execute("SELECT id, name, quantity, total_quantity, price FROM products WHERE username=?", (username,))
        rows = cursor.fetchall()
        conn.close()
        products = [{"id": r[0], "name": r[1], "quantity": r[2], "total_quantity": r[3], "price": r[4]} for r in rows]
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "role": role,
            "username": username,
            "products": products
        })

# ---------------- ADD PRODUCT ----------------
@app.post("/add-product")
def add_product(request: Request,
                name: str = Form(...),
                quantity: int = Form(...),
                price: float = Form(...)):
    if "user" not in request.session:
        return RedirectResponse("/login", status_code=303)
    username = request.session["user"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT ville FROM user WHERE username=?", (username,))
    ville_row = cursor.fetchone()
    ville = ville_row[0] if ville_row else ""
    cursor.execute("INSERT INTO products (name, quantity, total_quantity, price, username, ville) VALUES (?, ?, ?, ?, ?, ?)",
                   (name, quantity, quantity, price, username, ville))
    conn.commit()
    conn.close()
    return RedirectResponse("/dashboard", status_code=303)

# ---------------- SALE ----------------
@app.post("/sale")
def sale_submit(request: Request,
                client_name: str = Form(...),
                product_ids: List[int] = Form(...),
                quantities: List[int] = Form(...)):
    if "user" not in request.session:
        return RedirectResponse("/login", status_code=303)
    username = request.session["user"]
    conn = get_db()
    cursor = conn.cursor()
    items = []
    for pid, qty in zip(product_ids, quantities):
        if qty <= 0:
            continue
        cursor.execute("SELECT name, quantity, price FROM products WHERE id=? AND username=?", (pid, username))
        product = cursor.fetchone()
        if not product:
            continue
        name, stock, price = product
        if qty > stock:
            conn.close()
            return HTMLResponse(f"<h2>Stock insuffisant pour {name}</h2>")
        total = qty * price
        cursor.execute("UPDATE products SET quantity = quantity - ? WHERE id=?", (qty, pid))
        cursor.execute("INSERT INTO sales (product_id, username, quantity_sold, total_price) VALUES (?, ?, ?, ?)",
                       (pid, username, qty, total))
        items.append({"name": name, "quantity": qty, "price": price, "total": total})
    conn.commit()
    conn.close()
    if not items:
        return HTMLResponse("<h2>Aucun produit sélectionné</h2>")
    pdf_buffer = generate_invoice_pdf(client_name, items)
    return StreamingResponse(pdf_buffer, media_type="application/pdf",
                             headers={"Content-Disposition": f"inline; filename=facture_{client_name}.pdf"})

# ---------------- RUN ----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
