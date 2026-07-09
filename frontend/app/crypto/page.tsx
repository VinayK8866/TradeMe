'use client';

import React, { useEffect, useState, useRef } from 'react';
import { 
  Wifi, WifiOff, LayoutDashboard, History, Zap, Activity, 
  ShieldCheck, AlertOctagon, RefreshCw, Play, Pause, Settings,
  TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight, Info,
  BookOpen, Eye, Clock, HelpCircle, ShieldAlert, BadgeInfo
} from 'lucide-react';
import { 
  fetchCryptoSignals, 
  fetchCryptoPortfolioSummary, 
  fetchCryptoStats, 
  fetchCryptoBotStatus,
  startCryptoBot, 
  stopCryptoBot, 
  resumeCryptoBot, 
  triggerCryptoBotCycle, 
  switchCryptoBotMode,
  updateCryptoBotSettings,
  fetchCryptoTimingAdvisory,
  fetchTradeMemory
} from '@/lib/api';

export default function CryptoDashboard() {
  // Stats & Bot state
  const [portfolio, setPortfolio] = useState<any>(null);
  const [signals, setSignals] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [botStatus, setBotStatus] = useState<any>(null);
  const [timingAdvisory, setTimingAdvisory] = useState<string>('');
  
  // Loading & UI
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedCoin, setSelectedCoin] = useState<any>(null);
  const [selectedTradeMemory, setSelectedTradeMemory] = useState<any>(null);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [advisoryLoading, setAdvisoryLoading] = useState(false);

  // Settings form states
  const [capitalInput, setCapitalInput] = useState('5000');
  const [stopLossInput, setStopLossInput] = useState('5');
  const [startHourInput, setStartHourInput] = useState('9');
  const [endHourInput, setEndHourInput] = useState('24');
  const [maxPositionsInput, setMaxPositionsInput] = useState('3');

  // Load everything
  const loadDashboardData = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    try {
      const [portData, sigData, statsData, botData, advisoryData] = await Promise.all([
        fetchCryptoPortfolioSummary().catch(() => ({ success: false, data: null })),
        fetchCryptoSignals().catch(() => ({ success: false, data: { signals: [] } })),
        fetchCryptoStats().catch(() => ({ success: false, data: null })),
        fetchCryptoBotStatus().catch(() => ({ success: false, data: null })),
        fetchCryptoTimingAdvisory().catch(() => ({ success: false, data: { advisory: '' } }))
      ]);

      if (portData.success && portData.data) setPortfolio(portData.data);
      if (sigData.success && sigData.data) setSignals(sigData.data.signals);
      if (statsData.success && statsData.data) setStats(statsData.data);
      if (botData.success && botData.data) {
        setBotStatus(botData.data);
        setCapitalInput(String(botData.data.portfolio_capital_inr));
        setStopLossInput(String(botData.data.stop_loss_percent));
        setMaxPositionsInput(String(botData.data.max_simultaneous_positions));
      }
      if (advisoryData.success && advisoryData.data) setTimingAdvisory(advisoryData.data.advisory);

    } catch (err) {
      console.error("Failed to load crypto dashboard data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
    // Poll data every 30 seconds
    const interval = setInterval(() => {
      loadDashboardData(false);
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // Bot operations handlers
  const handleStartBot = async () => {
    setActionLoading(true);
    try {
      const res = await startCryptoBot();
      if (res.success) {
        await loadDashboardData(false);
      } else {
        alert(res.error || "Failed to start bot");
      }
    } catch (err) {
      alert("Error starting bot: " + err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStopBot = async () => {
    setActionLoading(true);
    try {
      const res = await stopCryptoBot();
      if (res.success) {
        await loadDashboardData(false);
      }
    } catch (err) {
      alert("Error stopping bot: " + err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResumeBot = async () => {
    setActionLoading(true);
    try {
      const res = await resumeCryptoBot();
      if (res.success) {
        await loadDashboardData(false);
      } else {
        alert(res.error || "Failed to resume bot");
      }
    } catch (err) {
      alert("Error resuming bot: " + err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleTriggerCycle = async () => {
    setActionLoading(true);
    try {
      const res = await triggerCryptoBotCycle();
      if (res.success) {
        await loadDashboardData(false);
        alert(`Bot cycle triggered successfully!\nOpened: ${res.data?.positions_opened?.length || 0} position(s)\nClosed: ${res.data?.positions_closed?.length || 0} position(s)`);
      } else {
        alert("Failed to run manual cycle: " + res.error);
      }
    } catch (err) {
      alert("Error running cycle: " + err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSwitchMode = async (mode: 'paper' | 'live') => {
    setActionLoading(true);
    try {
      const res = await switchCryptoBotMode(mode);
      if (res.success) {
        await loadDashboardData(false);
      } else {
        alert(res.error || `Failed to switch to ${mode} mode`);
      }
    } catch (err) {
      alert("Error switching mode: " + err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionLoading(true);
    try {
      const res = await updateCryptoBotSettings({
        portfolio_capital_inr: parseFloat(capitalInput),
        stop_loss_percent: parseFloat(stopLossInput),
        trading_start_hour: parseInt(startHourInput),
        trading_end_hour: parseInt(endHourInput),
        max_simultaneous_positions: parseInt(maxPositionsInput)
      });
      if (res.success) {
        setShowSettingsModal(false);
        await loadDashboardData(false);
      } else {
        alert(res.error || "Failed to update settings");
      }
    } catch (err) {
      alert("Error updating settings: " + err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleViewTradeMemory = async (tradeId: number) => {
    try {
      const res = await fetchTradeMemory(tradeId);
      if (res.success && res.data) {
        setSelectedTradeMemory(res.data);
      }
    } catch (err) {
      alert("No AI memory report available for this trade ID yet.");
    }
  };

  return (
    <main className="min-h-screen bg-background text-foreground selection:bg-purple-500/30">
      {/* Background Glow */}
      <div className="fixed top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] right-[-10%] w-[50%] h-[50%] bg-purple-900/10 blur-[130px] rounded-full" />
        <div className="absolute bottom-[-10%] left-[-10%] w-[50%] h-[50%] bg-blue-900/15 blur-[130px] rounded-full" />
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8 relative z-10">
        {/* Header */}
        <header className="mb-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-8 border-b border-white/5 pb-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="bg-purple-600 p-2 rounded-lg shadow-[0_0_15px_rgba(147,51,234,0.4)]">
                <Zap className="w-5 h-5 text-white" />
              </div>
              <h1 className="text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-white to-purple-400">
                Antigravity <span className="text-purple-400 font-mono text-2xl">Crypto</span>
              </h1>
              {botStatus?.is_running && (
                <div className="flex items-center gap-1.5 px-3 py-1 bg-purple-500/10 border border-purple-500/20 rounded-full text-[10px] font-bold text-purple-400 uppercase tracking-widest animate-pulse">
                  <ShieldCheck className="w-3 h-3" /> Autonomous Active
                </div>
              )}
            </div>
            <p className="text-zinc-400 flex items-center gap-2 text-sm font-medium">
              <span className="flex items-center gap-1.5 text-purple-400">
                <Wifi className="w-4 h-4" /> Live Market Tracking (CoinGecko)
              </span>
            </p>
          </div>
          
          <div className="flex flex-wrap gap-4 items-center">
            <nav className="flex gap-2">
              <a href="/" className="flex items-center gap-2 bg-white/5 hover:bg-white/10 px-4 py-2 rounded-lg transition-all text-sm font-medium border border-white/5">
                <LayoutDashboard className="w-4 h-4" /> NSE ETF Pro
              </a>
              <a href="/crypto" className="flex items-center gap-2 bg-purple-600/10 px-4 py-2 rounded-lg transition-all text-sm font-medium border border-purple-500/30 text-purple-400">
                <Activity className="w-4 h-4" /> Crypto Bot
              </a>
            </nav>
          </div>
        </header>

        {loading ? (
          <div className="flex flex-col justify-center items-center h-96 gap-4">
            <div className="w-12 h-12 border-2 border-purple-500/20 border-t-purple-500 rounded-full animate-spin"></div>
            <p className="text-zinc-500 animate-pulse text-sm font-medium uppercase tracking-widest">Waking Up AI Brain...</p>
          </div>
        ) : (
          <>
            {/* Drawdown emergency banner */}
            {botStatus?.is_stopped_by_loss && (
              <div className="mb-8 p-6 bg-red-950/20 border border-red-500/40 rounded-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-6 shadow-[0_0_30px_rgba(239,68,68,0.05)]">
                <div className="flex items-start gap-4">
                  <div className="bg-red-500/20 p-3 rounded-lg border border-red-500/30 text-red-400">
                    <ShieldAlert className="w-6 h-6 animate-bounce" />
                  </div>
                  <div>
                    <h3 className="font-bold text-lg text-white mb-1">Emergency Drawdown Stop-Loss Breached</h3>
                    <p className="text-sm text-zinc-300">
                      Total portfolio value dropped &gt;{botStatus?.stop_loss_percent}% from starting capital. All positions were automatically liquidated.
                    </p>
                    <p className="text-xs text-red-400 mt-2 font-mono">
                      Triggered at: {botStatus?.stop_loss_triggered_at ? new Date(botStatus.stop_loss_triggered_at).toLocaleString() : 'N/A'}
                    </p>
                  </div>
                </div>
                <button
                  onClick={handleResumeBot}
                  disabled={actionLoading}
                  className="px-6 py-3 bg-red-600 hover:bg-red-500 transition-all font-bold text-white rounded-lg text-sm shadow-[0_0_15px_rgba(220,38,38,0.4)] disabled:opacity-50"
                >
                  Resume Trading
                </button>
              </div>
            )}

            {/* Top row: Portfolio Summary & Stats */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
              {/* Portfolio Value summary */}
              <div className="glass-card p-6 flex flex-col justify-between lg:col-span-2">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="text-xs text-zinc-400 font-bold uppercase tracking-wider mb-1">
                      {portfolio?.mode?.toUpperCase()} PORTFOLIO VALUE
                    </p>
                    <h2 className="text-4xl font-mono font-bold text-white">
                      ₹{portfolio?.total_value_inr?.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </h2>
                    <div className="flex gap-4 mt-2">
                      <span className={`flex items-center gap-1 text-sm font-semibold ${portfolio?.unrealized_pnl_inr >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {portfolio?.unrealized_pnl_inr >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                        {portfolio?.unrealized_pnl_inr >= 0 ? '+' : ''}{portfolio?.unrealized_pnl_pct}% (₹{portfolio?.unrealized_pnl_inr?.toFixed(2)})
                      </span>
                      <span className="text-xs text-zinc-500 font-medium">starting capital: ₹{portfolio?.starting_capital_inr?.toLocaleString('en-IN')}</span>
                    </div>
                  </div>
                  
                  {/* Mode Selector */}
                  <div className="flex bg-white/5 border border-white/5 rounded-lg p-0.5">
                    <button
                      onClick={() => handleSwitchMode('paper')}
                      disabled={botStatus?.is_running}
                      className={`px-3 py-1 text-xs font-bold rounded-md transition-all ${portfolio?.mode === 'paper' ? 'bg-purple-600 text-white shadow-sm' : 'text-zinc-400 hover:text-zinc-200'}`}
                    >
                      PAPER
                    </button>
                    <button
                      onClick={() => handleSwitchMode('live')}
                      disabled={botStatus?.is_running || !botStatus?.graduation_ready}
                      className={`px-3 py-1 text-xs font-bold rounded-md transition-all relative ${portfolio?.mode === 'live' ? 'bg-amber-600 text-white shadow-sm' : 'text-zinc-500'} ${!botStatus?.graduation_ready ? 'cursor-not-allowed opacity-55' : ''}`}
                      title={!botStatus?.graduation_ready ? "Graduation target not met" : ""}
                    >
                      LIVE
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 pt-6 border-t border-white/5 mt-6">
                  <div>
                    <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Cash Available</span>
                    <span className="font-mono text-lg font-bold text-zinc-200">₹{portfolio?.cash_inr?.toLocaleString('en-IN')}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Currently Invested</span>
                    <span className="font-mono text-lg font-bold text-zinc-200">₹{portfolio?.invested_inr?.toLocaleString('en-IN')}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Realized Net profit</span>
                    <span className={`font-mono text-lg font-bold ${portfolio?.realized_pnl_inr >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      ₹{portfolio?.realized_pnl_inr?.toLocaleString('en-IN')}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Open Positions</span>
                    <span className="font-mono text-lg font-bold text-zinc-200">{portfolio?.open_count} / {botStatus?.max_simultaneous_positions}</span>
                  </div>
                </div>
              </div>

              {/* Bot controls card */}
              <div className="glass-card p-6 flex flex-col justify-between border-purple-500/10 bg-purple-500/2">
                <div>
                  <h3 className="text-zinc-400 text-xs font-bold uppercase tracking-wider mb-4 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-purple-400" /> Bot Execution Controls
                  </h3>
                  <div className="flex flex-col gap-3">
                    {botStatus?.is_running ? (
                      <button
                        onClick={handleStopBot}
                        disabled={actionLoading}
                        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-zinc-800 hover:bg-zinc-700 transition-all font-bold text-white rounded-lg text-sm border border-zinc-700"
                      >
                        <Pause className="w-4 h-4 fill-white" /> Pause Bot Engine
                      </button>
                    ) : (
                      <button
                        onClick={handleStartBot}
                        disabled={actionLoading || botStatus?.is_stopped_by_loss}
                        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-500 transition-all font-bold text-white rounded-lg text-sm shadow-[0_0_15px_rgba(147,51,234,0.3)] disabled:opacity-50"
                      >
                        <Play className="w-4 h-4 fill-white" /> Start Bot Engine
                      </button>
                    )}
                    
                    <button
                      onClick={handleTriggerCycle}
                      disabled={actionLoading}
                      className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-white/5 hover:bg-white/10 transition-all text-zinc-300 font-semibold rounded-lg text-xs border border-white/5"
                    >
                      <RefreshCw className="w-3.5 h-3.5" /> Manual Scan Cycle
                    </button>
                  </div>
                </div>

                <div className="pt-6 border-t border-white/5 flex justify-between items-center text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-zinc-500 font-medium">IST Window:</span>
                    <span className="text-zinc-300 font-bold font-mono">{botStatus?.trading_hours}</span>
                  </div>
                  <button 
                    onClick={() => setShowSettingsModal(true)}
                    className="p-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/5 transition-all text-zinc-400 hover:text-white"
                    title="Bot Settings"
                  >
                    <Settings className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {/* Holdings & Signal scanner section */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
              {/* Crypto Holdings list */}
              <div className="glass-card p-6 lg:col-span-2">
                <div className="flex justify-between items-center mb-6">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-1 bg-purple-500 rounded-full" />
                    <h2 className="font-bold text-lg text-white">Live open positions</h2>
                  </div>
                </div>
                {portfolio?.open_count === 0 ? (
                  <div className="flex flex-col justify-center items-center py-16 text-zinc-500">
                    <BadgeInfo className="w-8 h-8 mb-2 opacity-50" />
                    <p className="text-sm font-medium">No open positions. Running technical scans...</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm border-collapse">
                      <thead>
                        <tr className="border-b border-white/5 text-zinc-500 text-xs font-bold uppercase">
                          <th className="py-3">Coin</th>
                          <th className="py-3">Quantity</th>
                          <th className="py-3">Avg Buy</th>
                          <th className="py-3">Live Price</th>
                          <th className="py-3 text-right">Stop Loss</th>
                          <th className="py-3 text-right">P&L</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {portfolio?.positions?.map((p: any) => {
                          const pnlPositive = p.pnl_inr >= 0;
                          return (
                            <tr key={p.symbol} className="hover:bg-white/[0.01] transition-all">
                              <td className="py-4">
                                <div className="flex items-center gap-2">
                                  <span className="font-bold text-white">{p.symbol}</span>
                                  <span className="px-1.5 py-0.5 bg-purple-500/10 text-[9px] font-bold text-purple-400 rounded-md border border-purple-500/20">
                                    {p.strategy_used}
                                  </span>
                                </div>
                              </td>
                              <td className="py-4 font-mono text-zinc-300">{p.quantity.toFixed(4)}</td>
                              <td className="py-4 font-mono text-zinc-300">₹{p.avg_buy_price_inr.toLocaleString('en-IN')}</td>
                              <td className="py-4 font-mono text-zinc-300">₹{p.current_price_inr.toLocaleString('en-IN')}</td>
                              <td className="py-4 font-mono text-red-400 text-right">₹{p.stop_loss_price_inr.toLocaleString('en-IN')}</td>
                              <td className={`py-4 font-mono font-bold text-right ${pnlPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                                {pnlPositive ? '+' : ''}{p.pnl_pct}%
                                <span className="block text-[10px] font-medium text-zinc-500">₹{p.pnl_inr.toFixed(2)}</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Timing Advisor */}
              <div className="glass-card p-6 flex flex-col justify-between border-purple-500/5">
                <div>
                  <h3 className="text-zinc-400 text-xs font-bold uppercase tracking-wider mb-4 flex items-center gap-2">
                    <Clock className="w-4 h-4 text-purple-400" /> Daily Timing Advisory
                  </h3>
                  <div className="text-sm text-zinc-300 leading-relaxed max-h-[220px] overflow-y-auto pr-1">
                    {timingAdvisory ? (
                      <div className="space-y-3 prose prose-invert">
                        {timingAdvisory.split('\n\n').map((para, i) => {
                          if (para.startsWith('###')) {
                            return <h4 key={i} className="text-sm font-bold text-purple-400 mt-2">{para.replace('###', '')}</h4>;
                          }
                          return <p key={i} className="text-xs leading-relaxed">{para}</p>;
                        })}
                      </div>
                    ) : (
                      <p className="text-xs text-zinc-500 italic">No advisory compiled for today yet.</p>
                    )}
                  </div>
                </div>

                <div className="pt-4 border-t border-white/5 flex justify-between items-center text-xs text-zinc-500">
                  <span>Based on 30-day volatility peaks</span>
                  <span className="font-semibold text-purple-400">Gemini Brain Sync</span>
                </div>
              </div>
            </div>

            {/* Coin Scanner list */}
            <section className="glass-card p-6 mb-8">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-8 h-1 bg-purple-500 rounded-full" />
                <h2 className="font-bold text-lg text-white">Market Scanner & AI Signals</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {signals.map((s) => {
                  const isBuy = s.signal === 'BUY';
                  const isWatch = s.signal === 'WATCH';
                  return (
                    <div 
                      key={s.symbol}
                      onClick={() => setSelectedCoin(s)}
                      className={`p-5 rounded-xl border transition-all duration-300 cursor-pointer ${isBuy ? 'border-emerald-500/20 bg-emerald-500/[0.02] hover:border-emerald-500/40 shadow-sm' : 'border-white/5 bg-white/[0.01] hover:border-white/10 hover:bg-white/[0.02]'}`}
                    >
                      <div className="flex justify-between items-start mb-4">
                        <div>
                          <span className="text-[10px] text-zinc-500 font-bold block">RANK #{s.rank}</span>
                          <h4 className="font-bold text-white text-lg tracking-tight mt-0.5">{s.name} <span className="text-zinc-500 font-mono text-sm">{s.symbol}</span></h4>
                        </div>
                        <span className={`px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider ${isBuy ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-400' : isWatch ? 'bg-purple-500/10 border border-purple-500/20 text-purple-400' : 'bg-zinc-800 border border-zinc-700 text-zinc-400'}`}>
                          {s.signal} {s.signal === 'BUY' ? `(${s.confidence}%)` : ''}
                        </span>
                      </div>
                      
                      <div className="flex justify-between items-end">
                        <div>
                          <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block">Price (INR)</span>
                          <span className="font-mono text-lg font-bold text-zinc-200">₹{s.indicators?.close?.toLocaleString('en-IN')}</span>
                        </div>
                        <div className="text-right">
                          <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block">Fit Strategy</span>
                          <span className="text-xs font-semibold text-zinc-400">{s.selected_strategy}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Performance Trade History */}
            <section className="glass-card p-6">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-8 h-1 bg-purple-500 rounded-full" />
                <h2 className="font-bold text-lg text-white">Closed trade memory</h2>
              </div>
              {!stats?.total_trades ? (
                <div className="py-12 text-center text-zinc-500">
                  <p className="text-sm font-medium">No closed trades yet. The learning ledger is currently blank.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm border-collapse">
                    <thead>
                      <tr className="border-b border-white/5 text-zinc-500 text-xs font-bold uppercase">
                        <th className="py-3">Symbol</th>
                        <th className="py-3">Strategy</th>
                        <th className="py-3">Hold Period</th>
                        <th className="py-3">PnL</th>
                        <th className="py-3">Close Reason</th>
                        <th className="py-3 text-right">AI Feedback</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {stats?.best_trade && (
                        <tr className="hover:bg-white/[0.01] transition-all bg-emerald-500/[0.01]">
                          <td className="py-4">
                            <div className="flex items-center gap-1.5">
                              <span className="font-bold text-white">{stats.best_trade.symbol}</span>
                              <span className="px-1.5 py-0.5 bg-emerald-500/10 border border-emerald-500/20 text-[8px] font-bold text-emerald-400 rounded-md uppercase">BEST</span>
                            </div>
                          </td>
                          <td className="py-4 text-zinc-300">{stats.best_trade.strategy}</td>
                          <td className="py-4 text-zinc-400">
                            {stats.best_trade.opened_at ? Math.round((new Date(stats.best_trade.closed_at).getTime() - new Date(stats.best_trade.opened_at).getTime()) / 60000) : 'N/A'} mins
                          </td>
                          <td className="py-4 font-mono font-bold text-emerald-400">+{stats.best_trade.pnl_pct}% (+₹{stats.best_trade.pnl_inr})</td>
                          <td className="py-4 text-zinc-400 text-xs font-mono uppercase">{stats.best_trade.close_reason || 'Signal Reversal'}</td>
                          <td className="py-4 text-right">
                            <button 
                              onClick={() => handleViewTradeMemory(stats.best_trade.id)}
                              className="px-2.5 py-1.5 bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/20 hover:border-purple-500/30 text-purple-400 rounded-lg text-xs font-bold transition-all"
                            >
                              View Brain Explanation
                            </button>
                          </td>
                        </tr>
                      )}
                      {stats?.worst_trade && stats.worst_trade.id !== stats.best_trade?.id && (
                        <tr className="hover:bg-white/[0.01] transition-all bg-red-500/[0.01]">
                          <td className="py-4">
                            <div className="flex items-center gap-1.5">
                              <span className="font-bold text-white">{stats.worst_trade.symbol}</span>
                              <span className="px-1.5 py-0.5 bg-red-500/10 border border-red-500/20 text-[8px] font-bold text-red-400 rounded-md uppercase">WORST</span>
                            </div>
                          </td>
                          <td className="py-4 text-zinc-300">{stats.worst_trade.strategy}</td>
                          <td className="py-4 text-zinc-400">
                            {stats.worst_trade.opened_at ? Math.round((new Date(stats.worst_trade.closed_at).getTime() - new Date(stats.worst_trade.opened_at).getTime()) / 60000) : 'N/A'} mins
                          </td>
                          <td className="py-4 font-mono font-bold text-red-400">{stats.worst_trade.pnl_pct}% (₹{stats.worst_trade.pnl_inr})</td>
                          <td className="py-4 text-zinc-400 text-xs font-mono uppercase">{stats.worst_trade.close_reason || 'Stop Loss'}</td>
                          <td className="py-4 text-right">
                            <button 
                              onClick={() => handleViewTradeMemory(stats.worst_trade.id)}
                              className="px-2.5 py-1.5 bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/20 hover:border-purple-500/30 text-purple-400 rounded-lg text-xs font-bold transition-all"
                            >
                              View Brain Explanation
                            </button>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </div>

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex justify-center items-center z-50 p-4">
          <div className="bg-card border border-white/5 rounded-2xl w-full max-w-md p-6 relative animate-in zoom-in-95 duration-200">
            <h3 className="font-bold text-lg text-white mb-6">Bot Configuration Settings</h3>
            
            <form onSubmit={handleUpdateSettings} className="space-y-4">
              <div>
                <label className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Starting capital (INR)</label>
                <input 
                  type="number" 
                  value={capitalInput}
                  onChange={(e) => setCapitalInput(e.target.value)}
                  className="w-full bg-white/5 border border-white/5 focus:border-purple-500/40 rounded-lg px-3 py-2 text-sm font-mono text-zinc-200 focus:outline-none" 
                  required
                />
              </div>
              
              <div>
                <label className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Portfolio Stop loss limit (%)</label>
                <input 
                  type="number" 
                  value={stopLossInput}
                  onChange={(e) => setStopLossInput(e.target.value)}
                  className="w-full bg-white/5 border border-white/5 focus:border-purple-500/40 rounded-lg px-3 py-2 text-sm font-mono text-zinc-200 focus:outline-none" 
                  required
                />
              </div>

              <div>
                <label className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Max Simultaneous Positions</label>
                <input 
                  type="number" 
                  value={maxPositionsInput}
                  onChange={(e) => setMaxPositionsInput(e.target.value)}
                  className="w-full bg-white/5 border border-white/5 focus:border-purple-500/40 rounded-lg px-3 py-2 text-sm font-mono text-zinc-200 focus:outline-none" 
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">Start Hour (IST)</label>
                  <input 
                    type="number" 
                    value={startHourInput}
                    onChange={(e) => setStartHourInput(e.target.value)}
                    className="w-full bg-white/5 border border-white/5 focus:border-purple-500/40 rounded-lg px-3 py-2 text-sm font-mono text-zinc-200 focus:outline-none" 
                    required
                  />
                </div>
                <div>
                  <label className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider block mb-1">End Hour (IST)</label>
                  <input 
                    type="number" 
                    value={endHourInput}
                    onChange={(e) => setEndHourInput(e.target.value)}
                    className="w-full bg-white/5 border border-white/5 focus:border-purple-500/40 rounded-lg px-3 py-2 text-sm font-mono text-zinc-200 focus:outline-none" 
                    required
                  />
                </div>
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowSettingsModal(false)}
                  className="flex-1 py-2 rounded-lg font-bold text-zinc-400 bg-white/5 hover:bg-white/10 text-sm border border-white/5"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="flex-1 py-2 bg-purple-600 hover:bg-purple-500 transition-all font-bold text-white rounded-lg text-sm shadow-[0_0_10px_rgba(147,51,234,0.3)]"
                >
                  Save Settings
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Coin details modal */}
      {selectedCoin && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex justify-center items-center z-50 p-4">
          <div className="bg-card border border-white/5 rounded-2xl w-full max-w-lg p-6 relative max-h-[90vh] overflow-y-auto animate-in zoom-in-95 duration-200">
            <h3 className="font-bold text-xl text-white mb-2">{selectedCoin.name} <span className="text-zinc-500 font-mono">{selectedCoin.symbol}</span></h3>
            <span className="px-2 py-0.5 bg-purple-500/10 text-[10px] font-bold text-purple-400 rounded-md border border-purple-500/20 uppercase tracking-widest">
              Strategy: {selectedCoin.selected_strategy}
            </span>

            <div className="grid grid-cols-2 gap-4 mt-6">
              <div className="p-3 bg-white/5 rounded-xl border border-white/5">
                <span className="text-[10px] text-zinc-500 font-bold block mb-1">RSI (14)</span>
                <span className="font-mono text-lg font-bold text-zinc-200">{selectedCoin.indicators?.rsi}</span>
              </div>
              <div className="p-3 bg-white/5 rounded-xl border border-white/5">
                <span className="text-[10px] text-zinc-500 font-bold block mb-1">ADX Trend strength</span>
                <span className="font-mono text-lg font-bold text-zinc-200">{selectedCoin.indicators?.adx || 'N/A'}</span>
              </div>
              <div className="p-3 bg-white/5 rounded-xl border border-white/5">
                <span className="text-[10px] text-zinc-500 font-bold block mb-1">Bollinger band Pct</span>
                <span className="font-mono text-lg font-bold text-zinc-200">{selectedCoin.indicators?.bb_pct}</span>
              </div>
              <div className="p-3 bg-white/5 rounded-xl border border-white/5">
                <span className="text-[10px] text-zinc-500 font-bold block mb-1">Volume Ratio</span>
                <span className="font-mono text-lg font-bold text-zinc-200">{selectedCoin.indicators?.vol_ratio}x</span>
              </div>
            </div>

            <div className="mt-6 p-4 bg-purple-600/5 border border-purple-500/20 rounded-xl">
              <h4 className="text-xs font-bold text-purple-400 flex items-center gap-2 mb-2">
                <Info className="w-4 h-4" /> AI PRE-TRADE INTELLIGENCE
              </h4>
              <p className="text-xs text-zinc-300 leading-relaxed italic">
                "{signals.find(s => s.symbol === selectedCoin.symbol)?.pre_trade_note || 'This trade has passed the technical criteria checks. Ready for dynamic scorer.'}"
              </p>
            </div>

            <button
              onClick={() => setSelectedCoin(null)}
              className="w-full mt-6 py-2.5 bg-zinc-800 hover:bg-zinc-700 transition-all font-semibold text-zinc-300 text-sm rounded-xl border border-zinc-700"
            >
              Close Panel
            </button>
          </div>
        </div>
      )}

      {/* Trade Memory Modal */}
      {selectedTradeMemory && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex justify-center items-center z-50 p-4">
          <div className="bg-card border border-white/5 rounded-2xl w-full max-w-lg p-6 relative max-h-[90vh] overflow-y-auto animate-in zoom-in-95 duration-200">
            <h3 className="font-bold text-xl text-white mb-2">AI Trade Analysis <span className="text-purple-400">{selectedTradeMemory.symbol}</span></h3>
            
            <div className="flex gap-4 mt-1 mb-6 text-xs text-zinc-400">
              <span>Strategy: <b>{selectedTradeMemory.strategy_used}</b></span>
              <span>Outcome: <b className={selectedTradeMemory.outcome === 'PROFIT' ? 'text-emerald-400' : 'text-red-400'}>{selectedTradeMemory.outcome}</b></span>
              <span>PnL: <b>{selectedTradeMemory.pnl_percent}%</b></span>
            </div>

            <div className="space-y-4">
              <div className="p-4 bg-white/5 rounded-xl border border-white/5">
                <h4 className="text-xs font-bold text-zinc-300 uppercase tracking-wider mb-2">✅ What Worked</h4>
                <p className="text-xs text-zinc-400 leading-relaxed">{selectedTradeMemory.what_worked || 'No data recorded.'}</p>
              </div>

              <div className="p-4 bg-white/5 rounded-xl border border-white/5">
                <h4 className="text-xs font-bold text-zinc-300 uppercase tracking-wider mb-2">❌ What Failed / Risk Factors</h4>
                <p className="text-xs text-zinc-400 leading-relaxed">{selectedTradeMemory.what_failed || 'No data recorded.'}</p>
              </div>

              <div className="p-4 bg-purple-600/5 border border-purple-500/20 rounded-xl">
                <h4 className="text-xs font-bold text-purple-400 uppercase tracking-wider mb-2">💡 Lesson Extracted</h4>
                <p className="text-xs text-zinc-300 leading-relaxed font-semibold italic">"{selectedTradeMemory.lesson || 'No lesson compiled yet.'}"</p>
              </div>

              {selectedTradeMemory.avoid_pattern && (
                <div className="p-4 bg-red-950/10 border border-red-500/20 rounded-xl">
                  <h4 className="text-xs font-bold text-red-400 uppercase tracking-wider mb-2">⚠️ Avoid Pattern Registered</h4>
                  <p className="text-xs text-red-300 leading-relaxed font-mono">{selectedTradeMemory.avoid_pattern}</p>
                </div>
              )}
            </div>

            <button
              onClick={() => setSelectedTradeMemory(null)}
              className="w-full mt-6 py-2.5 bg-zinc-800 hover:bg-zinc-700 transition-all font-semibold text-zinc-300 text-sm rounded-xl border border-zinc-700"
            >
              Close Feedback
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
