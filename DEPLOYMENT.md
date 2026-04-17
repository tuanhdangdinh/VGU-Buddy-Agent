# Deployment Information

## Public URL
https://vgu-buddy-agent-production.up.railway.app
*(Note: Replace the URL above with your actual generated domain from Railway or Render)*

## Platform
Railway

## Test Commands

### Health Check
```bash
curl https://vgu-buddy-agent-production.up.railway.app/health
# Expected: {"status": "ok", "app": "Study Buddy - VGU", "version": "1.0.0", ...}
```

### API Test (with authentication)
```bash
curl -X POST https://vgu-buddy-agent-production.up.railway.app/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test", "question": "Hello"}'
```

### Rate Limiting Test (10 req/min)
```bash
for i in {1..15}; do 
  curl -H "X-API-Key: YOUR_KEY" \
       -H "Content-Type: application/json" \
       -X POST https://vgu-buddy-agent-production.up.railway.app/ask \
       -d '{"session_id":"test","question":"test '"$i"'"}'; 
  echo "";
done
# Should eventually return 429 Too Many Requests
```

## Environment Variables Set
- `PORT`
- `REDIS_URL`
- `AGENT_API_KEY`
- `GEMINI_API_KEY`
- `LOG_LEVEL` (or `DEBUG`)
- `ENVIRONMENT`
- `MONTHLY_BUDGET_USD` (= 10.0)
- `RATE_LIMIT_PER_MINUTE` (= 10)

## Screenshots
Please create a `screenshots/` folder and add your images there before submitting:
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)