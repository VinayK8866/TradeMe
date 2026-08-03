#!/usr/bin/env bash

# Start script for India ETF Trading Platform & Crypto Bot

echo "=================================================="
echo " Starting TradeMe System"
echo "=================================================="

# Detect docker-compose command (v1 vs v2)
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo "[!] Neither docker-compose nor 'docker compose' plugin was found."
    exit 1
fi

echo "[1/2] Starting TimescaleDB & Redis containers..."
$DOCKER_COMPOSE -f docker-compose-deps.yml up -d

MODE="${1:-run}"

if [ "$MODE" == "docker-build" ]; then
    echo "[+] Launching container stack via Docker Compose..."
    $DOCKER_COMPOSE up --build
else
    echo "[2/2] Starting Backend, Frontend, and Celery Scheduler..."
    echo "    - FastAPI Backend: http://localhost:8000"
    echo "    - Next.js Frontend: http://localhost:3000"
    echo ""
    echo "Press Ctrl+C to stop all services."
    echo ""

    # Clean shutdown on Ctrl+C
    cleanup() {
        echo ""
        echo "[!] Shutting down local services..."
        pkill -P $$ 2>/dev/null
        exit 0
    }
    trap cleanup SIGINT SIGTERM

    # 1. Backend
    (cd backend && ./venv/bin/uvicorn main:app --reload --port 8000) &
    BACKEND_PID=$!

    # 2. Celery Worker & Scheduler
    (cd backend && ./venv/bin/celery -A tasks.scheduler worker --loglevel=info) &
    CELERY_PID=$!

    # 3. Frontend
    (cd frontend && npm run dev) &
    FRONTEND_PID=$!

    wait
fi
