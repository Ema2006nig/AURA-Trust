from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
import sqlite3
from datetime import datetime
import os

app = FastAPI()

# --- CONFIGURATION DE LA BASE DE DONNÉES ---
DB_NAME = "aura_database.db"

def init_db():
    """Crée la base de données et la table des certificats si elles n'existent pas."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS certificates (
            id TEXT PRIMARY KEY,
            entity_name TEXT,
            entity_type TEXT,
            issue_date TEXT,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

# On lance l'initialisation au démarrage
init_db()

# --- MODÈLES DE DONNÉES ---
class CertRequest(BaseModel):
    name: str
    type: str

# --- ROUTES (LES COMMANDES DU SERVEUR) ---

@app.get("/")
async def read_index():
    """Affiche votre site web. Assurez-vous que le fichier s'appelle bien index.html"""
    if os.path.exists("index.html"):
        return FileResponse('index.html')
    else:
        # Petit message d'erreur sympa si le fichier est mal nommé
        return {"error": "Fichier index.html introuvable. Vérifiez qu'il ne s'appelle pas index.html.html"}

@app.post("/certify")
async def certify_endpoint(request: CertRequest):
    """Génère un certificat unique et l'enregistre dans la base de données."""
    cert_id = f"AURA-{uuid.uuid4().hex[:8].upper()}"
    date_now = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO certificates (id, entity_name, entity_type, issue_date, status) VALUES (?, ?, ?, ?, ?)",
            (cert_id, request.name, request.type, date_now, "VERIFIED_ACTIVE")
        )
        conn.commit()
        conn.close()
        return {"cert_id": cert_id, "status": "SUCCESS", "date": date_now}
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

@app.get("/verify/{cert_id}")
async def verify_cert(cert_id: str):
    """Permet de vérifier si un certificat existe dans votre registre."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM certificates WHERE id = ?", (cert_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            "valid": True, 
            "details": {
                "id": result[0],
                "name": result[1],
                "type": result[2],
                "date": result[3],
                "status": result[4]
            }
        }
    return {"valid": False, "message": "Identifiant inconnu dans le registre AURA."}