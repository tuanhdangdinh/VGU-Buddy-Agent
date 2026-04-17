# Study Buddy — VGU AI Agent

An AI-powered study assistant for VGU (Vietnam-Germany University) students, built with FastAPI, LangGraph, FAISS RAG, and Google Gemini.

**Live deployment:** https://accomplished-dream-production-2ae1.up.railway.app

---

## Features

- **RAG pipeline** — answers questions from VGU module handbooks via FAISS + Gemini embeddings
- **LangGraph ReAct agent** — multi-step reasoning with tool use
- **API key authentication** — protected endpoints
- **Rate limiting** — 10 requests/minute per key (sliding window)
- **Cost guard** — monthly Gemini API budget cap ($10 default)
- **Stateless sessions** — Redis (falls back to in-memory)
- **Health & readiness probes** — `/health` and `/ready`
- **Graceful shutdown** — SIGTERM handling

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API framework | FastAPI + Uvicorn |
| Agent | LangGraph ReAct |
| LLM | Google Gemini 2.0 Flash |
| Vector store | FAISS + Gemini Embeddings |
| Session storage | Redis / in-memory |
| Containerisation | Docker (multi-stage) |
| Cloud platform | Railway |

---

## Prerequisites

- Python 3.12+
- [Google Gemini API key](https://aistudio.google.com/)
- Docker (for containerised setup)
- Redis (optional — app falls back to in-memory)

---

## Local Setup

### 1. Clone and create virtual environment

```bash
git clone <repo-url>
cd VGU-RAG
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
AGENT_API_KEY=your-secret-api-key
ENVIRONMENT=development
DEBUG=true
REDIS_URL=redis://localhost:6379/0   # optional
```

### 3. Run the server

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

---

## Docker Setup

### Build and run (single container)

```bash
docker build -t vgu-rag .
docker run -p 8000:8000 \
  -e GEMINI_API_KEY=your_key \
  -e AGENT_API_KEY=your-secret \
  vgu-rag
```

### Full stack with Redis (docker-compose)

```bash
cp .env.example .env.local   # fill in GEMINI_API_KEY and AGENT_API_KEY
docker compose up --build
```

---

## Deployment on Railway

### One-click deploy

1. Push this repository to GitHub
2. Create a new Railway project → **Deploy from GitHub repo**
3. Set the following environment variables in Railway dashboard:

| Variable | Value |
|----------|-------|
| `GEMINI_API_KEY` | Your Gemini key |
| `AGENT_API_KEY` | Your chosen API key |
| `ENVIRONMENT` | `production` |
| `MONTHLY_BUDGET_USD` | `10.0` |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `REDIS_URL` | Redis plugin URL (optional) |

Railway automatically provides `PORT` — no manual configuration needed.

---

## API Reference

### Health check

```bash
curl https://accomplished-dream-production-2ae1.up.railway.app/health
```

### Ask a question

```bash
curl -X POST https://accomplished-dream-production-2ae1.up.railway.app/ask \
  -H "X-API-Key: my-secret-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"question": "VGU có những ngành học nào?"}'
```

Response:

```json
{
  "session_id": "...",
  "question": "VGU có những ngành học nào?",
  "answer": "Theo [Source: vgu_overview], VGU cung cấp các ngành ...",
  "model": "gemini-2.0-flash",
  "turn": 1,
  "storage": "in-memory",
  "timestamp": "2026-04-17T19:35:00+00:00"
}
```

### Continue a session

```bash
curl -X POST https://accomplished-dream-production-2ae1.up.railway.app/ask \
  -H "X-API-Key: my-secret-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<id from previous response>", "question": "Học bổng DAAD là gì?"}'
```

### Rate limiting test

```bash
for i in {1..15}; do
  curl -s -X POST https://accomplished-dream-production-2ae1.up.railway.app/ask \
    -H "X-API-Key: my-secret-key-change-in-production" \
    -H "Content-Type: application/json" \
    -d '{"question": "test '"$i"'"}' | python3 -m json.tool
  echo "---"
done
# Requests 11–15 return HTTP 429 Too Many Requests
```

---

## Project Structure

```
VGU-RAG/
├── app/
│   ├── main.py              # FastAPI app, lifespan, endpoints
│   ├── config.py            # Settings from env vars
│   ├── auth.py              # X-API-Key authentication
│   ├── rate_limiter.py      # Sliding-window rate limit
│   ├── cost_guard.py        # Monthly budget cap
│   ├── session.py           # Redis / in-memory session storage
│   └── agent/
│       ├── graph.py         # LangGraph ReAct agent
│       ├── rag.py           # FAISS vectorstore + Gemini embeddings
│       └── tools.py         # search_handbook tool
├── data/
│   ├── handbooks/           # VGU module handbooks (Markdown/PDF)
│   └── faiss_cache/         # Pre-built FAISS index
├── Dockerfile               # Multi-stage build
├── docker-compose.yml       # App + Redis stack
├── railway.json             # Railway deployment config
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
└── DEPLOYMENT.md            # Live URL and test commands
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | *(required)* | Google Gemini API key |
| `AGENT_API_KEY` | `dev-key-change-me` | API key for `/ask` endpoint |
| `ENVIRONMENT` | `development` | `development` or `production` |
| `DEBUG` | `false` | Enable debug logging |
| `PORT` | `8000` | Server port (set automatically by Railway) |
| `REDIS_URL` | *(empty)* | Redis connection URL (optional) |
| `RATE_LIMIT_PER_MINUTE` | `10` | Max requests per API key per minute |
| `MONTHLY_BUDGET_USD` | `10.0` | Max Gemini spend per month |
| `LLM_MODEL` | `gemini-2.0-flash` | Gemini model name |

---

## Author

**Đặng Đinh Tú Anh** — Student ID: 2A202600019  
VGU — Day 12 Lab Submission, April 2026
