from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
import datetime, os
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(title="Gestion Stock API", docs_url="/docs", redoc_url="/redoc")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(SessionMiddleware, secret_key="ton_secret_ultra_long_et_imprevisible")

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if not password or len(password.encode("utf-8")) > 72:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Mot de passe invalide"})
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.verify_password(password):
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
def submit_product(request: Request, name: str = Form(...), quantity: float = Form(...), price: float = Form(...), db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    new_product = Product(name=name, quantity=quantity, total_quantity=quantity, price=price, username=request.session["user"], ville="Cotonou")
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return RedirectResponse(url="/products-page", status_code=303)

@app.get("/sales-page")
def sales_page(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    sales = db.query(Sale).order_by(Sale.date.desc()).all()
    products = db.query(Product).all()
    return templates.TemplateResponse("sales.html", {"request": request, "sales": sales, "products": products})

@app.get("/create-sale")
def create_sale_page(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    products = db.query(Product).all()
    return templates.TemplateResponse("create_sale.html", {"request": request, "products": products})


@app.post("/sales")
def create_sale(
    request: Request,
    product_id: int = Form(...),
    client_name: str = Form(...),
    quantity_sold: float = Form(...),
    invoice_id: int = Form(None),   # ✅ nouveau champ optionnel
    db: Session = Depends(get_db)
):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or product.quantity < quantity_sold:
        raise HTTPException(status_code=400, detail="Stock insuffisant")

    total_price = round(product.price * quantity_sold, 2)

    # ✅ Si invoice_id est fourni, on rattache la vente à cette facture
    if invoice_id:
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Facture introuvable")
    else:
        # Sinon, on crée une nouvelle facture
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
        invoice_id=invoice.id
    )
    db.add(new_sale)

    # Mise à jour du stock
    product.quantity -= quantity_sold
    db.commit()

    # ✅ Si on ajoute à une facture existante → redirige vers la facture
    if invoice_id:
        return RedirectResponse(url=f"/invoice/{invoice.id}", status_code=303)
    else:
        return RedirectResponse(url="/sales-page", status_code=303)


@app.get("/admin-dashboard")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    today = datetime.date.today()
    daily_sales = db.query(func.sum(Sale.total_price)).filter(func.date(Sale.date) == today).scalar() or 0
    products = db.query(Product).all()
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "daily_sales": daily_sales, "products": products})

@app.get("/reset-db")
def reset_db(request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    db.query(Sale).delete()
    db.query(Invoice).delete()
    db.query(Product).delete()
    db.commit()
    return {"message": "Toutes les ventes, factures et produits ont été réinitialisés."}

@app.get("/invoice/{invoice_id}")
def view_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    if "user" not in request.session:
        return RedirectResponse(url="/login", status_code=303)
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    sales = db.query(Sale).filter(Sale.invoice_id == invoice_id).all()
    total = sum(s.total_price for s in sales)
    return templates.TemplateResponse("invoice.html", {
        "request": request,
        "invoice": invoice,
        "sales": sales,
        "total": total
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
