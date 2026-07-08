'use client';

import React, { useEffect, useState, useRef } from 'react';
import { PriceCard } from '@/components/PriceCard';
import { fetchSignals, fetchAutoTradeSettings } from '@/lib/api';
import { VixMeter } from '@/components/VixMeter';
import { Wifi, WifiOff, LayoutDashboard, History, Zap, Activity, ShieldCheck } from 'lucide-react';

export default function Dashboard() {
  const [signals, setSignals] = useState<any[]>([]);
  const [livePrices, setLivePrices] = useState<Record<string, any>>({});
  const [autoTradeSettings, setAutoTradeSettings] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isLive, setIsLive] = useState(false);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      
      // Load Signals
      try {
        const signalsData = await fetchSignals();
        if (signalsData.success) {
          setSignals(signalsData.data);
        } else {
          console.warn("Signals API returned success:false", signalsData.error);
        }
      } catch (err) {
        console.error("Failed to fetch signals:", err);
        setError('Market data connection failed. Check backend.');
      }

      // Load Settings (Non-blocking)
      try {
        const settingsData = await fetchAutoTradeSettings();
        if (settingsData.success) {
          const settingsMap: Record<string, any> = {};
          settingsData.data.forEach((s: any) => {
            settingsMap[s.symbol] = s;
          });
          setAutoTradeSettings(settingsMap);
        }
      } catch (err) {
        console.warn("Failed to fetch auto-trade settings:", err);
      }

      setLoading(false);
    }

    loadData();

    // Connect to WebSocket
    const connectWS = () => {
      ws.current = new WebSocket('ws://localhost:8080/ws/prices');
      
      ws.current.onopen = () => {
        setIsLive(true);
      };

      ws.current.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === 'PRICE_UPDATE') {
          const updates: Record<string, any> = {};
          message.data.forEach((item: any) => {
            updates[item.symbol] = item;
          });
          setLivePrices((prev) => ({ ...prev, ...updates }));
        }
      };

      ws.current.onclose = () => {
        setIsLive(false);
        // Reconnect after 3 seconds
        setTimeout(connectWS, 3000);
      };
    };

    connectWS();

    return () => {
      if (ws.current) ws.current.close();
    };
  }, []);

  const anyAutoTradeActive = Object.values(autoTradeSettings).some((s: any) => s.auto_trade_enabled);

  return (
    <main className="min-h-screen bg-background text-foreground selection:bg-blue-500/30">
      {/* Background Glow */}
      <div className="fixed top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-900/20 blur-[120px] rounded-full" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-indigo-900/10 blur-[120px] rounded-full" />
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8 relative z-10">
        <header className="mb-12 flex flex-col md:flex-row justify-between items-start md:items-center gap-8 border-b border-white/5 pb-8">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="bg-blue-600 p-2 rounded-lg shadow-[0_0_15px_rgba(37,99,235,0.4)]">
                <Zap className="w-5 h-5 text-white" />
              </div>
              <h1 className="text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-white/60">
                TradeMe <span className="text-blue-500">Pro</span>
              </h1>
              {anyAutoTradeActive && (
                <div className="flex items-center gap-1.5 px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-full text-[10px] font-bold text-emerald-400 uppercase tracking-widest animate-pulse">
                  <ShieldCheck className="w-3 h-3" /> Autonomous Active
                </div>
              )}
            </div>
            <p className="text-zinc-400 flex items-center gap-2 text-sm font-medium">
              {isLive ? (
                <span className="flex items-center gap-1.5 text-emerald-500">
                  <Wifi className="w-4 h-4 animate-pulse" /> Live Market Signals (NSE)
                </span>
              ) : (
                <span className="flex items-center gap-1.5 text-zinc-500">
                  <WifiOff className="w-4 h-4" /> Delayed Data (yfinance)
                </span>
              )}
            </p>
          </div>
          
          <div className="flex flex-wrap gap-4 items-center">
            <VixMeter />
            <div className="h-8 w-px bg-white/10 mx-2 hidden md:block" />
            <nav className="flex gap-2">
              <a href="/" className="flex items-center gap-2 bg-white/10 px-4 py-2 rounded-lg transition-all text-sm font-medium border border-blue-500/30 text-blue-400">
                <LayoutDashboard className="w-4 h-4" /> Dashboard
              </a>
              <a href="/backtest" className="flex items-center gap-2 bg-white/5 hover:bg-white/10 px-4 py-2 rounded-lg transition-all text-sm font-medium border border-white/5">
                <History className="w-4 h-4" /> Strategy Lab
              </a>
            </nav>
          </div>
        </header>

        {loading ? (
          <div className="flex flex-col justify-center items-center h-96 gap-4">
            <div className="w-12 h-12 border-2 border-blue-500/20 border-t-blue-500 rounded-full animate-spin"></div>
            <p className="text-zinc-500 animate-pulse text-sm font-medium uppercase tracking-widest">Initalizing Terminal...</p>
          </div>
        ) : error ? (
          <div className="bg-red-500/10 border border-red-500/20 p-6 rounded-xl text-red-400 flex flex-col items-center text-center gap-4">
            <p className="font-medium">{error}</p>
            <button onClick={() => window.location.reload()} className="text-xs underline hover:text-red-300">Retry Connection</button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {signals.map((s) => (
              <PriceCard
                key={s.symbol}
                symbol={s.symbol}
                price={livePrices[s.symbol]?.price || s.ma50} 
                change={livePrices[s.symbol]?.change || 0}
                changePercent={livePrices[s.symbol]?.change_percent || 0}
                signalData={s}
                isAutoTradeEnabled={autoTradeSettings[s.symbol]?.auto_trade_enabled}
              />
            ))}
          </div>
        )}

        <section className="mt-16 glass-card p-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-8 h-1 bg-blue-500 rounded-full"></div>
            <h2 className="text-lg font-bold tracking-tight">System Compliance & Status</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-4 bg-white/5 rounded-xl border border-white/5">
              <p className="text-zinc-400 text-xs font-bold uppercase tracking-wider mb-2">NSE Connectivity</p>
              <p className="text-sm font-medium">9:15 AM – 3:30 PM IST</p>
              <p className="text-xs text-zinc-500 mt-1">Market is currently CLOSED</p>
            </div>
            <div className="p-4 bg-white/5 rounded-xl border border-white/5">
              <p className="text-zinc-400 text-xs font-bold uppercase tracking-wider mb-2">Broker Gateway</p>
              <p className="text-sm font-medium text-amber-500">Paper Trading Mode Only</p>
              <p className="text-xs text-zinc-500 mt-1">Zerodha API integration pending</p>
            </div>
            <div className="p-4 bg-white/5 rounded-xl border border-white/5">
              <p className="text-zinc-400 text-xs font-bold uppercase tracking-wider mb-2">Regulatory Check</p>
              <p className="text-sm font-medium">SEBI Compliant (v2.4)</p>
              <p className="text-xs text-zinc-500 mt-1">Static IP requirement active</p>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
