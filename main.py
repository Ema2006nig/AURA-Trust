import os
import sqlite3
import psycopg2
import qrcode
from datetime import datetime
from io import BytesIO
from fastapi import FastAPI, Form, Request, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

app = FastAPI()

# --- SÉCURITÉ ANTI-CRASH DOSSIER ---
# Si le dossier templates n'existe pas, on le crée pour éviter l'erreur Status 1
if not os.path.exists("templates"):
    print("⚠️ Dossier 'templates' introuvable. Création automatique...")
    os.makedirs("templates", exist_ok=True)

templates = Jinja2Templates(directory="templates")

# --- CONFIGURATION SÉCURISÉE ---
ADMIN_PASSWORD = "mybilloniaword2006$$"  # <--- METS TON MOT DE PASSE ICI
DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_DB = "backup_certificates.db"

def init_db():
    # 1. SQLite (Toujours actif pour éviter les plantages)
    try:
        s_conn = sqlite3.connect(SQLITE_DB)
        s_conn.execute('''CREATE TABLE IF NOT EXISTS certificates 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, cert_id TEXT UNIQUE, name TEXT, type TEXT, date TEXT)''')
        s_conn.commit()
        s_conn.close()
        print("✅ Base de données locale (SQLite) prête.")
    except Exception as e:
        print(f"❌ Erreur SQLite : {e}")

    # 2. PostgreSQL (Sur Render)
    if DATABASE_URL:
        try:
            p_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            p_cur = p_conn.cursor()
            p_cur.execute('''CREATE TABLE IF NOT EXISTS certificates 
                            (id SERIAL PRIMARY KEY, cert_id TEXT UNIQUE, name TEXT, type TEXT, date TEXT)''')
            p_conn.commit()
            p_cur.close()
            p_conn.close()
            print("✅ Base de données principale (PostgreSQL) prête.")
        except Exception as e:
            print(f"⚠️ Alerte : PostgreSQL injoignable. Le site utilisera SQLite. Erreur: {e}")

# Lancer la vérification des bases de données au démarrage
init_db()

def save_certificate(cert_id, name, cert_type, date):
    # Sauvegarde dans SQLite (Secours)
    try:
        s_conn = sqlite3.connect(SQLITE_DB)
        s_conn.execute("INSERT INTO certificates (cert_id, name, type, date) VALUES (?, ?, ?, ?)", (cert_id, name, cert_type, date))
        s_conn.commit()
        s_conn.close()
    except: pass
    
    # Sauvegarde dans PostgreSQL (Principal)
    if DATABASE_URL:
        try:
            p_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            p_cur = p_conn.cursor()
            p_cur.execute("INSERT INTO certificates (cert_id, name, type, date) VALUES (%s, %s, %s, %s)", (cert_id, name, cert_type, date))
            p_conn.commit()
            p_cur.close()
            p_conn.close()
        except: pass

def get_cert(cert_id):
    # On cherche d'abord dans PostgreSQL
    if DATABASE_URL:
        try:
            p_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            p_cur = p_conn.cursor()
            p_cur.execute("SELECT name, type, date FROM certificates WHERE cert_id = %s", (cert_id,))
            res = p_cur.fetchone()
            p_cur.close()
            p_conn.close()
            if res: return res
        except: pass
            
    # Si échec, on cherche dans SQLite
    try:
        s_conn = sqlite3.connect(SQLITE_DB)
        res = s_conn.execute("SELECT name, type, date FROM certificates WHERE cert_id = ?", (cert_id,)).fetchone()
        s_conn.close()
        return res
    except: return None

# --- ROUTES DU SITE ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/generate", response_class=HTMLResponse)
async def generate(request: Request, name: str = Form(...), cert_type: str = Form(...), password: str = Form(...)):
    # Vérification du mot de passe
    if password != ADMIN_PASSWORD:
        return HTMLResponse(content="<h2 style='color:red;text-align:center;'>❌ Accès refusé : Mot de passe incorrect.</h2>", status_code=403)
    
    # Création du certificat
    cert_id = f"AURA-{os.urandom(3).hex().upper()}"
    date_str = datetime.now().strftime("%d/%m/%Y")
    save_certificate(cert_id, name, cert_type, date_str)
    
    return templates.TemplateResponse("result.html", {"request": request, "cert_id": cert_id, "name": name})

@app.get("/verify/{cert_id}", response_class=HTMLResponse)
async def verify(request: Request, cert_id: str):
    data = get_cert(cert_id)
    return templates.TemplateResponse("verify.html", {"request": request, "cert_id": cert_id, "data": data})

@app.get("/download/{cert_id}")
async def download(cert_id: str):
    data = get_cert(cert_id)
    if not data:
        return Response(status_code=404, content="Erreur 404 : Ce certificat n'existe pas.")
    
    name, cert_type, date = data
    
    # Création du PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setStrokeColorRGB(0.1, 0.4, 0.8)
    p.rect(30, 30, 535, 782, stroke=1)
    
    p.setFont("Helvetica-Bold", 30)
    p.drawCentredString(297, 750, "AURA TRUST")
    
    p.setFont("Helvetica-Bold", 20)
    p.drawCentredString(297, 500, name.upper())
    
    p.setFont("Helvetica", 16)
    p.drawCentredString(297, 470, cert_type)
    
    p.setFont("Helvetica", 12)
    p.drawCentredString(297, 430, f"ID: {cert_id} | Délivré le: {date}")
    
    # Ajout du QR Code qui pointe vers la page de vérification
    qr = qrcode.make(f"https://aura-trust.onrender.com/verify/{cert_id}")
    qr_b = BytesIO()
    qr.save(qr_b, format='PNG')
    qr_b.seek(0)
    p.drawImage(ImageReader(qr_b), 400, 50, width=120, height=120)
    
    p.save()
    buffer.seek(0)
    
    return Response(content=buffer.getvalue(), media_type="application/pdf")