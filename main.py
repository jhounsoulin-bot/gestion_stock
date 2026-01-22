from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
import datetime
import pdfkit
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware

# -----------------------------
# Initialisation
# -----------------------------
app = FastAPI(title="Gestion Stock API")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ✅ Sessions
app.add_middleware(SessionMiddleware, secret_key="ton_secret_ultra_long_et_imprevisible")

# ✅ Connexion MySQL (remplace 1234 par ton vrai mot de passe)
DATABASE_URL = "mysql+mysqlconnector://gestion:jnNbWJmzUFvFUlzIOQRzgpfJuiVAnxhP@localhost/gestion_stock"
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -----------------------------
# Modèles
# -----------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="user")

    def verify_password(self, password: str):
        return pwd_context.verify(password, self.password_hash)

    def set_password(self, password: str):
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

# -----------------------------
# Création des tables
# -----------------------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

# -----------------------------
# Dépendance DB
# -----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------
# Authentification
# -----------------------------
@app.get("/")
def root():
    # Affiche directement le formulaire de connexion
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.verify_password(password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Identifiants invalides"})
    request.session["user"] = user.username
    return RedirectResponse(url="/sales-page", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# -----------------------------
# Initialisation admin (optionnel)
# -----------------------------
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


@app.post("/init-admin")
def init_admin(
    request: Request,
    username: str = Form("admin"),
    password: str = Form("admin123"),
    db: Session = Depends(get_db)
):
    # Crée un admin si aucun utilisateur n'existe
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return {"message": "Admin existe déjà"}
    user = User(username=username, role="admin")
    user.set_password(password)
    db.add(user)
    db.commit()
    return {"message": f"Admin '{username}' créé"}

# -----------------------------
# Produits
# -----------------------------
@app.get("/products-page")
def products_page(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    products = db.query(Product).all()
    return templates.TemplateResponse("products.html", {"request": request, "products": products})

@app.get("/add-product")
def add_product_page(request: Request):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("add_product.html", {"request": request})

@app.post("/add-product")
def submit_product(
    request: Request,
    name: str = Form(...),
    quantity: float = Form(...),
    price: float = Form(...),
    db: Session = Depends(get_db)
):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    new_product = Product(
        name=name,
        quantity=quantity,
        total_quantity=quantity,
        price=price,
        username=request.session["user"],
        ville="Cotonou"
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return RedirectResponse(url="/products-page", status_code=303)

@app.get("/restock/{product_id}")
def restock_page(request: Request, product_id: int, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    return templates.TemplateResponse("restock.html", {"request": request, "product": product})

@app.post("/restock/{product_id}")
def restock_product(
    request: Request,
    product_id: int,
    added_quantity: float = Form(...),
    new_price: float = Form(...),
    db: Session = Depends(get_db)
):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    product.quantity += added_quantity
    product.total_quantity += added_quantity
    product.price = new_price
    db.commit()
    db.refresh(product)
    return RedirectResponse(url="/products-page", status_code=303)

# -----------------------------
# Ventes (historique + ajout direct)
# -----------------------------
@app.get("/sales-page")
def sales_page(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    sales = db.query(Sale).order_by(Sale.date.desc()).all()
    products = db.query(Product).all()
    return templates.TemplateResponse("sales.html", {"request": request, "sales": sales, "products": products})

@app.post("/sales")
def create_sale(
    request: Request,
    product_id: int = Form(...),
    client_name: str = Form(...),
    quantity_sold: float = Form(...),
    db: Session = Depends(get_db)
):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    if product.quantity < quantity_sold:
        raise HTTPException(status_code=400, detail="Stock insuffisant")

    total_price = round(product.price * quantity_sold, 2)

    # Facture du jour pour ce client
    today = datetime.date.today()
    invoice = db.query(Invoice).filter(
        Invoice.client_name == client_name,
        func.date(Invoice.date) == today
    ).first()
    if not invoice:
        invoice = Invoice(client_name=client_name)
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

    new_sale = Sale(
        product_id=product_id,
        username=request.session["user"],
        client_name=client_name,
        quantity_sold=quantity_sold,
        total_price=total_price,
        date=datetime.datetime.utcnow(),
        invoice_id=invoice.id
    )
    db.add(new_sale)
    product.quantity -= quantity_sold
    db.commit()
    db.refresh(new_sale)

    return RedirectResponse(url="/sales-page", status_code=303)

# -----------------------------
# Facture multi-articles (panier par client)
# -----------------------------
@app.post("/start-invoice")
def start_invoice(
    request: Request,
    client_name: str = Form(...),
    db: Session = Depends(get_db)
):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    today = datetime.date.today()
    invoice = db.query(Invoice).filter(
        Invoice.client_name == client_name,
        func.date(Invoice.date) == today
    ).first()

    if not invoice:
        invoice = Invoice(client_name=client_name)
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

    products = db.query(Product).all()
    return templates.TemplateResponse("invoice.html", {
        "request": request,
        "invoice": invoice,
        "sales": invoice.sales,
        "products": products
    })

@app.post("/add-to-invoice/{invoice_id}")
def add_to_invoice(
    request: Request,
    invoice_id: int,
    product_id: int = Form(...),
    quantity_sold: float = Form(...),
    db: Session = Depends(get_db)
):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    product = db.query(Product).filter(Product.id == product_id).first()
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()

    if not product or not invoice:
        raise HTTPException(status_code=404, detail="Produit ou facture introuvable")
    if product.quantity < quantity_sold:
        raise HTTPException(status_code=400, detail="Stock insuffisant")

    total_price = round(product.price * quantity_sold, 2)

    new_sale = Sale(
        product_id=product_id,
        username=request.session["user"],
        client_name=invoice.client_name,
        quantity_sold=quantity_sold,
        total_price=total_price,
        date=datetime.datetime.utcnow(),
        invoice_id=invoice.id
    )
    db.add(new_sale)
    product.quantity -= quantity_sold
    db.commit()
    db.refresh(new_sale)

    products = db.query(Product).all()
    return templates.TemplateResponse("invoice.html", {
        "request": request,
        "invoice": invoice,
        "sales": invoice.sales,
        "products": products
    })

# -----------------------------
# Téléchargement facture PDF
# -----------------------------
@app.get("/download-invoice/{invoice_id}")
def download_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture introuvable")

    html_content = f"""
    <h2 style="text-align:center;">FACTURE NIVAL IMPACT</h2>
    <p><strong>Client :</strong> {invoice.client_name}</p>
    <p><strong>Date :</strong> {invoice.date}</p>
    <table border="1" cellspacing="0" cellpadding="5">
      <tr><th>Produit</th><th>Quantité</th><th>Prix unitaire</th><th>Total</th></tr>
    """
    total_general = 0
    for sale in invoice.sales:
        html_content += f"<tr><td>{sale.product.name}</td><td>{sale.quantity_sold}</td><td>{sale.product.price} FCFA</td><td>{sale.total_price} FCFA</td></tr>"
        total_general += sale.total_price

    html_content += f"<tr><td colspan='3'><strong>Total général</strong></td><td><strong>{total_general} FCFA</strong></td></tr></table>"

    path_wkhtmltopdf = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)

    pdf_file = f"facture_{invoice.id}.pdf"
    pdfkit.from_string(html_content, pdf_file, configuration=config)

    return FileResponse(pdf_file, filename=pdf_file, media_type="application/pdf")

# -----------------------------
# Admin Dashboard
# -----------------------------
@app.get("/admin-dashboard")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    today = datetime.date.today()
    start_week = today - datetime.timedelta(days=today.weekday())
    start_month = today.replace(day=1)

    # Totaux ventes
    daily_sales = db.query(func.sum(Sale.total_price)).filter(func.date(Sale.date) == today).scalar() or 0
    weekly_sales = db.query(func.sum(Sale.total_price)).filter(Sale.date >= start_week).scalar() or 0
    monthly_sales = db.query(func.sum(Sale.total_price)).filter(Sale.date >= start_month).scalar() or 0

    # Quantité vendue par produit
    sales_stats = db.query(
        Sale.product_id,
        func.sum(Sale.quantity_sold).label("sold")
    ).group_by(Sale.product_id).all()
    sold_map = {s.product_id: float(s.sold or 0) for s in sales_stats}

    # Tableau produits: initial / vendu / restant
    product_stats = []
    products = db.query(Product).all()
    for p in products:
        sold = sold_map.get(p.id, 0.0)
        remaining = float(p.quantity or 0.0)
        product_stats.append({
            "name": p.name,
            "initial": float(p.total_quantity or 0.0),
            "sold": sold,
            "remaining": remaining
        })

    # Top 3 plus et moins vendus
    top_3 = sorted(product_stats, key=lambda x: x["sold"], reverse=True)[:3]
    bottom_3 = sorted(product_stats, key=lambda x: x["sold"])[:3]

    # Alertes stock < 2
    alerts = [p for p in product_stats if p["remaining"] < 2]

    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "daily_sales": daily_sales,
        "weekly_sales": weekly_sales,
        "monthly_sales": monthly_sales,
        "product_stats": product_stats,
        "top_3": top_3,
        "bottom_3": bottom_3,
        "alerts": alerts
    })

# -----------------------------
# Reset complet
# -----------------------------
@app.get("/reset-db")
def reset_db(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    db.query(Sale).delete()
    db.query(Invoice).delete()
    db.query(Product).delete()
    db.commit()
    return {"message": "Toutes les ventes, factures et produits ont été réinitialisés."}
