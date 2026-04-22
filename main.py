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
templates = Jinja2Templates(directory="templates")

# --- CONFIGURATION ---
ADMIN_PASSWORD = "mybilloniaword2006$$"  # <--- MODIFIE CECI
DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_DB = "backup_certificates.db"

def init_db():
    try:
        s_conn = sqlite3.connect(SQLITE_DB)
        s_conn.execute('''CREATE TABLE IF NOT EXISTS certificates 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, cert_id TEXT UNIQUE, name TEXT, type TEXT, date TEXT)''')
        s_conn.close()
        if DATABASE_URL:
            p_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            p_cur = p_conn.cursor()
            p_cur.execute('''CREATE TABLE IF NOT EXISTS certificates 
                            (id SERIAL PRIMARY KEY, cert_id TEXT UNIQUE, name TEXT, type TEXT, date TEXT)''')
            p_conn.commit()
            p_cur.close()
            p_conn.close()
    except Exception as e:
        print(f"Init DB Error: {e}")

init_db()

# --- FONCTIONS UTILES ---
def save_certificate(cert_id, name, cert_type, date):
    try:
        s_conn = sqlite3.connect(SQLITE_DB)
        s_conn.execute("INSERT INTO certificates (cert_id, name, type, date) VALUES (?, ?, ?, ?)", (cert_id, name, cert_type, date))
        s_conn.commit()
        s_conn.close()
        if DATABASE_URL:
            p_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            p_cur = p_conn.cursor()
            p_cur.execute("INSERT INTO certificates (cert_id, name, type, date) VALUES (%s, %s, %s, %s)", (cert_id, name, cert_type, date))
            p_conn.commit()
            p_cur.close()
            p_conn.close()
    except: pass

def get_cert(cert_id):
    try:
        s_conn = sqlite3.connect(SQLITE_DB)
        res = s_conn.execute("SELECT name, type, date FROM certificates WHERE cert_id = ?", (cert_id,)).fetchone()
        s_conn.close()
        return res
    except: return None

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/generate", response_class=HTMLResponse)
async def generate(request: Request, name: str = Form(...), cert_type: str = Form(...), password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        return HTMLResponse(content="<h2 style='color:red;text-align:center;'>❌ Mot de passe incorrect. Accès refusé.</h2>", status_code=403)
    
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
    if not data: return Response(status_code=404)
    name, cert_type, date = data
    
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setStrokeColorRGB(0.1, 0.4, 0.8)
    p.rect(30, 30, 535, 782, stroke=1)
    p.setFont("Helvetica-Bold", 30)
    p.drawCentredString(297, 750, "AURA TRUST")
    p.setFont("Helvetica-Bold", 20)
    p.drawCentredString(297, 500, name.upper())
    p.setFont("Helvetica", 12)
    p.drawCentredString(297, 450, f"ID: {cert_id} | Date: {date}")
    
    qr = qrcode.make(f"https://aura-trust.onrender.com/verify/{cert_id}")
    qr_b = BytesIO()
    qr.save(qr_b, format='PNG')
    qr_b.seek(0)
    p.drawImage(ImageReader(qr_b), 400, 50, width=120, height=120)
    p.save()
    buffer.seek(0)
    return Response(content=buffer.getvalue(), media_type="application/pdf")