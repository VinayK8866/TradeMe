import React from 'react';

interface SignalBadgeProps {
  type: 'BUY' | 'HOLD' | 'WATCH' | 'AVOID' | 'SAFE HOLD';
}

export const SignalBadge: React.FC<SignalBadgeProps> = ({ type }) => {
  const styles = {
    BUY: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-[0_0_10px_rgba(16,185,129,0.2)]',
    HOLD: 'bg-amber-500/10 text-amber-400 border-amber-500/30 shadow-[0_0_10px_rgba(245,158,11,0.2)]',
    WATCH: 'bg-blue-500/10 text-blue-400 border-blue-500/30 shadow-[0_0_10px_rgba(59,130,246,0.2)]',
    AVOID: 'bg-red-500/10 text-red-400 border-red-500/30 shadow-[0_0_10px_rgba(239,68,68,0.2)]',
    'SAFE HOLD': 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30 shadow-[0_0_10px_rgba(99,102,241,0.2)]',
  };

  return (
    <span className={`px-2.5 py-1 rounded-md text-[10px] font-black uppercase tracking-widest border ${styles[type]}`}>
      {type}
    </span>
  );
};
