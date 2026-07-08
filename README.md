# India ETF Trading Platform 🇮🇳

A full-stack trading intelligence platform designed for beginners in the Indian stock market. Built with **FastAPI**, **Next.js 15**, and **Claude AI**.

## 🚀 Features

- **Live Dashboard**: Real-time price tracking and technical signals for NSE ETFs (NIFTYBEES, GOLDBEES, etc.).
- **AI Signal Mentor**: Plain-English explanations of technical indicators (RSI, MA) powered by **Google Gemini**.
- **Strategy Lab**: High-performance historical backtesting using `backtesting.py`.
- **Market Sentiment**: Real-time **India VIX** meter with beginner-friendly risk interpretations.
- **WebSocket Streaming**: Sub-second price updates for a professional trading experience.
- **Paper Trading**: Simulated order execution to practice without financial risk.

## 🛠️ Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy (Async), Celery, Redis, TimescaleDB.
- **Frontend**: Next.js 15 (App Router), TypeScript, Tailwind CSS, Lightweight Charts, Recharts.
- **AI**: Google Gemini API (1.5 Flash).
- **Data**: yfinance (NSE/BSE).

## 🏗️ Getting Started

### Prerequisites
- Docker & Docker Compose
- Google API Key (for AI explanations)

### Run with Docker (Recommended)
1. Clone the repository.
2. Add your `GOOGLE_API_KEY` to `backend/.env`.
3. Start the services:
   ```bash
   docker-compose up -d
   ```
4. Access the platform:
   - Frontend: `http://localhost:3000`
   - Backend API: `http://localhost:8000`

### Manual Setup

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## 📈 ETF Symbols
Always use the base ticker in the UI; the backend handles the `.NS` suffix for NSE:
- `NIFTYBEES`: Nippon India ETF Nifty 50 BeES
- `GOLDBEES`: Nippon India ETF Gold BeES
- `ITBEES`: Nippon India ETF Nifty IT
- `JUNIORBEES`: Nippon India ETF Nifty Next 50

## ⚖️ SEBI Compliance & Safety
- **Risk Warning**: Always displayed before simulated or real order placement.
- **Static IP**: Mandatory for broker API-based order placement (Zerodha/Upstox) as of April 2026.
- **Market Hours**: NSE operates 9:15 AM – 3:30 PM IST, Monday–Friday.

---
Built with ❤️ for Indian ETF Traders.
