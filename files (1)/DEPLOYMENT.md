# 🍽️ AI Restaurant Call Center — Deployment Guide

## Architecture Overview

```
Phone Call
    │
    ▼
┌─────────┐   Media Stream (WS)   ┌──────────────┐   Live WS    ┌─────────────────┐
│  Twilio  │ ◄──────────────────► │  FastAPI      │ ◄──────────► │ Gemini 3.1 Flash│
│  (PSTN)  │   mulaw audio 8kHz   │  Backend      │  audio+text  │ Live API        │
└─────────┘                        │  (Railway)    │              └─────────────────┘
                                   │               │
                                   │  record_order │
                                   │       │       │
                                   └───────┼───────┘
                                           │ INSERT
                                           ▼
                                   ┌───────────────┐
                                   │   Supabase    │◄──── Dashboard (Vercel)
                                   │  PostgreSQL   │      Next.js + Realtime
                                   └───────┬───────┘
                                           │ Realtime
                                           ▼
                                   ┌───────────────┐
                                   │ Kitchen       │
                                   │ Thermal Print │
                                   └───────────────┘
```

## Phase 1: Database Setup

1. Create a new Supabase project at https://supabase.com
2. Go to **SQL Editor** → paste `supabase/schema.sql` → Run
3. Verify tables in **Table Editor**: `menu_items`, `customers`, `orders`
4. Confirm Realtime is enabled: **Database → Replication** → `orders` should be listed

## Phase 2–3: Backend Deployment (Railway)

### Local Testing
```bash
cd backend
cp ../.env.example .env   # fill in real values
pip install -r requirements.txt
python main.py
```

### Deploy to Railway
1. Push the `backend/` folder to a GitHub repo
2. Go to https://railway.app → **New Project** → **Deploy from GitHub**
3. Set root directory to `backend/`
4. Add environment variables from `.env.example` in Railway dashboard
5. Railway auto-detects the `Dockerfile` and deploys
6. Copy the public URL, e.g. `https://callcenter-xxx.up.railway.app`

### Configure Twilio
1. In Twilio Console → **Phone Numbers** → select your number
2. Under **Voice & Fax → A Call Comes In**:
   - Webhook: `https://callcenter-xxx.up.railway.app/twilio/voice`
   - Method: `POST`

## Phase 4: Dashboard Deployment (Vercel)

```bash
cd dashboard
npm install
npm run dev   # local test at localhost:3000
```

### Deploy to Vercel
1. Push `dashboard/` to GitHub
2. Import in Vercel → set **Root Directory** to `dashboard/`
3. Add env vars:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
4. Deploy — Vercel handles build automatically

## Phase 5: Kitchen Printer

Run on the local machine connected to the thermal printer:

```bash
cd printer
pip install supabase realtime-py python-escpos python-dotenv
# Edit printer.py — uncomment Usb() or Network() line
python printer.py
```

The script listens to Supabase Realtime and prints every new order.

## Key Connection: Twilio ↔ Gemini Live

The bridge works in 3 stages:

1. **Twilio calls `/twilio/voice`** → returns TwiML that opens a bidirectional
   Media Stream WebSocket back to `/twilio/stream`

2. **`/twilio/stream` handler** receives the Twilio WS, extracts the caller's
   phone number, builds a personalized system prompt (querying Supabase for
   returning customers), then opens a second WebSocket to Gemini Live API

3. **Two async tasks run concurrently:**
   - `_twilio_to_gemini`: reads audio chunks from Twilio → forwards to Gemini
   - `_gemini_to_twilio`: reads Gemini responses (audio/tool calls) → pipes
     audio back to Twilio, handles `record_order` tool calls by writing to Supabase

### Audio Format Notes
- Twilio sends **mulaw/8000** (G.711 µ-law, 8 kHz mono)
- Gemini Live expects **PCM audio** — in production add an audioop/ffmpeg
  transcode step between Twilio and Gemini
- Gemini responds with PCM audio — transcode back to mulaw for Twilio

## Environment Variables Reference

| Variable | Where | Description |
|----------|-------|-------------|
| `GEMINI_API_KEY` | Backend | Google AI Studio API key |
| `GEMINI_MODEL` | Backend | `gemini-2.0-flash-live-001` |
| `SUPABASE_URL` | Both | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Backend + Printer | service_role key |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Dashboard | anon/public key |
| `TWILIO_ACCOUNT_SID` | Backend | Twilio SID |
| `TWILIO_AUTH_TOKEN` | Backend | Twilio auth token |
