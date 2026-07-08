import React, { useState } from 'react';
import { fetchExplanation } from '@/lib/api';
import { Sparkles, BrainCircuit, Quote } from 'lucide-react';

interface SignalExplanationProps {
  symbol: string;
  signal: any;
}

export const SignalExplanation: React.FC<SignalExplanationProps> = ({ symbol, signal }) => {
  const [explanation, setExplanation] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleExplain = async () => {
    setLoading(true);
    try {
      const data = await fetchExplanation(signal);
      if (data.success) {
        setExplanation(data.explanation);
      }
    } catch (err) {
      setExplanation("Could not get explanation. Check if backend is running.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Sentiment Micro-Card */}
      <div className="flex items-center justify-between p-3 bg-white/5 rounded-xl border border-white/10 group hover:border-blue-500/30 transition-colors">
        <div className="flex items-center gap-3">
          <div className={`w-2 h-2 rounded-full ${signal.sentiment_score > 0 ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : signal.sentiment_score < 0 ? 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]' : 'bg-zinc-500'}`} />
          <div>
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">News Sentiment</p>
            <p className="text-sm font-bold text-white capitalize">{signal.sentiment_label || 'Neutral'}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Score</p>
          <p className={`text-sm font-bold terminal-font ${signal.sentiment_score > 0 ? 'text-emerald-400' : signal.sentiment_score < 0 ? 'text-red-400' : 'text-zinc-400'}`}>
            {signal.sentiment_score > 0 ? '+' : ''}{signal.sentiment_score?.toFixed(2) || '0.00'}
          </p>
        </div>
      </div>

      {!explanation && !loading && (
        <button 
          onClick={handleExplain}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-blue-600/10 hover:bg-blue-600/20 border border-blue-500/20 text-blue-400 text-xs font-bold uppercase tracking-widest transition-all group"
        >
          <BrainCircuit className="w-4 h-4 group-hover:rotate-12 transition-transform" />
          Get AI Mentor Insight
        </button>
      )}

      {loading && (
        <div className="flex flex-col items-center justify-center py-8 gap-3">
          <div className="flex gap-1">
            <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
            <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
            <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" />
          </div>
          <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em] animate-pulse">Consulting Gemini Engine...</span>
        </div>
      )}

      {explanation && (
        <div className="relative p-5 bg-indigo-500/5 rounded-2xl border border-indigo-500/10 animate-in fade-in zoom-in-95 duration-500">
          <Quote className="absolute top-4 left-4 w-8 h-8 text-indigo-500/10" />
          <div className="relative z-10 text-sm text-zinc-300 leading-relaxed font-medium">
            {explanation}
          </div>
          <div className="mt-4 flex items-center gap-2 text-[10px] font-bold text-indigo-400/60 uppercase tracking-widest">
            <Sparkles className="w-3 h-3" /> Powered by Gemini 1.5 Flash
          </div>
        </div>
      )}
    </div>
  );
};
