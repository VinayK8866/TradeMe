const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

export async function fetchPrice(symbol: string) {
  const response = await fetch(`${API_URL}/api/v1/prices/${symbol}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch price for ${symbol}`);
  }
  return response.json();
}

export async function fetchSignals() {
  const response = await fetch(`${API_URL}/api/v1/signals/`);
  if (!response.ok) {
    throw new Error('Failed to fetch signals');
  }
  return response.json();
}

export async function fetchExplanation(signal: any) {
  const response = await fetch(`${API_URL}/api/v1/explain/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ signal }),
  });
  if (!response.ok) {
    throw new Error('Failed to fetch explanation');
  }
  return response.json();
}

export async function fetchBacktest(symbol: string) {
  const response = await fetch(`${API_URL}/api/v1/backtest/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ symbol }),
  });
  if (!response.ok) {
    throw new Error('Failed to run backtest');
  }
  return response.json();
}

export async function fetchNews(symbol: string) {
  const response = await fetch(`${API_URL}/api/v1/prices/${symbol}/news`);
  if (!response.ok) {
    throw new Error('Failed to fetch news');
  }
  return response.json();
}

export async function fetchAutoTradeSettings() {
  const response = await fetch(`${API_URL}/api/v1/auto-trade/settings`);
  if (!response.ok) {
    throw new Error('Failed to fetch auto-trade settings');
  }
  return response.json();
}

export async function toggleAutoTrade(symbol: string, enabled: boolean) {
  const response = await fetch(`${API_URL}/api/v1/auto-trade/toggle`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ symbol, enabled }),
  });
  if (!response.ok) {
    throw new Error('Failed to toggle auto-trade');
  }
  return response.json();
}

// ─── Crypto Bot API Helpers ──────────────────────────────────────────────────

export async function fetchCryptoCoins() {
  const response = await fetch(`${API_URL}/api/v1/crypto/coins`);
  if (!response.ok) throw new Error('Failed to fetch crypto coins');
  return response.json();
}

export async function fetchCryptoSignals() {
  const response = await fetch(`${API_URL}/api/v1/crypto/signals`);
  if (!response.ok) throw new Error('Failed to fetch crypto signals');
  return response.json();
}

export async function fetchCryptoSignalDetails(symbol: string) {
  const response = await fetch(`${API_URL}/api/v1/crypto/signals/${symbol}`);
  if (!response.ok) throw new Error(`Failed to fetch signal details for ${symbol}`);
  return response.json();
}

export async function fetchCryptoPortfolioSummary() {
  const response = await fetch(`${API_URL}/api/v1/crypto/portfolio/summary`);
  if (!response.ok) throw new Error('Failed to fetch crypto portfolio summary');
  return response.json();
}

export async function fetchCryptoTrades() {
  const response = await fetch(`${API_URL}/api/v1/crypto/portfolio/trades`);
  if (!response.ok) throw new Error('Failed to fetch crypto trades');
  return response.json();
}

export async function fetchCryptoStats() {
  const response = await fetch(`${API_URL}/api/v1/crypto/portfolio/stats`);
  if (!response.ok) throw new Error('Failed to fetch crypto stats');
  return response.json();
}

export async function fetchCryptoBotStatus() {
  const response = await fetch(`${API_URL}/api/v1/crypto/bot/status`);
  if (!response.ok) throw new Error('Failed to fetch bot status');
  return response.json();
}

export async function startCryptoBot() {
  const response = await fetch(`${API_URL}/api/v1/crypto/bot/start`, { method: 'POST' });
  if (!response.ok) throw new Error('Failed to start crypto bot');
  return response.json();
}

export async function stopCryptoBot() {
  const response = await fetch(`${API_URL}/api/v1/crypto/bot/stop`, { method: 'POST' });
  if (!response.ok) throw new Error('Failed to stop crypto bot');
  return response.json();
}

export async function resumeCryptoBot() {
  const response = await fetch(`${API_URL}/api/v1/crypto/bot/resume`, { method: 'POST' });
  if (!response.ok) throw new Error('Failed to resume crypto bot');
  return response.json();
}

export async function triggerCryptoBotCycle() {
  const response = await fetch(`${API_URL}/api/v1/crypto/bot/cycle`, { method: 'POST' });
  if (!response.ok) throw new Error('Failed to manually trigger bot cycle');
  return response.json();
}

export async function switchCryptoBotMode(mode: 'paper' | 'live') {
  const response = await fetch(`${API_URL}/api/v1/crypto/bot/mode/${mode}`, { method: 'POST' });
  if (!response.ok) throw new Error(`Failed to switch mode to ${mode}`);
  return response.json();
}

export async function updateCryptoBotSettings(settings: any) {
  const response = await fetch(`${API_URL}/api/v1/crypto/bot/settings`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(settings),
  });
  if (!response.ok) throw new Error('Failed to update bot settings');
  return response.json();
}

export async function fetchCryptoTimingAdvisory() {
  const response = await fetch(`${API_URL}/api/v1/crypto/bot/timing-advisory`);
  if (!response.ok) throw new Error('Failed to fetch timing advisory');
  return response.json();
}

export async function fetchTradeMemory(tradeId: number) {
  const response = await fetch(`${API_URL}/api/v1/crypto/trades/${tradeId}/memory`);
  if (!response.ok) throw new Error(`Failed to fetch trade memory for ID ${tradeId}`);
  return response.json();
}

