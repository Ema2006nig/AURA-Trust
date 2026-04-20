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

# --- CONFIGURATION DES BASES DE DONNÉES ---
DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_DB = "backup_certificates.db"

def init_db():
    """Initialise les tables si elles n'existent pas"""
    # SQLite (Local)
    try:
        s_conn = sqlite3.connect(SQLITE_DB)
        s_conn.execute('''CREATE TABLE IF NOT EXISTS certificates 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, cert_id TEXT, name TEXT, type TEXT, date TEXT)''')
        s_conn.close()
    except Exception as e:
        print(f"Erreur SQLite: {e}")

    # PostgreSQL (Render)
    if DATABASE_URL:
        try:
            p_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            p_cur = p_conn.cursor()
            p_cur.execute('''CREATE TABLE IF NOT EXISTS certificates 
                            (id SERIAL PRIMARY KEY, cert_id TEXT UNIQUE, name TEXT, type TEXT, date TEXT)''')
            p_conn.commit()
            p_cur.close()
            p_conn.close()
        except Exception as e:
            print(f"Erreur Postgres: {e}")

init_db()

# --- LOGIQUE DE SAUVEGARDE ---
def save_certificate(cert_id, name, cert_type, date):
    # Sauvegarde SQLite
    try:
        s_conn = sqlite3.connect(SQLITE_DB)
        s_conn.execute("INSERT INTO certificates (cert_id, name, type, date) VALUES (?, ?, ?, ?)",
                       (cert_id, name, cert_type, date))
        s_conn.commit()
        s_conn.close()
    except: pass

    # Sauvegarde PostgreSQL
    if DATABASE_URL:
        try:
            p_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            p_cur = p_conn.cursor()
            p_cur.execute("INSERT INTO certificates (cert_id, name, type, date) VALUES (%s, %s, %s, %s)",
                          (cert_id, name, cert_type, date))
            p_conn.commit()
            p_cur.close()
            p_conn.close()
        except: pass

def get_cert_from_db(cert_id):
    """Cherche un certificat dans les bases"""
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
    
    # Fallback sur SQLite si Postgres échoue
    s_conn = sqlite3.connect(SQLITE_DB)
    res = s_conn.execute("SELECT name, type, date FROM certificates WHERE cert_id = ?", (cert_id,)).fetchone()
    s_conn.close()
    return res

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/generate", response_class=HTMLResponse)
async def generate(request: Request, name: str = Form(...), cert_type: str = Form(...)):
    cert_id = f"AURA-{os.urandom(3).hex().upper()}"
    date_str = datetime.now().strftime("%d/%m/%Y")
    
    save_certificate(cert_id, name, cert_type, date_str)
    
    return templates.TemplateResponse("result.html", {
        "request": request, 
        "cert_id": cert_id, 
        "name": name, 
        "date": date_str
    })

@app.get("/download/{cert_id}")
async def download_pdf(cert_id: str):
    data = get_cert_from_db(cert_id)
    if not data:
        return Response(content="Certificat non trouvé", status_code=404)
    
    name, cert_type, date = data
    
    # Création du PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Design
    p.setStrokeColorRGB(0.1, 0.4, 0.8)
    p.rect(30, 30, width-60, height-60, stroke=1)
    p.setFont("Helvetica-Bold", 35)
    p.drawCentredString(width/2, height-120, "AURA TRUST")
    p.setFont("Helvetica", 20)
    p.drawCentredString(width/2, height-170, "CERTIFICAT D'INTÉGRITÉ")
    
    p.setFont("Helvetica", 16)
    p.drawCentredString(width/2, height-280, "Ce document est délivré à :")
    p.setFont("Helvetica-Bold", 26)
    p.drawCentredString(width/2, height-330, name.upper())
    
    p.setFont("Helvetica", 14)
    p.drawCentredString(width/2, height-400, f"Pour le motif de : {cert_type}")
    p.drawString(100, 150, f"Date : {date}")
    p.drawString(100, 130, f"ID de vérification : {cert_id}")

    # QR Code
    qr_url = f"https://aura-trust.onrender.com/verify/{cert_id}"
    qr = qrcode.make(qr_url)
    qr_buffer = BytesIO()
    qr.save(qr_buffer, format='PNG')
    qr_buffer.seek(0)
    p.drawImage(ImageReader(qr_buffer), width-180, 80, width=120, height=120)
    p.setFont("Helvetica", 8)
    p.drawRightString(width-70, 70, "Scannez pour vérifier l'authenticité")

    p.showPage()
    p.save()
    buffer.seek(0)
    
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Certificat_AURA_{cert_id}.pdf"}
    )