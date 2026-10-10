import os, sqlite3, json, secrets, hmac, html
from contextlib import contextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from cryptography.fernet import Fernet
from pydantic import BaseModel

app = FastAPI(title="Agentic Governance Control Plane", version="0.1.0")
security = HTTPBasic()
DB = os.environ.get("DB_PATH", "/tmp/governance.db")
fernet = Fernet(os.environ["DATA_KEY"].encode())
# Only explicitly registered destinations may be reached by the gateway.
SERVICES = {
    "local-demo": {"name": "Offline Local Demo", "capabilities": ["test-local"], "url": "http://governance:8000/gateway/local-demo", "method": "GET"},
    "httpbin-demo": {"name": "HTTPBin Demo API (online opt-in only)", "capabilities": ["test-http"], "url": "https://httpbin.org/get", "method": "GET"},
    "openai-models": {"name": "OpenAI Models API (metadata only)", "capabilities": ["list-models"], "url": "https://api.openai.com/v1/models", "method": "GET"},
}

def now(): return datetime.now(timezone.utc).isoformat()
@contextmanager
def db():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally: c.close()

@app.on_event("startup")
def init():
    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, agent TEXT NOT NULL, service TEXT NOT NULL, status TEXT NOT NULL, encrypted_reason BLOB NOT NULL, created TEXT NOT NULL, decided TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT, action TEXT NOT NULL, at TEXT NOT NULL)")

def agent_auth(x_agent_token: str = Header(default="")):
    if not hmac.compare_digest(x_agent_token, os.environ["AGENT_TOKEN"]): raise HTTPException(401, "Invalid agent credential")
    return "protected-app-001"

def gateway_auth(x_gateway_token: str = Header(default="")):
    if not hmac.compare_digest(x_gateway_token, os.environ["GATEWAY_TOKEN"]): raise HTTPException(401, "Invalid gateway credential")

def admin_auth(creds: HTTPBasicCredentials = Depends(security)):
    if not (hmac.compare_digest(creds.username, "admin") and hmac.compare_digest(creds.password, os.environ["ADMIN_PASSWORD"])):
        raise HTTPException(401, "Invalid admin credentials", headers={"WWW-Authenticate": "Basic"})

def audit(c, request_id, action):
    c.execute("INSERT INTO audit(request_id,action,at) VALUES (?,?,?)", (request_id, action, now()))

class A2AMessage(BaseModel):
    action: str
    service_id: str | None = None
    reason: str | None = None

@app.get("/health")
def health(): return {"ok": True}

@app.post("/a2a")
def a2a(msg: A2AMessage, agent: str = Depends(agent_auth)):
    # MVP custom A2A-style envelope; not a complete A2A protocol implementation.
    if msg.action == "discover":
        return {"type": "service_catalog", "agent": agent, "services": [
            {"id": k, "name": v["name"], "capabilities": v["capabilities"], "access": "approval_required"} for k, v in SERVICES.items()]}
    if msg.action == "request_access":
        if msg.service_id not in SERVICES: raise HTTPException(404, "Unknown service")
        if not msg.reason or len(msg.reason) > 2000: raise HTTPException(422, "Reason required (max 2000 characters)")
        rid = secrets.token_urlsafe(18)
        with db() as c:
            c.execute("INSERT INTO requests VALUES (?,?,?,?,?,?,?)", (rid, agent, msg.service_id, "pending", fernet.encrypt(msg.reason.encode()), now(), None))
            audit(c, rid, "requested")
        return {"request_id": rid, "status": "pending", "message": "Human approval required"}
    raise HTTPException(400, "Unsupported action")

@app.get("/agent/requests/{request_id}")
def agent_status(request_id: str, agent: str = Depends(agent_auth)):
    with db() as c:
        r = c.execute("SELECT status, service FROM requests WHERE id=? AND agent=?", (request_id, agent)).fetchone()
    if not r: raise HTTPException(404, "Request not found")
    return dict(r)

@app.get("/gateway/local-demo")
def local_demo(_: None = Depends(gateway_auth)):
    return {"message": "Local offline service reached after human approval"}

@app.get("/gateway/authorize/{request_id}")
def authorize(request_id: str, _: None = Depends(gateway_auth)):
    with db() as c:
        r = c.execute("SELECT status, service FROM requests WHERE id=?", (request_id,)).fetchone()
    if not r or r["status"] != "approved": raise HTTPException(403, "Not approved")
    service = SERVICES.get(r["service"])
    if not service: raise HTTPException(403, "Service unavailable")
    return {"service": r["service"], "url": service["url"], "method": service["method"]}

@app.post("/gateway/audit/{request_id}")
def gateway_audit(request_id: str, _: None = Depends(gateway_auth)):
    with db() as c: audit(c, request_id, "gateway_invoked")
    return {"ok": True}

@app.get("/api/requests")
def requests(_: None = Depends(admin_auth)):
    with db() as c:
        rows = c.execute("SELECT * FROM requests ORDER BY created DESC LIMIT 100").fetchall()
    return [{"id": r["id"], "agent": r["agent"], "service": r["service"], "status": r["status"], "reason": fernet.decrypt(r["encrypted_reason"]).decode(), "created": r["created"]} for r in rows]

@app.post("/api/requests/{request_id}/{decision}")
def decide(request_id: str, decision: str, _: None = Depends(admin_auth)):
    if decision not in ("approve", "deny", "revoke"): raise HTTPException(400, "Invalid decision")
    with db() as c:
        r = c.execute("SELECT status FROM requests WHERE id=?", (request_id,)).fetchone()
        if not r: raise HTTPException(404, "Unknown request")
        if decision in ("approve", "deny") and r["status"] != "pending": raise HTTPException(409, "Already decided")
        if decision == "revoke" and r["status"] != "approved": raise HTTPException(409, "Not approved")
        status = {"approve":"approved", "deny":"denied", "revoke":"revoked"}[decision]
        c.execute("UPDATE requests SET status=?, decided=? WHERE id=?", (status, now(), request_id))
        audit(c, request_id, status)
    return {"request_id": request_id, "status": status}

@app.get("/", response_class=HTMLResponse)
def dashboard(_: None = Depends(admin_auth)):
    return """<!doctype html><html><head><meta charset='utf-8'><title>Agentic Governance</title>
<style>body{font:16px system-ui;max-width:920px;margin:40px auto;padding:0 20px;background:#f8fafc;color:#0f172a}h1{margin-bottom:4px}.item{background:white;border:1px solid #cbd5e1;border-radius:10px;padding:16px;margin:12px 0}button{margin:4px;padding:8px 12px;cursor:pointer}small{color:#475569}code{overflow-wrap:anywhere}</style></head><body>
<h1>Agentic Governance</h1><p>Human approval dashboard · all external connections require authorization</p><div id='items'>Loading…</div>
<script>
async function refresh(){const res=await fetch('/api/requests');if(!res.ok){document.getElementById('items').textContent='Could not load requests';return}const data=await res.json();const root=document.getElementById('items');root.replaceChildren();if(!data.length)root.textContent='No requests yet. Open the protected application demo endpoint.';
for(const r of data){const card=document.createElement('div');card.className='item';const h=document.createElement('strong');h.textContent=r.service+' — '+r.status;card.append(h);for(const val of [r.reason,'Agent: '+r.agent,'Request ID: '+r.id]){const p=document.createElement('p');p.textContent=val;card.append(p)}for(const action of (r.status==='pending'?['approve','deny']:r.status==='approved'?['revoke']:[])){const b=document.createElement('button');b.textContent=action;b.onclick=async()=>{const response=await fetch('/api/requests/'+encodeURIComponent(r.id)+'/'+action,{method:'POST'});if(!response.ok)alert(await response.text());await refresh()};card.append(b)}root.append(card)}}refresh();setInterval(refresh,5000);
</script></body></html>"""
