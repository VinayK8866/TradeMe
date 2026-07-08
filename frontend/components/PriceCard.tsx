import React, { useState } from 'react';
import { SignalBadge } from './SignalBadge';
import { SignalExplanation } from './SignalExplanation';
import { TrendingUp, TrendingDown, Info, ChevronDown, ChevronUp, Cpu, Bot } from 'lucide-react';
import { toggleAutoTrade } from '@/lib/api';

interface PriceCardProps {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  signalData?: any;
  isAutoTradeEnabled?: boolean;
}

export const PriceCard: React.FC<PriceCardProps> = ({ symbol, price, change, changePercent, signalData, isAutoTradeEnabled = false }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [autoTrade, setAutoTrade] = useState(isAutoTradeEnabled);
  const [isToggling, setIsToggling] = useState(false);
  
  const isPositive = change >= 0;
  const signal = signalData?.signal_type;

  const handleToggleAutoTrade = async () => {
    setIsToggling(true);
    try {
      await toggleAutoTrade(symbol, !autoTrade);
      setAutoTrade(!autoTrade);
    } catch (err) {
      console.error("Failed to toggle auto-trade", err);
    } finally {
      setIsToggling(false);
    }
  };

  return (
    <div className={`glass-card p-6 group transition-all duration-500 ${autoTrade ? 'border-blue-500/40 bg-blue-500/5 shadow-[0_0_20px_rgba(59,130,246,0.1)]' : ''}`}>
      <div className="flex justify-between items-start mb-6">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-bold text-xl text-white group-hover:text-blue-400 transition-colors tracking-tight">{symbol}</h3>
            {autoTrade && <Bot className="w-4 h-4 text-blue-400 animate-pulse" />}
          </div>
          <p className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest mt-1">NSE ETF Instrument</p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {signal && <SignalBadge type={signal} />}
          <button 
            onClick={handleToggleAutoTrade}
            disabled={isToggling}
            className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-bold uppercase transition-all ${autoTrade ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]' : 'bg-white/5 text-zinc-500 hover:text-zinc-300'}`}
          >
            <Cpu className="w-3 h-3" />
            {isToggling ? '...' : autoTrade ? 'Auto ON' : 'Auto OFF'}
          </button>
        </div>
      </div>
      
      <div className="mb-6">
        <div className="terminal-font text-3xl font-medium text-white tracking-tighter">
          ₹{price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
        </div>
        <div className={`flex items-center gap-1.5 mt-2 text-sm font-semibold ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
          {isPositive ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
          <span>
            {isPositive ? '+' : ''}{change.toFixed(2)} ({isPositive ? '+' : ''}{changePercent.toFixed(2)}%)
          </span>
        </div>
      </div>

      <div className="flex justify-between items-center pt-4 border-t border-white/5">
        <div className="flex gap-3">
           <div className="flex flex-col">
              <span className="text-[10px] text-zinc-500 uppercase font-bold tracking-tighter">RSI (14)</span>
              <span className={`text-xs font-bold terminal-font ${signalData?.rsi > 70 ? 'text-red-400' : signalData?.rsi < 30 ? 'text-emerald-400' : 'text-zinc-300'}`}>
                {signalData?.rsi || '--'}
              </span>
           </div>
           <div className="flex flex-col">
              <span className="text-[10px] text-zinc-500 uppercase font-bold tracking-tighter">MA (50)</span>
              <span className="text-xs font-bold terminal-font text-zinc-300">
                ₹{signalData?.ma50?.toLocaleString('en-IN') || '--'}
              </span>
           </div>
        </div>
        
        <button 
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-zinc-400 hover:text-white"
          title="Analyze Signal"
        >
          {isExpanded ? <ChevronDown className="w-4 h-4 rotate-180 transition-transform" /> : <ChevronDown className="w-4 h-4 transition-transform" />}
        </button>
      </div>

      {isExpanded && signalData && (
        <div className="mt-6 pt-6 border-t border-blue-500/20 bg-blue-500/5 -mx-6 px-6 pb-6 rounded-b-xl animate-in fade-in slide-in-from-top-2 duration-300">
          <div className="flex items-center gap-2 mb-4 text-blue-400">
            <Info className="w-4 h-4" />
            <span className="text-xs font-bold uppercase tracking-wider">AI Signal Intelligence</span>
          </div>
          <SignalExplanation symbol={symbol} signal={signalData} />
          
          <div className="mt-6 flex gap-2">
            <button className="flex-1 trading-btn bg-emerald-600/20 text-emerald-400 border border-emerald-600/30 hover:bg-emerald-600/30 text-xs">
              Paper Buy
            </button>
            <button className="flex-1 trading-btn bg-white/5 text-zinc-400 border border-white/10 hover:bg-white/10 text-xs">
              Set Alert
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
