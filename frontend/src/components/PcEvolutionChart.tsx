"use client";

import { useEffect, useRef } from "react";

type PcHistoryPoint = {
  cdm_id: string;
  pc: number;
  created: string;
  miss_distance: number;
};

export default function PcEvolutionChart({ history }: { history: PcHistoryPoint[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || history.length < 2) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = rect.height;
    const padL = 55, padR = 12, padT = 10, padB = 24;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;

    ctx.clearRect(0, 0, W, H);

    const pcs = history.map(h => h.pc);
    const maxPc = Math.max(...pcs) * 1.2;

    // Grid lines — minimal
    ctx.strokeStyle = "#21262d";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 3; i++) {
      const y = padT + (chartH / 3) * i;
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(W - padR, y);
      ctx.stroke();

      const val = maxPc - (maxPc / 3) * i;
      ctx.fillStyle = "#484f58";
      ctx.font = "9px 'JetBrains Mono', monospace";
      ctx.textAlign = "right";
      ctx.fillText(val.toExponential(1), padL - 6, y + 3);
    }

    // X labels
    ctx.textAlign = "center";
    ctx.fillStyle = "#484f58";
    ctx.font = "8px sans-serif";
    const step = Math.max(1, Math.floor(history.length / 4));
    for (let i = 0; i < history.length; i += step) {
      const x = padL + (chartW / Math.max(1, history.length - 1)) * i;
      const dt = new Date(history[i].created);
      ctx.fillText(dt.toLocaleDateString([], { month: "short", day: "numeric" }), x, H - 4);
    }

    // Line — single solid color, no gradient fill
    ctx.beginPath();
    ctx.strokeStyle = "#7d8590";
    ctx.lineWidth = 1.5;
    ctx.lineJoin = "round";
    for (let i = 0; i < history.length; i++) {
      const x = padL + (chartW / Math.max(1, history.length - 1)) * i;
      const y = padT + chartH - ((history[i].pc) / maxPc) * chartH;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Points — small dots, last point highlighted
    for (let i = 0; i < history.length; i++) {
      const x = padL + (chartW / Math.max(1, history.length - 1)) * i;
      const y = padT + chartH - ((history[i].pc) / maxPc) * chartH;
      const isLast = i === history.length - 1;

      ctx.beginPath();
      ctx.arc(x, y, isLast ? 3 : 2, 0, Math.PI * 2);
      ctx.fillStyle = isLast ? "#e6edf3" : "#7d8590";
      ctx.fill();
    }
  }, [history]);

  if (history.length < 2) return null;

  const latest = history[history.length - 1];
  const prev = history[history.length - 2];
  const pctChange = prev.pc > 0 ? ((latest.pc - prev.pc) / prev.pc * 100) : 0;
  const trendUp = pctChange > 0;

  return (
    <div className="px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold">
            Pc Maturation
          </span>
          <span className="font-data text-[10px] text-[#484f58]">
            {history.length} updates
          </span>
        </div>
        <span className={`font-data text-[11px] ${trendUp ? "text-[#f85149]" : "text-[#3fb950]"}`}>
          {trendUp ? "▲" : "▼"} {Math.abs(pctChange).toFixed(1)}%
        </span>
      </div>
      <canvas ref={canvasRef} className="w-full" style={{ height: "110px" }} />
    </div>
  );
}
