import os
import httpx
from fastapi import FastAPI, HTTPException
app = FastAPI(title="Governed Egress Gateway")
GOV = os.environ["GOVERNANCE_URL"]
HEADERS = {"X-Gateway-Token": os.environ["GATEWAY_TOKEN"]}

@app.get("/health")
def health(): return {"ok": True}

@app.post("/invoke/{request_id}")
async def invoke(request_id: str):
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        try:
            auth = await client.get(GOV + "/gateway/authorize/" + request_id, headers=HEADERS)
            if auth.status_code != 200: raise HTTPException(403, "Human approval required or revoked")
            target = auth.json()
            # Only URLs supplied by the trusted governance registry are used.
            if target["method"] != "GET": raise HTTPException(403, "Method not permitted")
            result = await client.get(target["url"], headers=HEADERS if target["service"] == "local-demo" else {})
            await client.post(GOV + "/gateway/audit/" + request_id, headers=HEADERS)
            return {"service": target["service"], "upstream_status": result.status_code, "response_excerpt": result.text[:1500]}
        except httpx.HTTPError as e:
            raise HTTPException(502, "Upstream connection failed") from e
