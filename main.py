"""Convite Dulce Marcos — website e registo de presenças.

Arranque: uvicorn main:app --host 0.0.0.0 --port 8000
Os dados são guardados em SQLite. Para hospedagem persistente, configurar DATABASE_PATH
num volume persistente. A integração WhatsApp Business Cloud API é opcional e requer
credenciais oficiais e um template aprovado.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

load_dotenv()
BASE = Path(__file__).resolve().parent
STATIC = BASE / "static" if (BASE / "static" / "index.html").exists() else BASE
DB_PATH = Path(os.environ.get("DATABASE_PATH", str(BASE / "data" / "rsvps.sqlite3")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
WA_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WA_SENDER = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WA_TEMPLATE = os.getenv("WHATSAPP_TEMPLATE_NAME", "")
WA_LANG = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "pt_PT")
WA_TO = re.sub(r"\D", "", os.getenv("WHATSAPP_TO", ""))
META_API_VERSION = os.getenv("WHATSAPP_GRAPH_VERSION", "v27.0")
WHATSAPP_READY = all((WA_TOKEN, WA_SENDER, WA_TEMPLATE, WA_TO))
ADMIN_READY = bool(ADMIN_PASSWORD and len(SESSION_SECRET) >= 32 and "SUBSTITUIR" not in ADMIN_PASSWORD.upper() and "SUBSTITUIR" not in SESSION_SECRET.upper())
MZ_TZ = ZoneInfo("Africa/Maputo")

app = FastAPI(title="Dulce Marcos · 50 anos", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/assets", StaticFiles(directory=STATIC / "assets" if (STATIC / "assets").exists() else STATIC), name="assets")

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/admin"):
        response.headers["Cache-Control"] = "no-store"
    return response

_lock = threading.Lock()
_rate = {}


def db():
    conn = sqlite3.connect(str(DB_PATH), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


with db() as conn:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS rsvps (
        id TEXT PRIMARY KEY, guest_token_hash TEXT NOT NULL UNIQUE,
        guest_name TEXT NOT NULL, attending TEXT NOT NULL CHECK(attending IN ('sim','nao')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        notification_state TEXT NOT NULL DEFAULT 'pendente',
        notification_error TEXT NOT NULL DEFAULT '',
        notification_attempts INTEGER NOT NULL DEFAULT 0,
        notification_sent_at TEXT
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS rsvp_sort ON rsvps(updated_at DESC)")
    conn.commit()


def rate_limit(request: Request, key: str, limit: int, window: int):
    # Defesa básica para implantação de instância única. Em produção multi-instância,
    # migrar os contadores para um serviço partilhado (p. ex. Redis).
    ip = request.client.host if request.client else "unknown"
    ident = f"{key}:{ip}"
    now = time.monotonic()
    with _lock:
        items = [v for v in _rate.get(ident, []) if v > now - window]
        if len(items) >= limit:
            raise HTTPException(429, detail="Demasiadas tentativas. Volte a tentar dentro de alguns minutos.")
        items.append(now)
        _rate[ident] = items
        if len(_rate) > 20000:
            for k in list(_rate)[:10000]:
                if all(v < now - window for v in _rate[k]):
                    _rate.pop(k, None)


class RSVP(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    attending: str
    guest_token: str
    contact_site: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        v = re.sub(r"\s+", " ", v.strip())
        if len(v) < 3 or not any(c.isalpha() for c in v):
            raise ValueError("Indique um nome válido")
        if not re.fullmatch(r"[\w\sÀ-ÿ'’.,-]+", v, flags=re.UNICODE):
            raise ValueError("O nome contém caracteres não permitidos")
        return v

    @field_validator("attending")
    @classmethod
    def validate_attendance(cls, v):
        if v not in {"sim", "nao"}:
            raise ValueError("Resposta inválida")
        return v

    @field_validator("guest_token")
    @classmethod
    def validate_token(cls, v):
        if len(v) > 128 or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", v):
            raise ValueError("Identificador inválido")
        return v


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def record_event(name: str, attendance: str, guest_token: str):
    token_hash = hashlib.sha256(guest_token.encode("utf-8")).hexdigest()
    now = utcnow()
    with db() as conn:
        row = conn.execute("SELECT id,guest_name,attending FROM rsvps WHERE guest_token_hash=?", (token_hash,)).fetchone()
        if row:
            changed = row["guest_name"] != name or row["attending"] != attendance
            if changed:
                conn.execute("""UPDATE rsvps SET guest_name=?, attending=?, updated_at=?,
                    notification_state='pendente',notification_error='',notification_attempts=0,
                    notification_sent_at=NULL WHERE id=?""", (name, attendance, now, row["id"]))
            rsvp_id = row["id"]
        else:
            changed = True
            rsvp_id = str(uuid.uuid4())
            conn.execute("""INSERT INTO rsvps (id,guest_token_hash,guest_name,attending,created_at,updated_at)
                VALUES (?,?,?,?,?,?)""", (rsvp_id, token_hash, name, attendance, now, now))
        conn.commit()
    return rsvp_id, changed


def send_whatsapp(rsvp_id: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM rsvps WHERE id=?", (rsvp_id,)).fetchone()
    if not row:
        return False
    if not WHATSAPP_READY:
        with db() as conn:
            conn.execute("UPDATE rsvps SET notification_state='pendente',notification_error=? WHERE id=?",
                         ("Falta configurar a API oficial do WhatsApp.", rsvp_id))
            conn.commit()
        return False
    status = "Confirmo a minha presença" if row["attending"] == "sim" else "Não poderei comparecer"
    timestamp = datetime.fromisoformat(row["updated_at"]).astimezone(MZ_TZ).strftime("%d/%m/%Y às %H:%M")
    # TEMPLATE a aprovar na Meta, tipo Utility, idioma pt_PT:
    # "Nova resposta ao aniversário de Dulce: {{1}} — {{2}}. Registado em {{3}}."
    data = {
        "messaging_product": "whatsapp", "to": WA_TO, "type": "template",
        "template": {"name": WA_TEMPLATE, "language": {"code": WA_LANG},
                     "components": [{"type": "body", "parameters": [
                         {"type": "text", "text": row["guest_name"]},
                         {"type": "text", "text": status},
                         {"type": "text", "text": timestamp},
                     ]}]},
    }
    try:
        result = requests.post(
            f"https://graph.facebook.com/{META_API_VERSION}/{WA_SENDER}/messages",
            headers={"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"},
            json=data, timeout=12)
        if not result.ok:
            raise RuntimeError(f"API do WhatsApp: HTTP {result.status_code}: {result.text[:300]}")
        accepted = bool(result.json().get("messages"))
        if not accepted:
            raise RuntimeError("API não devolveu identificador de mensagem")
        # 'enviada' indica aceite pela API, não entregue ao destinatário.
        with db() as conn:
            conn.execute("""UPDATE rsvps SET notification_state='aceite_pela_api',
                notification_error='',notification_attempts=notification_attempts+1,
                notification_sent_at=? WHERE id=? AND updated_at=?""",
                (utcnow(),rsvp_id,row["updated_at"]))
            conn.commit()
        return True
    except Exception as e:
        with db() as conn:
            conn.execute("""UPDATE rsvps SET notification_state='falhou',
              notification_error=?,notification_attempts=notification_attempts+1 WHERE id=? AND updated_at=?""",
              (str(e)[:350],rsvp_id,row["updated_at"]))
            conn.commit()
        return False


@app.post("/api/rsvp")
def post_rsvp(item: RSVP, request: Request, background_tasks: BackgroundTasks):
    rate_limit(request, "rsvp", 30, 600)
    if item.contact_site.strip():
        raise HTTPException(400, detail="Não foi possível validar a resposta.")
    rsvp_id, changed = record_event(item.name, item.attending, item.guest_token)
    if changed:
        background_tasks.add_task(send_whatsapp, rsvp_id)
    return {"saved": True, "message": "A sua resposta foi registada."}


def auth_token():
    expires = int(time.time() + 8 * 3600)
    nonce = secrets.token_urlsafe(16)
    payload = f"{expires}.{nonce}"
    digest = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{digest}"


def require_admin(request: Request):
    if not ADMIN_READY:
        raise HTTPException(503, detail="O administrador ainda não está configurado.")
    value = request.cookies.get("dulce_admin", "")
    parts = value.split(".")
    if len(parts) != 3:
        raise HTTPException(401, detail="Sessão não iniciada")
    exp, nonce, signature = parts
    if not exp.isdigit() or int(exp) < int(time.time()):
        raise HTTPException(401, detail="Sessão expirada")
    expected = hmac.new(SESSION_SECRET.encode(), f"{exp}.{nonce}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, detail="Sessão inválida")


class Login(BaseModel):
    password: str


@app.post("/api/admin/login")
def admin_login(item: Login, request: Request, response: Response):
    rate_limit(request, "admin-login", 5, 900)
    if not ADMIN_READY:
        raise HTTPException(503, detail="Configure ADMIN_PASSWORD e SESSION_SECRET no servidor.")
    if not hmac.compare_digest(item.password.encode(), ADMIN_PASSWORD.encode()):
        raise HTTPException(401, detail="Palavra-passe incorrecta")
    secure_cookie = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie("dulce_admin", auth_token(), max_age=8*3600, httponly=True,
                        secure=secure_cookie, samesite="strict", path="/")
    return {"ok": True}


@app.post("/api/admin/logout")
def logout(request: Request, response: Response):
    require_admin(request)
    response.delete_cookie("dulce_admin", path="/")
    return {"ok": True}


@app.get("/api/admin/rsvps")
def admin_rsvps(request: Request):
    require_admin(request)
    with db() as conn:
        rows = conn.execute("""SELECT id,guest_name,attending,created_at,updated_at,
                 notification_state, notification_error,notification_attempts,notification_sent_at
                 FROM rsvps ORDER BY updated_at DESC""").fetchall()
    items = [dict(row) for row in rows]
    return {"items": items, "counts": {
        "total": len(items), "sim": sum(1 for x in items if x["attending"] == "sim"),
        "nao": sum(1 for x in items if x["attending"] == "nao"),
        "pending": sum(1 for x in items if x["notification_state"] == "pendente"),
        "failed": sum(1 for x in items if x["notification_state"] == "falhou"),
    }, "whatsapp_configured": WHATSAPP_READY}


@app.get("/api/admin/export")
def admin_export(request: Request):
    require_admin(request)
    with db() as conn:
        rows = conn.execute("SELECT guest_name,attending,created_at,updated_at,notification_state FROM rsvps ORDER BY guest_name").fetchall()
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Nome", "Presença", "Criado em (UTC)", "Actualizado em (UTC)", "Estado WhatsApp"])
    for r in rows:
        writer.writerow([r["guest_name"], "Confirmado" if r["attending"] == "sim" else "Não comparece",r["created_at"],r["updated_at"],r["notification_state"]])
    return Response(content="\ufeff"+stream.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=confirmacoes-dulce-marcos.csv"})


@app.post("/api/admin/retry")
def retry_notifications(request: Request):
    require_admin(request)
    rate_limit(request, "retry", 5, 60)
    with db() as conn:
        rows = conn.execute("SELECT id FROM rsvps WHERE notification_state IN ('pendente','falhou') ORDER BY updated_at LIMIT 10").fetchall()
    sent = 0
    if WHATSAPP_READY:
        for row in rows:
            sent += bool(send_whatsapp(row["id"]))
    return {"processed": len(rows) if WHATSAPP_READY else 0, "accepted_by_api": sent,
            "configured": WHATSAPP_READY}


@app.delete("/api/admin/rsvps/{rsvp_id}")
def delete_rsvp(rsvp_id: str, request: Request):
    require_admin(request)
    try: uuid.UUID(rsvp_id)
    except ValueError: raise HTTPException(400, detail="Identificador inválido")
    with db() as conn:
        conn.execute("DELETE FROM rsvps WHERE id=?", (rsvp_id,))
        conn.commit()
    return {"deleted": True}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/admin")
def admin_page():
    return FileResponse(STATIC / "admin.html")


@app.get("/styles.css")
def styles(): return FileResponse(STATIC / "styles.css", media_type="text/css")


@app.get("/app.js")
def appjs(): return FileResponse(STATIC / "app.js", media_type="text/javascript")


@app.get("/admin.js")
def adminjs(): return FileResponse(STATIC / "admin.js", media_type="text/javascript")


@app.get("/")
def homepage(): return FileResponse(STATIC / "index.html")
