from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
import datetime, os, io
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = FastAPI(title="Gestion Stock API", docs_url="/docs", redoc_url="/redoc")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(SessionMiddleware, secret_key="ton_secret_ultra_long_et_imprevisible")

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Configuration Passlib avec Argon2

pwd_context = CryptContext(
    schemes=["argon2", "pbkdf2_sha256", "bcrypt"],  # accepte aussi bcrypt
    default="argon2",                               # nouvel algo par défaut
    deprecated="auto"
)

def verify_and_upgrade_password(password: str, user, db: Session) -> bool:
    try:
        # Vérifie le mot de passe avec le hash existant
        if pwd_context.verify(password, user.password_hash):
            # Si le hash n'est pas au format par défaut (argon2), on le met à jour
            if pwd_context.needs_update(user.password_hash):
                user.password_hash = pwd_context.hash(password)
                db.add(user)
                db.commit()
            return True
    except Exception:
        return False


def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="user")

    def verify_password(self, password: str):
        return pwd_context.verify(password, self.password_hash)

    def set_password(self, password: str):
        if not password:
            raise ValueError("Le mot de passe ne peut pas être vide")
        if len(password.encode("utf-8")) > 72:
            raise ValueError("Le mot de passe dépasse 72 caractères (limite bcrypt)")
        self.password_hash = pwd_context.hash(password)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    quantity = Column(Float, nullable=False)
    total_quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    username = Column(String(255), nullable=False)
    ville = Column(String(255), nullable=False)

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String(255), nullable=False)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    sales = relationship("Sale", backref="invoice")

class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    username = Column(String(255), nullable=False)
    client_name = Column(String(255), nullable=False)
    quantity_sold = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    product = relationship("Product", backref="sales")

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------ ROUTES ------------------

@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_and_upgrade_password(password, user, db):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Identifiants invalides"})
    request.session["user"] = user.username
    return RedirectResponse(url="/sales-page", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/init-admin")
def init_admin(db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == "admin").first()
    if existing:
        return {"message": "Admin existe déjà"}
    user = User(username="admin", role="admin")
    user.set_password("admin123")
    db.add(user)
    db.commit()
    return {"message": "Admin créé avec succès"}

# ------------------ PRODUCTS ------------------

@app.get("/products-page")
def products_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    # Si un terme de recherche est fourni, filtrer les produits
    if q:
        products = db.query(Product).filter(Product.name.ilike(f"%{q}%")).all()
    else:
        products = db.query(Product).order_by(Product.name.asc()).all()


    return templates.TemplateResponse("products.html", {
        "request": request,
        "products": products,
        "q": q
    })

@app.get("/add-product")
def add_product_page(request: Request):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("add_product.html", {"request": request})

@app.post("/add-product")
def submit_product(request: Request, name: str = Form(...), quantity: float = Form(...), price: float = Form(...), db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    new_product = Product(name=name, quantity=quantity, total_quantity=quantity, price=price, username=request.session["user"], ville="Cotonou")
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return RedirectResponse(url="/products-page", status_code=303)

# ------------------ SALES ------------------

@app.get("/sales-page")
def sales_page(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    sales = db.query(Sale).order_by(Sale.date.desc()).all()
    products = db.query(Product).order_by(Product.name.asc()).all()
    return templates.TemplateResponse("sales.html", {"request": request, "sales": sales, "products": products})

@app.get("/create-sale")
def create_sale_page(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    products = db.query(Product).order_by(Product.name.asc()).all()
    return templates.TemplateResponse("create_sale.html", {"request": request, "products": products})

@app.post("/sales")
def create_sale(request: Request, product_id: int = Form(...), client_name: str = Form(...), quantity_sold: float = Form(...), invoice_id: int = Form(None), db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or product.quantity < quantity_sold:
        raise HTTPException(status_code=400, detail="Stock insuffisant")

    total_price = round(product.price * quantity_sold, 2)

    if invoice_id:
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Facture introuvable")
    else:
        invoice = Invoice(client_name=client_name)
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

    new_sale = Sale(product_id=product_id, username=request.session["user"], client_name=client_name, quantity_sold=quantity_sold, total_price=total_price, invoice_id=invoice.id)
    db.add(new_sale)
    product.quantity -= quantity_sold
    db.commit()

    if invoice_id:
        return RedirectResponse(url=f"/invoice/{invoice.id}", status_code=303)
    else:
        return RedirectResponse(url="/sales-page", status_code=303)

# ------------------ ADMIN ------------------

@app.get("/admin-dashboard")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    today = datetime.date.today()

    # --- Ventes journalières ---
    daily_sales = db.query(func.sum(Sale.total_price))\
        .filter(func.date(Sale.date) == today).scalar() or 0

    # --- Ventes hebdomadaires ---
    start_week = today - datetime.timedelta(days=today.weekday())  # lundi
    weekly_sales = db.query(func.sum(Sale.total_price))\
        .filter(Sale.date >= start_week).scalar() or 0

    # --- Ventes mensuelles ---
    start_month = today.replace(day=1)
    monthly_sales = db.query(func.sum(Sale.total_price))\
        .filter(Sale.date >= start_month).scalar() or 0

    # --- Ventes par mois (janvier → décembre) ---
    monthly_totals = []
    for month in range(1, 13):
        start = datetime.date(today.year, month, 1)
        if month == 12:
            end = datetime.date(today.year + 1, 1, 1)
        else:
            end = datetime.date(today.year, month + 1, 1)

        total = db.query(func.sum(Sale.total_price))\
            .filter(Sale.date >= start, Sale.date < end).scalar() or 0

        monthly_totals.append({
            "month": start.strftime("%B"),  # Nom du mois (Janvier, Février…)
            "total": total
        })

    # --- Stats produits ---
    products = db.query(Product).all()
    product_stats = []
    for p in products:
        sold_qty = sum(s.quantity_sold for s in p.sales)
        remaining = p.quantity
        initial = p.total_quantity
        product_stats.append({
            "name": p.name,
            "initial": initial,
            "sold": sold_qty,
            "remaining": remaining
        })

    # --- Top 3 / Bottom 3 ---
    top_3 = sorted(product_stats, key=lambda x: x["sold"], reverse=True)[:3]
    bottom_3 = sorted(product_stats, key=lambda x: x["sold"])[:3]

    # --- Alertes stock faible ---
    alerts = [p for p in product_stats if p["remaining"] < 5]

    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "daily_sales": daily_sales,
        "weekly_sales": weekly_sales,
        "monthly_sales": monthly_sales,
        "product_stats": product_stats,
        "top_3": top_3,
        "bottom_3": bottom_3,
        "alerts": alerts,
        "monthly_totals": monthly_totals
    })

@app.get("/reset-db")
def reset_db(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    db.query(Sale).delete()
    db.query(Invoice).delete()
    db.query(Product).delete()
    db.commit()
    return {"message": "Toutes les ventes, factures et produits ont été réinitialisés."}


# ------------------ INVOICES ------------------

@app.get("/invoice/{invoice_id}")
def view_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture introuvable")

    sales = db.query(Sale).filter(Sale.invoice_id == invoice_id).all()
    total = sum(s.total_price for s in sales)

    products = db.query(Product).order_by(Product.name.asc()).all()

    return templates.TemplateResponse("invoice.html", {
        "request": request,
        "invoice": invoice,
        "sales": sales,
        "total": total,
        "products": products
    })


@app.get("/invoice-page")
def invoice_page(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    invoices = db.query(Invoice).order_by(Invoice.date.desc()).all()
    return templates.TemplateResponse("invoices.html", {"request": request, "invoices": invoices})

@app.post("/create-invoice")
def create_invoice(request: Request, client_name: str = Form(...), db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    invoice = Invoice(client_name=client_name)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return RedirectResponse(url=f"/invoice/{invoice.id}", status_code=303)

# ------------------ PDF GENERATION ------------------
@app.get("/invoice/{invoice_id}/pdf")
def download_invoice_pdf(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture introuvable")

    sales = db.query(Sale).filter(Sale.invoice_id == invoice_id).all()
    total = sum(s.total_price for s in sales)

    # Générer le PDF
    buffer = generate_invoice_pdf(invoice, sales, total)

    # Retourner le PDF en StreamingResponse
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=facture_{invoice.id}.pdf"}
    )


def generate_invoice_pdf(invoice, sales, total):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Titre
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, f"Facture #{invoice.id}")

    # Client
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, f"Client : {invoice.client_name}")
    c.drawString(50, height - 100, f"Date : {invoice.date.strftime('%d/%m/%Y')}")

    # Tableau des ventes
    y = height - 150
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Produit")
    c.drawString(250, y, "Quantité")
    c.drawString(350, y, "Prix total")

    c.setFont("Helvetica", 12)
    for sale in sales:
        y -= 20
        c.drawString(50, y, sale.product.name)
        c.drawString(250, y, str(sale.quantity_sold))
        c.drawString(350, y, f"{sale.total_price:.2f} FCFA")

    # Total
    y -= 40
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Total : {total:.2f} FCFA")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


# ------------------ REAPPROVISIONNEMENT ------------------

@app.get("/reapprovisionnement/{product_id}")
def reapprovisionnement_page(product_id: int, request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    return templates.TemplateResponse("reapprovisionnement.html", {"request": request, "product": product})

@app.post("/reapprovisionnement/{product_id}")
def reapprovisionnement(
    product_id: int,
    request: Request,
    added_quantity: float = Form(...),
    new_price: float = Form(...),
    db: Session = Depends(get_db)
):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")

    # ✅ Mise à jour du stock et du prix
    product.quantity += added_quantity
    product.total_quantity += added_quantity
    product.price = new_price

    db.commit()
    db.refresh(product)

    return RedirectResponse(url="/products-page", status_code=303)


