# CLAUDE.md

This file provides persistent project context to Claude Code for the **India ETF Trading Platform** — a dynamic, beginner-friendly ETF trading assistant for Indian markets (NSE/BSE), built with Python (FastAPI backend) and React/Next.js (frontend).

---

## Project overview

A full-stack trading intelligence platform that:
- Pulls live ETF price data from NSE/BSE via yfinance and/or TrueData
- Computes real-time technical signals (RSI, MA crossovers, volume) using pandas-ta
- Runs backtests on historical NSE data using backtesting.py
- Streams live prices and signals to a React dashboard over WebSocket
- Explains signals in plain English using the Claude API (Anthropic)
- Supports paper trading (simulated orders) and eventually real orders via broker APIs (Zerodha Kite / Upstox / Angel One SmartAPI)

Target user: complete beginner in Indian stock markets.

---

## Monorepo structure

```
etf-platform/
├── CLAUDE.md                   ← this file
├── .claude/
│   ├── settings.json
│   └── rules/
│       ├── backend-rules.md
│       └── frontend-rules.md
├── backend/                    ← Python FastAPI app
│   ├── main.py                 ← FastAPI entry point
│   ├── api/
│   │   ├── prices.py           ← /prices WebSocket + REST
│   │   ├── signals.py          ← /signals endpoint
│   │   ├── backtest.py         ← /backtest endpoint
│   │   └── explain.py          ← /explain (Claude API calls)
│   ├── services/
│   │   ├── data_ingestion.py   ← yfinance / TrueData fetchers
│   │   ├── signal_engine.py    ← RSI, MA, MACD logic
│   │   ├── backtest_engine.py  ← backtesting.py wrapper
│   │   └── broker.py           ← Zerodha / Upstox adapters
│   ├── models/
│   │   ├── etf.py
│   │   ├── signal.py
│   │   └── trade.py
│   ├── db/
│   │   ├── database.py         ← SQLAlchemy + TimescaleDB setup
│   │   └── migrations/         ← Alembic migrations
│   ├── tasks/
│   │   └── scheduler.py        ← Celery beat tasks
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/                   ← Next.js React app
│   ├── app/
│   │   ├── page.tsx            ← main dashboard
│   │   ├── strategy/
│   │   ├── backtest/
│   │   └── learn/
│   ├── components/
│   │   ├── PriceCard.tsx
│   │   ├── SignalBadge.tsx
│   │   ├── CandlestickChart.tsx
│   │   └── BacktestChart.tsx
│   ├── lib/
│   │   ├── websocket.ts        ← WebSocket client hook
│   │   └── api.ts              ← REST API client
│   ├── package.json
│   └── .env.local.example
├── docker-compose.yml
└── README.md
```

---

## Commands

### Backend

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Run FastAPI dev server
cd backend && uvicorn main:app --reload --port 8000

# Run Celery worker (price polling scheduler)
cd backend && celery -A tasks.scheduler worker --loglevel=info

# Run Celery beat (periodic task trigger)
cd backend && celery -A tasks.scheduler beat --loglevel=info

# Run tests
cd backend && pytest tests/ -v

# Database migrations
cd backend && alembic upgrade head
cd backend && alembic revision --autogenerate -m "description"

# Lint and format
cd backend && ruff check . && ruff format .
```

### Frontend

```bash
# Install dependencies
cd frontend && npm install

# Run Next.js dev server
cd frontend && npm run dev

# Build for production
cd frontend && npm run build

# Run tests
cd frontend && npm test

# Lint
cd frontend && npm run lint
```

### Docker (full stack)

```bash
# Start all services (postgres, redis, backend, frontend)
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop all
docker-compose down
```

---

## Tech stack

### Backend
| Tool | Purpose |
|---|---|
| Python 3.12+ | Core language |
| FastAPI | REST API + WebSocket server |
| yfinance | Free NSE/BSE OHLCV data (`.NS` suffix for NSE) |
| pandas-ta | Technical indicators (RSI, MA, MACD, Bollinger) |
| backtesting.py | Strategy backtesting on historical OHLCV |
| SQLAlchemy 2.x | ORM (async) |
| PostgreSQL + TimescaleDB | Time-series OHLCV storage |
| Redis | Live price cache, Celery broker |
| Celery | Scheduled price-polling tasks |
| Alembic | Database migrations |
| Anthropic Python SDK | Claude API for plain-English signal explanations |
| kiteconnect | Zerodha broker API (live orders) |
| upstox-python | Upstox broker API (alternative) |
| ruff | Linting and formatting (replaces black + flake8) |
| pytest + pytest-asyncio | Testing |

### Frontend
| Tool | Purpose |
|---|---|
| Next.js 15 (App Router) | React framework |
| TypeScript | All frontend code is strictly typed |
| Tailwind CSS | Styling |
| lightweight-charts | TradingView candlestick charts |
| Recharts | Backtest P&L charts |
| socket.io-client | WebSocket live price connection |
| SWR | Data fetching and caching |
| Zustand | Global state (portfolio, signals) |
| Vitest | Unit testing |

### Infrastructure
| Tool | Purpose |
|---|---|
| Docker + docker-compose | Local dev environment |
| TimescaleDB | PostgreSQL extension for OHLCV time-series |
| Redis | Cache + Celery message broker |

---

## ETF symbols reference

Always use the `.NS` suffix when calling yfinance for NSE-listed ETFs:

```python
# Correct yfinance symbols for Indian ETFs
NIFTYBEES_SYMBOL   = "NIFTYBEES.NS"    # Nippon India ETF Nifty 50 BeES
GOLDBEES_SYMBOL    = "GOLDBEES.NS"     # Nippon India ETF Gold BeES
LIQUIDBEES_SYMBOL  = "LIQUIDBEES.NS"   # Nippon India ETF Liquid BeES
KOTAKBKETF_SYMBOL  = "KOTAKBKETF.NS"   # Kotak Nifty Bank ETF
SETFNIF50_SYMBOL   = "SETFNIF50.NS"    # SBI ETF Nifty 50
ITBEES_SYMBOL      = "ITBEES.NS"       # Nippon India ETF Nifty IT
JUNIORBEES_SYMBOL  = "JUNIORBEES.NS"   # Nippon India ETF Nifty Next 50
```

NSE market hours: **9:15 AM – 3:30 PM IST, Monday–Friday** (excluding NSE holidays).
Pre-open session: 9:00–9:15 AM IST. Do not attempt order placement outside market hours.

---

## Code style and conventions

### Python (backend)

- Use **Python 3.12+** features. Use `match` statements for signal type switching.
- **Async everywhere**: all FastAPI routes, database calls, and external API calls must be `async def`.
- Use `ruff` for formatting — do not use black or flake8 separately.
- Use **type hints on all functions** — both arguments and return types. No `Any` unless unavoidable.
- Prefer **Pydantic v2** models for request/response validation.
- All monetary values (prices, P&L) are stored as `Decimal`, not `float`.
- Signal values (RSI, MA, etc.) may use `float`.
- Use `pandas` for all OHLCV data manipulation. Never iterate row-by-row with a for loop — use vectorized operations.
- **Never hardcode API keys**. All secrets come from environment variables via `python-dotenv`.
- Use `structlog` for structured JSON logging — not `print()` or `logging.info()`.
- Database queries use SQLAlchemy async sessions only — never raw SQL strings.

### TypeScript / React (frontend)

- **Strict TypeScript** — `tsconfig.json` has `"strict": true`. No `any`.
- Use **Next.js App Router** (`app/` directory) only — not the Pages router.
- All components are **functional components with hooks**. No class components.
- Use **named exports** for components — no default exports.
- Keep components under 150 lines. Extract hooks to `lib/hooks/`.
- API calls go through `lib/api.ts` — never call `fetch` directly in a component.
- WebSocket logic lives in `lib/websocket.ts` — never inline it in components.
- Use **Tailwind CSS** for all styling. No inline styles, no CSS modules.
- Format: 2-space indentation, single quotes, no semicolons (Prettier config).

---

## Environment variables

### Backend (`backend/.env`)

```env
# Data
YFINANCE_ENABLED=true
TRUEDATA_API_KEY=                     # Optional — for tick-by-tick data
TRUEDATA_USER=

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/etfdb
REDIS_URL=redis://localhost:6379/0

# Anthropic (for signal explanations)
ANTHROPIC_API_KEY=                    # Required for /explain endpoint

# Broker APIs (optional — only needed for live order placement)
ZERODHA_API_KEY=
ZERODHA_API_SECRET=
UPSTOX_API_KEY=
UPSTOX_API_SECRET=

# App
ENVIRONMENT=development               # development | production
LOG_LEVEL=INFO
```

### Frontend (`frontend/.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/prices
```

---

## Key domain rules — always follow these

**Signal definitions** (used consistently across backend and frontend):

| Signal | Condition | Display |
|---|---|---|
| BUY | RSI 40–60 AND price > MA50 AND volume > 1.5× avg | Green badge |
| HOLD | Price near MA50 (within 1%) OR RSI 60–70 | Amber badge |
| WATCH | Price > MA20 but < MA50, volume rising | Teal badge |
| AVOID | Price < MA50 OR RSI > 70 OR RSI < 30 | Red badge |
| SAFE HOLD | Liquid BeES only — always stable | Blue badge |

**Backtest rules:**
- Always backtest on a minimum of 1 year of historical OHLCV data.
- Report: win rate, average return, max drawdown, number of trades, Sharpe ratio.
- Never show backtest results without the "Buy & Hold" benchmark comparison.
- Always include the disclaimer: "Past backtested performance does not guarantee future returns."

**Beginner safety rules** (never remove these from the UI):
- Always show a risk warning when a user is about to place a real order.
- Show stop-loss recommendation (−3% from entry) on every BUY signal.
- Display VIX level with a plain-English interpretation (< 15 = calm, 15–25 = elevated, > 25 = high fear).
- For intraday trading: flag if the user attempts to hold past 3:15 PM IST.

**SEBI compliance note:**
- As of April 2026, a **static IP address is mandatory** for broker API-based order placement (Zerodha, Upstox, Angel One). Always surface this requirement in the broker setup UI.

---

## API endpoint conventions

All REST endpoints follow this pattern:

```
GET  /api/v1/prices/{symbol}           → latest price snapshot
GET  /api/v1/prices/{symbol}/history   → OHLCV history (query: from, to, interval)
GET  /api/v1/signals                   → signals for all tracked ETFs
GET  /api/v1/signals/{symbol}          → signal for one ETF
POST /api/v1/backtest                  → run a backtest (body: symbol, strategy, from, to)
POST /api/v1/explain                   → Claude API explanation of a signal
WS   /ws/prices                        → live price stream (JSON messages)
```

All responses use this envelope:

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "timestamp": "2026-05-05T10:30:00+05:30"
}
```

All timestamps are **IST (Asia/Kolkata, UTC+5:30)**, stored in DB as UTC, returned as ISO 8601 with timezone.

---

## Testing conventions

- All backend tests go in `backend/tests/`.
- Use `pytest` with `pytest-asyncio` for async test functions.
- Use `httpx.AsyncClient` for FastAPI endpoint tests — not TestClient (which is sync).
- Mock external data calls (yfinance, broker APIs, Anthropic) in tests — never hit live APIs in tests.
- Frontend unit tests use Vitest. Component tests use React Testing Library.
- Test file naming: `test_signal_engine.py`, `test_prices_api.py` (backend); `SignalBadge.test.tsx` (frontend).

---

## Common mistakes to avoid

- Do **not** use `float` for price or P&L values — use `Decimal`.
- Do **not** use `.NS` suffix in the UI display — show only the base ticker (e.g., `NIFTYBEES`).
- Do **not** place orders outside 9:15 AM–3:30 PM IST market hours — validate server-side.
- Do **not** call the Anthropic API synchronously — use `async` with the `AsyncAnthropic` client.
- Do **not** fetch yfinance data on every API request — always serve from Redis cache, refresh via Celery.
- Do **not** show raw RSI/MA numbers to users without a plain-English interpretation.
- Do **not** use `npm` — this project uses `npm` (not pnpm or yarn). Always use `npm run ...`.
- Do **not** commit `.env` files — use `.env.example` as the template.
- Do **not** use `print()` in backend code — use `structlog`.

---

## Useful references

- NSE India official: https://www.nseindia.com
- yfinance docs: https://ranaroussi.github.io/yfinance
- pandas-ta docs: https://github.com/twopirllc/pandas-ta
- backtesting.py docs: https://kernc.github.io/backtesting.py
- Zerodha Kite API: https://kite.trade/docs/connect/v3
- Upstox API v2: https://upstox.com/developer/api-documentation
- Angel One SmartAPI: https://smartapi.angelbroking.com/docs
- TrueData API: https://truedata.in/docs
- Anthropic Python SDK: https://github.com/anthropic-ai/anthropic-sdk-python
- TimescaleDB docs: https://docs.timescale.com
- FastAPI docs: https://fastapi.tiangolo.com
