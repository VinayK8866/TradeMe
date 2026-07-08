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
