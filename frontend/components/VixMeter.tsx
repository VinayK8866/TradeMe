'use client';

import React, { useEffect, useState } from 'react';
import { Activity, ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react';

export const VixMeter = () => {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    async function fetchVix() {
      try {
        const response = await fetch('http://localhost:8000/api/v1/sentiment/');
        const json = await response.json();
        if (json.success) {
          setData(json.data);
        }
      } catch (err) {
        console.error("Failed to fetch VIX");
      }
    }
    fetchVix();
    const interval = setInterval(fetchVix, 300000); // 5 mins
    return () => clearInterval(interval);
  }, []);

  if (!data) return null;

  const colorMap: any = {
    'CALM': 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    'ELEVATED': 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    'HIGH_FEAR': 'text-red-400 bg-red-500/10 border-red-500/20 shadow-[0_0_20px_rgba(239,68,68,0.2)]'
  };

  const TrendIcon = () => {
    if (data.trend === 'RISING') return <ArrowUpRight className="w-3 h-3 text-red-400" />;
    if (data.trend === 'FALLING') return <ArrowDownRight className="w-3 h-3 text-emerald-400" />;
    return <Minus className="w-3 h-3 opacity-30" />;
  };

  return (
    <div className={`px-4 py-2 rounded-xl flex items-center gap-4 border ${colorMap[data.status] || 'border-white/10'} transition-all duration-500`}>
      <div className="p-1.5 bg-white/5 rounded-lg relative">
        <Activity className={`w-4 h-4 ${data.status === 'HIGH_FEAR' ? 'animate-pulse' : ''}`} />
        <div className="absolute -top-1 -right-1">
          <TrendIcon />
        </div>
      </div>
      <div className="flex flex-col">
        <span className="text-[10px] font-bold uppercase tracking-widest opacity-50">India VIX</span>
        <div className="flex items-center gap-1">
          <span className="text-sm font-bold terminal-font">{data.value}</span>
        </div>
      </div>
      <div className="h-8 w-px bg-white/10" />
      <div className="text-xs font-medium leading-tight max-w-[200px]">
        <span className="font-bold block tracking-tight">{data.status.replace('_', ' ')}</span>
        <span className="opacity-60 text-[10px] leading-[1.1] block mt-0.5">{data.interpretation}</span>
      </div>
    </div>
  );
};
