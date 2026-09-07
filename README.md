# DeenLink AI

DeenLink AI is an intelligent RAG (Retrieval-Augmented Generation) AI Agent designed to answer questions related to the Quran, Hadith, Fiqh, and provide Islamic motivational support. It is built to prioritize authenticity, citing its sources, and strictly avoiding hallucinations or religious innovations.

Live at: [deenlink.org](https://deenlink.org) · API: [api.deenlink.org](https://api.deenlink.org)

## ✨ Features
- 🤖 **RAG-Powered Answers** — retrieval-augmented responses grounded in Quran, Hadith, and Fiqh sources, with citations
- 💬 **Conversational Chat** — persistent conversation history, streaming responses
- ⭐ **Stellar Payments** — optional, non-custodial USDC/XLM support flow: unsigned transaction → user signs in their own wallet → on-chain verification via Horizon (off by default, see below)
- 🔐 **JWT Authentication** — RSA-signed tokens, role-based access
- 📊 **Admin Dashboard** — system health, latency, and feedback monitoring

## Tech Stack
- **Backend Framework**: FastAPI (Python)
- **AI/LLM Engine**: Groq (`openai/gpt-oss-120b`)
- **Vector Database**: Qdrant (for RAG document retrieval)
- **Relational Database**: PostgreSQL (for chat history, users, and analytics)
- **Blockchain**: `stellar-sdk` (Python) · Horizon — optional Stellar payments module
- **Package Manager**: `uv` (fast, reproducible Python environments)
- **Reverse Proxy**: Caddy (for automatic HTTPS)

---

## 🛠️ Local Development Setup

1. **Install Dependencies**
   Make sure you have the `uv` package manager installed. Then run:
```bash
   uv sync
```

2. **Environment Variables**
   Copy the example environment file and fill in your keys:
```bash
   cp .env.example .env
```

3. **Generate JWT Keys**
   To run the backend locally, you need RSA keys for JWT verification:
```bash
   mkdir -p src/backend/api/v2/keys
   openssl genpkey -algorithm RSA -out src/backend/api/v2/keys/private.pem -pkeyopt rsa_keygen_bits:2048
   openssl rsa -pubout -in src/backend/api/v2/keys/private.pem -out src/backend/api/v2/keys/public.pem
   chmod 600 src/backend/api/v2/keys/private.pem
```

4. **Start Databases**
   Start local instances of Postgres and Qdrant:
```bash
   docker compose up -d
```

5. **Start the Server**
```bash
   uv run uvicorn src.backend.api.main:app --reload --host 127.0.0.1 --port 8000
```

6. **Ingest Knowledge Base**
   Populate the Qdrant database with Quran and Hadith data:
```bash
   uv run python src/backend/api/v2/optimise_vps_kb.py
   uv run python src/backend/api/v2/ingest_quran.py
```

---

## ⭐ Stellar Payments (Optional Feature)

DeenLink AI includes an optional, non-custodial Stellar/USDC support flow, gated entirely behind an environment flag and **off by default**. When disabled, the app's behavior and UI are unchanged.

**How it works:**
1. Backend builds an unsigned Stellar payment transaction (`POST /api/stellar/payment/initialize`)
2. The user signs it in their own wallet (Freighter, xBull, Albedo)
3. Backend verifies the payment on-chain via Horizon (`POST /api/stellar/payment/verify`)
4. Funds go directly to the platform's Stellar account — no custody of user funds at any point

**Environment variables:**

| Variable | Description |
|---|---|
| `STELLAR_PAYMENTS_ENABLED` | Enables the feature (routes, UI, SEP-1 metadata). Default: `false` |
| `STELLAR_NETWORK` | `testnet` or `mainnet`. Default: `testnet` |
| `STELLAR_PLATFORM_PUBLIC_KEY` | Public key that receives payments; published in `stellar.toml` |

**SEP-1 Metadata:** `GET /.well-known/stellar.toml` (active only when the feature is enabled)

**Known limitation:** the transaction-signing flow uses SEP-0007 deep links, which work with mobile wallet apps but not browser extensions — verified functional via direct API testing (real XDR generation, on-chain verification); full mobile wallet click-through is tracked as an open issue.

---

## 🚀 Production VPS Deployment

These are the exact steps to deploy DeenLink AI to a public VPS (like Ubuntu).

### 1. Clone & Configure
```bash
git clone https://github.com/CyberXpert607/DeenLink-AI.git
cd DeenLink-AI
cp .env.example .env
nano .env  # Add your production API keys and secure POSTGRES_PASSWORD
```

### 2. Generate Security Keys
```bash
mkdir -p src/backend/api/v2/keys
openssl genpkey -algorithm RSA -out src/backend/api/v2/keys/private.pem -pkeyopt rsa_keygen_bits:2048
openssl rsa -pubout -in src/backend/api/v2/keys/private.pem -out src/backend/api/v2/keys/public.pem
chmod 600 src/backend/api/v2/keys/private.pem
```

### 3. Spin up Secure Databases
```bash
# This starts Postgres and Qdrant bound safely to 127.0.0.1
docker compose up -d
```

### 4. Configure Systemd Service
```bash
sudo cp deen-ai.service /etc/systemd/system/deen-ai.service

# Edit the service file:
# 1. Update `User=` to your VPS username (e.g. ubuntu)
# 2. Update `WorkingDirectory=` to the absolute path of the repo
# 3. Ensure the `ExecStart=` path points to your `uv` binary
sudo nano /etc/systemd/system/deen-ai.service

sudo systemctl daemon-reload
sudo systemctl enable deen-ai
sudo systemctl start deen-ai
```

### 5. Ingest Knowledge Base
*Note: This can be run safely while the backend is live.*
```bash
uv run python src/backend/api/v2/optimise_vps_kb.py
uv run python src/backend/api/v2/ingest_quran.py
```

### 6. Configure Caddy Proxy
```bash
# Replace 'api.deenlink.org' with your actual domain in the Caddyfile
nano Caddyfile

sudo caddy fmt --overwrite Caddyfile
sudo caddy reload --config Caddyfile
```

---

## 📊 Admin Dashboard
The API includes a built-in administration dashboard to track system health, active users, API latency, error rates, and user feedback.
When the server is running, you can access the dashboard UI at:
`https://api.yourdomain.com/api/v2/admin/dashboard/ui`
*(Note: JWT Authentication with `user_type = admin` is required to view live metrics).*

---

## 🌊 Contributing & Drips Wave

This repository participates in the Stellar Drips Wave bounty program — contributors earn Points (and real rewards) for resolving this repo's issues during a Wave, with complexity tiers set in the Drips Wave app.

- All pull requests target the `dev` branch (`main` is releases only)
- CI (tests) must pass before review
- One contributor per issue — request it through the Wave app; the maintainer assigns it. Please don't open a PR for an issue you haven't been assigned.

## 📜 License
MIT © DeenLink AI
