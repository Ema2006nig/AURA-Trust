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

# --- CORRECTION CRUCIALE POUR RENDER ---
# On force le chemin absolu vers le dossier templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates_path = os.path.join(BASE_DIR, "templates")

# Sécurité : On s'assure que le dossier existe
if not os.path.exists(templates_path):
    os.makedirs(templates_path, exist_ok=True)

templates = Jinja2Templates(directory=templates_path)

# --- CONFIGURATION ---
ADMIN_PASSWORD = "mybilloniaword2006$$" # Change-le ici !
DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_DB = os.path.join(BASE_DIR, "backup_certificates.db")

def init_db():
    try:
        s_conn = sqlite3.connect(SQLITE_DB)
        s_conn.execute('''CREATE TABLE IF NOT EXISTS certificates 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, cert_id TEXT UNIQUE, name TEXT, type TEXT, date TEXT)''')
        s_conn.commit()
        s_conn.close()
    except Exception as e:
        print(f"Erreur DB: {e}")

init_db()

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Si cette ligne cause l'erreur 500, c'est que index.html n'est pas dans /templates
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/generate", response_class=HTMLResponse)
async def generate(request: Request, name: str = Form(...), cert_type: str = Form(...), password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        return HTMLResponse(content="<h2 style='color:red;'>Accès refusé</h2>", status_code=403)
    
    cert_id = f"AURA-{os.urandom(3).hex().upper()}"
    date_str = datetime.now().strftime("%d/%m/%Y")
    
    # Sauvegarde simplifiée pour le test
    conn = sqlite3.connect(SQLITE_DB)
    conn.execute("INSERT INTO certificates (cert_id, name, type, date) VALUES (?, ?, ?, ?)", (cert_id, name, cert_type, date_str))
    conn.commit()
    conn.close()
    
    return templates.TemplateResponse("result.html", {"request": request, "cert_id": cert_id, "name": name})

@app.get("/verify/{cert_id}", response_class=HTMLResponse)
async def verify(request: Request, cert_id: str):
    conn = sqlite3.connect(SQLITE_DB)
    data = conn.execute("SELECT name, type, date FROM certificates WHERE cert_id = ?", (cert_id,)).fetchone()
    conn.close()
    return templates.TemplateResponse("verify.html", {"request": request, "cert_id": cert_id, "data": data})

@app.get("/download/{cert_id}")
async def download(cert_id: str):
    conn = sqlite3.connect(SQLITE_DB)
    data = conn.execute("SELECT name, type, date FROM certificates WHERE cert_id = ?", (cert_id,)).fetchone()
    conn.close()
    
    if not data: return Response(status_code=404)
    
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.drawString(100, 700, f"CERTIFICAT AURA TRUST - {data[0]}")
    p.drawString(100, 680, f"Type: {data[1]} | Date: {data[2]}")
    
    qr = qrcode.make(f"https://aura-trust.onrender.com/verify/{cert_id}")
    qr_b = BytesIO()
    qr.save(qr_b, format='PNG')
    qr_b.seek(0)
    p.drawImage(ImageReader(qr_b), 400, 50, width=100, height=100)
    
    p.save()
    buffer.seek(0)
    return Response(content=buffer.getvalue(), media_type="application/pdf")