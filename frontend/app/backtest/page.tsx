'use client';

import React, { useState } from 'react';
import { fetchBacktest } from '@/lib/api';
import { ChevronLeft, FlaskConical, TrendingUp, TrendingDown, Target, BarChart3, Clock, Wallet, Activity, Info } from 'lucide-react';

export default function BacktestPage() {
  const [symbol, setSymbol] = useState('NIFTYBEES');
  const [results, setResults] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRunBacktest = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBacktest(symbol);
      if (data.success) {
        setResults(data.data);
      } else {
        setError(data.data.error || 'Backtest failed');
      }
    } catch (err) {
      setError('Failed to connect to backend.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-background text-foreground selection:bg-blue-500/30">
      {/* Background Glow */}
      <div className="fixed top-0 left-0 w-full h-full overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-indigo-900/10 blur-[120px] rounded-full" />
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8 relative z-10">
        <header className="mb-12 flex justify-between items-center border-b border-white/5 pb-8">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="bg-indigo-600 p-2 rounded-lg shadow-[0_0_15px_rgba(79,70,229,0.4)]">
                <FlaskConical className="w-5 h-5 text-white" />
              </div>
              <h1 className="text-3xl font-bold tracking-tight">Strategy <span className="text-indigo-400">Lab</span></h1>
            </div>
            <p className="text-zinc-400 text-sm">Historical performance analytics for Indian NSE ETFs</p>
          </div>
          <a href="/" className="flex items-center gap-2 text-zinc-400 hover:text-white transition-colors text-sm font-medium">
            <ChevronLeft className="w-4 h-4" /> Back to Dashboard
          </a>
        </header>

        <section className="glass-card p-8 mb-8">
          <form onSubmit={handleRunBacktest} className="grid grid-cols-1 md:grid-cols-3 gap-6 items-end">
            <div>
              <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-3">Target Instrument</label>
              <select 
                value={symbol} 
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full p-3 bg-white/5 border border-white/10 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 outline-none transition-all hover:bg-white/10"
              >
                <option value="NIFTYBEES">NIFTYBEES (Nifty 50)</option>
                <option value="GOLDBEES">GOLDBEES (Gold)</option>
                <option value="ITBEES">ITBEES (Nifty IT)</option>
                <option value="JUNIORBEES">JUNIORBEES (Nifty Next 50)</option>
                <option value="KOTAKBKETF">KOTAKBKETF (Bank Nifty)</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-3">Simulation Capital</label>
              <div className="relative">
                <Wallet className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <input type="text" value="₹ 1,00,000" disabled className="w-full p-3 pl-10 bg-white/5 border border-white/10 rounded-xl text-sm text-zinc-400" />
              </div>
            </div>
            <button 
              type="submit" 
              disabled={loading}
              className="trading-btn bg-indigo-600 text-white hover:bg-indigo-500 shadow-[0_0_20px_rgba(79,70,229,0.2)] h-[46px]"
            >
              {loading ? 'Processing Data...' : 'Run Simulation'}
            </button>
          </form>
        </section>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 p-4 rounded-xl text-red-400 text-sm mb-8 animate-in fade-in slide-in-from-top-2">
            {error}
          </div>
        )}

        {results && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="glass-card p-8 border-indigo-500/20 bg-indigo-500/5 mb-8">
              <div className="flex justify-between items-center mb-8">
                <h2 className="text-xl font-bold flex items-center gap-3">
                  Simulation Report: {results.symbol}
                  <span className={`text-xs px-3 py-1 rounded-full border ${results.return_percent >= 0 ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
                    {results.return_percent}% Total Return
                  </span>
                </h2>
                <div className="text-zinc-500 text-[10px] font-bold uppercase tracking-widest">
                  Period: {results.start.split(' ')[0]} to {results.end.split(' ')[0]}
                </div>
              </div>
              
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                <StatCard icon={<Wallet className="w-4 h-4" />} label="Final Equity" value={`₹${results.equity_final.toLocaleString()}`} isPositive={results.equity_final >= 100000} />
                <StatCard icon={<Target className="w-4 h-4" />} label="Win Rate" value={`${results.win_rate}%`} />
                <StatCard icon={<TrendingDown className="w-4 h-4" />} label="Max Drawdown" value={`${results.max_drawdown}%`} />
                <StatCard icon={<BarChart3 className="w-4 h-4" />} label="Total Trades" value={results.trades_count} />
                <StatCard icon={<Activity className="w-4 h-4" />} label="Sharpe Ratio" value={results.sharpe_ratio} />
                <StatCard icon={<TrendingUp className="w-4 h-4" />} label="B&H Return" value={`${results.buy_hold_return}%`} />
                <StatCard icon={<Clock className="w-4 h-4" />} label="Duration" value="1 Year" />
                <StatCard icon={<FlaskConical className="w-4 h-4" />} label="Strategy" value="SMA-50 Cross" />
              </div>
            </div>

            <div className="p-6 rounded-xl border border-white/5 bg-white/2">
               <h3 className="text-sm font-bold mb-4 text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                 <Info className="w-4 h-4" /> Lab Conclusion
               </h3>
               <p className="text-sm text-zinc-500 leading-relaxed">
                 Based on the historical performance of {results.symbol}, this strategy {results.return_percent > results.buy_hold_return ? 'outperformed' : 'underperformed'} a simple Buy & Hold approach. {results.max_drawdown > 15 ? 'Caution is advised due to high volatility and significant drawdown periods.' : 'The strategy shows stable risk-adjusted returns with manageable drawdown.'}
               </p>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

function StatCard({ label, value, icon, isPositive }: { label: string; value: any; icon: React.ReactNode; isPositive?: boolean }) {
  return (
    <div className="p-4 bg-white/5 rounded-xl border border-white/5 hover:border-white/10 transition-colors group">
      <div className="flex items-center gap-2 text-zinc-500 mb-2 group-hover:text-zinc-400 transition-colors">
        {icon}
        <div className="text-[10px] font-bold uppercase tracking-wider">{label}</div>
      </div>
      <div className={`text-xl font-bold terminal-font ${isPositive !== undefined ? (isPositive ? 'text-emerald-400' : 'text-red-400') : 'text-white'}`}>
        {value}
      </div>
    </div>
  );
}

