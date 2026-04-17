import os
import uuid
import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI()

# --- CONFIGURATION DES BASES DE DONNÉES ---
# Render fournit 'DATABASE_URL'. Sur ton PC, on utilisera tes identifiants locaux.
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    if DATABASE_URL:
        # CONNEXION RENDER (EN LIGNE)
        return psycopg2.connect(DATABASE_URL, sslmode='require')
    else:
        # CONNEXION LOCALE (TON PC)
        # Remplace 'postgres' et 'ton_mot_de_passe' par tes vrais identifiants
        return psycopg2.connect(
            host="localhost",
            database="aura_db", 
            user="postgres",
            password="ton_mot_de_passe" 
        )

# --- INITIALISATION DE LA TABLE ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS certificates (
            id SERIAL PRIMARY KEY,
            cert_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            date TEXT NOT NULL
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- MODÈLES DE DONNÉES ---
class CertificateRequest(BaseModel):
    name: str
    type: str

# --- ROUTES API ---

@app.post("/certify")
async def create_certificate(req: CertificateRequest):
    cert_id = f"AURA-{uuid.uuid4().hex[:8].upper()}"
    date_str = datetime.datetime.now().strftime("%d/%m/%Y")
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO certificates (cert_id, name, type, date) VALUES (%s, %s, %s, %s)",
            (cert_id, req.name, req.type, date_str)
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"cert_id": cert_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/verify/{cert_id}")
async def verify_certificate(cert_id: str):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT name, type, date FROM certificates WHERE cert_id = %s", (cert_id,))
    cert = cur.fetchone()
    cur.close()
    conn.close()
    
    if cert:
        return {"valid": True, "details": cert}
    return {"valid": False}

# --- SERVIR LE FRONTEND ---
@app.get("/")
async def read_index():
    return FileResponse('index.html')

app.mount("/", StaticFiles(directory="."), name="static")