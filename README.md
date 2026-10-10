# Agentic Governance — MVP v0.2 (offline-first)

Human-in-the-loop authorization for external AI service connections initiated by a containerized application.

## Architecture

- **Governance:** FastAPI parent control plane, Basic-auth human approval dashboard, SQLite registry/requests/audit, encrypted request-reason field.
- **Protected:** FastAPI application on an **internal-only Docker network**. On startup, it discovers registered services through a custom A2A-style JSON message. It cannot directly reach the public internet.
- **Gateway:** The only component eligible for an opt-in outbound network. In the **default offline configuration**, every container is attached exclusively to the internal Docker network. For each invocation, the gateway asks governance whether the request is approved, then calls a fixed, allowlisted URL.

**Scope:** This is an educational MVP, not production-grade security. It does **not** yet implement the formal A2A protocol, local LLM inference, human self-registration, complete encrypted-database storage, provider credential management, or a full policy engine. Its governance "agent" is currently deterministic logic rather than an LLM. Those are roadmap items, not completed features. SQLite metadata and audit entries are plaintext; the request reason is encrypted using Fernet. Docker isolation alone is not a hardened multi-tenant sandbox.

## Run

1. Install Docker with Compose and Python 3 (with `cryptography` installed for key generation).
2. Copy `.env.example` to `.env`. Generate fresh random `ADMIN_PASSWORD`, `AGENT_TOKEN`, and `GATEWAY_TOKEN` values, and a Fernet `DATA_KEY` using:
   ```sh
   python -m pip install cryptography
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
3. For an offline runtime, pre-load Docker images and Python dependencies into the local build environment before disconnecting from the internet (see `docs/OFFLINE_DEPLOYMENT.md`). Then run `docker compose up --build -d`. The default Compose stack has **no public egress network**.
4. Open **http://localhost:8000/** and sign in with username `admin` and the `ADMIN_PASSWORD` from `.env`.
5. To exercise the protected app without exposing it on the host, use Docker Compose exec:
   ```sh
   docker compose exec protected python -c 'import httpx; print(httpx.get("http://localhost:8000/catalog").json())'
   docker compose exec protected python -c 'import httpx; print(httpx.post("http://localhost:8000/demo/request/local-demo").json())'
   ```
6. Copy the returned `request_id`. **Before approval**, test invocation (expected HTTP 403):
   ```sh
   docker compose exec protected python -c 'import httpx; r=httpx.post("http://localhost:8000/demo/invoke/REPLACE_REQUEST_ID"); print(r.status_code, r.text)'
   ```
7. Click **approve** in the parent dashboard and repeat the invocation. You should receive a response from the local demo endpoint without internet access. Click **revoke** and repeat: access is denied again.
8. Inspect `docker compose logs protected` to see the startup discovery response.

To explicitly enable internet-connected providers, use `docker compose -f docker-compose.yml -f docker-compose.online.yml up --build -d`. Never use this override for an air-gapped deployment. `openai-models` is included as an illustrative provider entry. Without provider credentials, that upstream endpoint returns 401 even after human approval; this is expected. Approval is not a substitute for provider authentication.

## Security notes

- The parent dashboard binds to localhost only. Do not expose HTTP Basic authentication over an untrusted network without HTTPS and stronger authentication.
- The protected application and gateway share the internal network. The gateway exposes only the allowlisted `/invoke/{request_id}` interface. The parent authenticates agents with a development token and the gateway with a separate token.
- This MVP assumes a single trusted protected application. It does not bind invocation to individual container identities, limit approved calls, or prevent one protected workload from using another's request ID. Add workload identity, short-lived grants, rate limits, scoped policies, and network hardening before supporting untrusted workloads.
- The external service list is code-defined, not yet editable from the UI. A database-backed registry is a next milestone.
- Keep `.env` private; never commit secrets. Losing `DATA_KEY` makes encrypted request reasons unreadable. Rotate development credentials if leaked.
- `docker compose down -v` removes the local database volume and all approvals/audit history.

## Roadmap

1. Standards-compliant A2A agent cards, task messaging and authentication.
2. Database-backed dynamic service registry and human registration with roles.
3. Local Ollama advisory agent producing risk explanations (never granting approval).
4. Authenticated workload identity and gateway-bound, scoped authorization grants.
5. Provider credentials stored separately from protected workloads; complete database encryption.
6. Integration tests for egress denial, approval, revocation and malicious requests.

License: MIT.

## Offline-first architecture decision (2026-10-10)

- **All AI-agent infrastructure is self-hosted locally**; the Docker daemon manages the protected workload and governance services.
- **No cloud AI dependency is required for the offline demonstration.** The first approved invocation calls `local-demo` through the governance gateway.
- **External AI services are optional future integrations**, not required at startup. They cannot be reached in the default network configuration.
- The current release does **not** yet embed an offline LLM or Ollama. An optional local model server is planned; its model weights and images must be preloaded for truly offline use.
- The startup service discovery response is a **custom A2A-style message**, not standards-compliant A2A.
- All design decisions, tests, security findings, and deployment guidance are exported in the ZIP under `docs/`.
