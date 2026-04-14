"use client";

import { useEffect, useRef, useState } from "react";

type CurvePoint = {
  scale: number;
  pc: number;
};

type SensitivityData = {
  base?: number;
  covariance_x2?: number;
  covariance_x0_5?: number;
  curve?: CurvePoint[];
};

export default function PcSensitivityChart({ data }: { data: SensitivityData }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ x: number; y: number; scale: number; pc: number } | null>(null);

  const curve = data.curve || [];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || curve.length < 2) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = rect.height;
    const padL = 58, padR = 14, padT = 14, padB = 28;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;

    ctx.clearRect(0, 0, W, H);

    const pcs = curve.map(p => p.pc);
    const scales = curve.map(p => p.scale);
    const maxPc = Math.max(...pcs) * 1.15 || 1e-6;
    const minScale = Math.min(...scales);
    const maxScale = Math.max(...scales);
    const scaleRange = maxScale - minScale || 1;

    const toX = (s: number) => padL + ((s - minScale) / scaleRange) * chartW;
    const toY = (pc: number) => padT + chartH - (pc / maxPc) * chartH;

    // --- Grid ---
    ctx.strokeStyle = "#21262d";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padT + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(W - padR, y);
      ctx.stroke();

      const val = maxPc - (maxPc / 4) * i;
      ctx.fillStyle = "#484f58";
      ctx.font = "9px 'JetBrains Mono', monospace";
      ctx.textAlign = "right";
      ctx.fillText(val.toExponential(1), padL - 6, y + 3);
    }

    // --- X labels ---
    ctx.textAlign = "center";
    ctx.fillStyle = "#484f58";
    ctx.font = "9px 'JetBrains Mono', monospace";
    const xLabelScales = [0.5, 1, 2, 3, 5, 8].filter(s => s >= minScale && s <= maxScale);
    for (const s of xLabelScales) {
      const x = toX(s);
      ctx.fillText(`${s}×`, x, H - 6);
    }

    // --- Axis labels ---
    ctx.fillStyle = "#484f58";
    ctx.font = "8px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Covariance Scale Factor", padL + chartW / 2, H);

    ctx.save();
    ctx.translate(8, padT + chartH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("Pc", 0, 0);
    ctx.restore();

    // --- Gradient fill under curve ---
    const gradient = ctx.createLinearGradient(0, padT, 0, padT + chartH);
    gradient.addColorStop(0, "rgba(88, 166, 255, 0.18)");
    gradient.addColorStop(1, "rgba(88, 166, 255, 0.0)");

    ctx.beginPath();
    ctx.moveTo(toX(curve[0].scale), toY(0));
    for (const pt of curve) {
      ctx.lineTo(toX(pt.scale), toY(pt.pc));
    }
    ctx.lineTo(toX(curve[curve.length - 1].scale), toY(0));
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // --- Curve line ---
    ctx.beginPath();
    ctx.strokeStyle = "#58a6ff";
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    for (let i = 0; i < curve.length; i++) {
      const x = toX(curve[i].scale);
      const y = toY(curve[i].pc);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // --- Points ---
    for (let i = 0; i < curve.length; i++) {
      const x = toX(curve[i].scale);
      const y = toY(curve[i].pc);
      const isBase = curve[i].scale === 1.0;

      ctx.beginPath();
      ctx.arc(x, y, isBase ? 4.5 : 2.5, 0, Math.PI * 2);
      ctx.fillStyle = isBase ? "#e6edf3" : "#58a6ff";
      ctx.fill();

      if (isBase) {
        // Outer glow ring for the 1× base point
        ctx.beginPath();
        ctx.arc(x, y, 7, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(230, 237, 243, 0.25)";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    }

    // --- 1× vertical reference line ---
    const baseX = toX(1.0);
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "#30363d";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(baseX, padT);
    ctx.lineTo(baseX, padT + chartH);
    ctx.stroke();
    ctx.setLineDash([]);

    // "Current" label
    ctx.fillStyle = "#7d8590";
    ctx.font = "8px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("current", baseX, padT - 3);
  }, [curve, hover]);

  // --- Mouse interaction ---
  const handleMouseMove = (e: React.MouseEvent) => {
    if (!canvasRef.current || curve.length < 2) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left;

    const scales = curve.map(p => p.scale);
    const minScale = Math.min(...scales);
    const maxScale = Math.max(...scales);
    const padL = 58, padR = 14;
    const chartW = rect.width - padL - padR;
    const scaleRange = maxScale - minScale || 1;

    const mouseScale = minScale + ((mx - padL) / chartW) * scaleRange;

    // Find closest point
    let closest = curve[0];
    let minDist = Infinity;
    for (const pt of curve) {
      const d = Math.abs(pt.scale - mouseScale);
      if (d < minDist) { minDist = d; closest = pt; }
    }

    const toX = (s: number) => padL + ((s - minScale) / scaleRange) * chartW;
    const maxPc = Math.max(...curve.map(p => p.pc)) * 1.15 || 1e-6;
    const padT = 14, chartH = rect.height - padT - 28;
    const toY = (pc: number) => padT + chartH - (pc / maxPc) * chartH;

    setHover({ x: toX(closest.scale), y: toY(closest.pc), scale: closest.scale, pc: closest.pc });
  };

  if (curve.length < 2) return null;

  // Find peak Pc and its scale
  const peakPt = curve.reduce((a, b) => b.pc > a.pc ? b : a, curve[0]);
  const basePt = curve.find(p => p.scale === 1.0);

  return (
    <div ref={containerRef} className="px-4 py-3">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold">
            📊 Pc Sensitivity
          </span>
          <span className="font-data text-[10px] text-[#484f58]">
            {curve.length} points
          </span>
        </div>
        {peakPt && (
          <span className="font-data text-[10px] text-[#d29922]">
            peak {peakPt.pc.toExponential(1)} @ {peakPt.scale}×
          </span>
        )}
      </div>

      <div className="relative" onMouseMove={handleMouseMove} onMouseLeave={() => setHover(null)}>
        <canvas ref={canvasRef} className="w-full cursor-crosshair" style={{ height: "160px" }} />

        {/* Tooltip */}
        {hover && (
          <div
            className="absolute pointer-events-none z-10"
            style={{
              left: `${hover.x}px`,
              top: `${hover.y - 42}px`,
              transform: "translateX(-50%)",
            }}
          >
            <div className="bg-[#1c2128] border border-[#30363d] px-2 py-1 rounded shadow-lg whitespace-nowrap text-center">
              <div className="font-data text-[10px] text-[#7d8590]">{hover.scale}× covariance</div>
              <div className="font-data text-[11px] text-[#e6edf3]">Pc = {hover.pc.toExponential(2)}</div>
            </div>
          </div>
        )}
      </div>

      {/* Legend row */}
      <div className="flex items-center justify-between mt-1 text-[9px] text-[#484f58]">
        <span>← tighter uncertainty</span>
        <span>looser uncertainty →</span>
      </div>
    </div>
  );
}
