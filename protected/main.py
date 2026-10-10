import os, asyncio
import httpx
from fastapi import FastAPI, HTTPException
app = FastAPI(title="Protected AI Application")
GOV = os.environ["GOVERNANCE_URL"]
GATEWAY = os.environ["GATEWAY_URL"]
HEADERS = {"X-Agent-Token": os.environ["AGENT_TOKEN"]}

async def discover():
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(GOV + "/a2a", json={"action": "discover"}, headers=HEADERS)
        r.raise_for_status()
        return r.json()

@app.on_event("startup")
async def startup():
    # Retries handle first boot while the control plane creates its database.
    for attempt in range(20):
        try:
            catalog = await discover()
            print("Startup service discovery:", catalog, flush=True)
            return
        except (httpx.HTTPError, OSError):
            await asyncio.sleep(2)
    print("Startup discovery unavailable; retry through /catalog", flush=True)

@app.get("/health")
def health(): return {"ok": True}

@app.get("/catalog")
async def catalog():
    try: return await discover()
    except httpx.HTTPError as e: raise HTTPException(502, str(e))

@app.post("/demo/request/{service_id}")
async def request(service_id: str):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(GOV + "/a2a", headers=HEADERS, json={"action": "request_access", "service_id": service_id, "reason": "Demo agent needs to test a registered external API"})
    if r.status_code != 200: raise HTTPException(r.status_code, r.text)
    return r.json()

@app.post("/demo/invoke/{request_id}")
async def invoke(request_id: str):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(GATEWAY + "/invoke/" + request_id)
    if r.status_code != 200: raise HTTPException(r.status_code, r.text)
    return r.json()
