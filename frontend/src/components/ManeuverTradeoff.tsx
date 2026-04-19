"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { fetchTradeoff } from "@/lib/api";

interface TradeoffResult {
  delta_v_mps: number;
  new_miss_distance_m: number;
  new_pc: number;
  fuel_cost_kg: number;
  feasible: boolean;
  effective_time_s: number;
  ghost_offset_m?: number;
  hypothetical?: boolean;
  original_miss_distance_m?: number;
  original_pc?: number;
}

/* ── Animated number display ─────────────────────────────────────── */
function AnimatedValue({
  value,
  format,
  className,
}: {
  value: number;
  format: (v: number) => string;
  className?: string;
}) {
  const [display, setDisplay] = useState(value);
  const rafRef = useRef<number>(0);
  const prevRef = useRef(value);

  useEffect(() => {
    const from = prevRef.current;
    const to = value;
    prevRef.current = value;
    if (from === to) return;

    const start = performance.now();
    const duration = 350;

    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3); // ease-out cubic
      setDisplay(from + (to - from) * ease);
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value]);

  return <span className={className}>{format(display)}</span>;
}

/* ── Circular Pc gauge ───────────────────────────────────────────── */
function PcGauge({
  originalPc,
  newPc,
}: {
  originalPc: number;
  newPc: number;
}) {
  // Map Pc to 0-1 scale (log-scale from 1e-12 to 1e-1)
  const pcToNorm = (pc: number) => {
    if (pc <= 0) return 0;
    const logVal = Math.log10(Math.max(pc, 1e-12));
    return Math.max(0, Math.min(1, (logVal + 12) / 11)); // -12 to -1 range
  };

  const origNorm = pcToNorm(originalPc);
  const newNorm = pcToNorm(newPc);
  const reduction = originalPc > 0 ? Math.max(0, (1 - newPc / originalPc) * 100) : 0;

  // Arc parameters
  const size = 80;
  const cx = size / 2;
  const cy = size / 2;
  const r = 32;
  const strokeWidth = 5;
  const startAngle = 135;
  const endAngle = 405;
  const totalArc = endAngle - startAngle;

  const polarToCart = (angle: number) => ({
    x: cx + r * Math.cos((angle * Math.PI) / 180),
    y: cy + r * Math.sin((angle * Math.PI) / 180),
  });

  const describeArc = (start: number, end: number) => {
    const s = polarToCart(start);
    const e = polarToCart(end);
    const largeArc = end - start > 180 ? 1 : 0;
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${largeArc} 1 ${e.x} ${e.y}`;
  };

  const origEnd = startAngle + totalArc * origNorm;
  const newEnd = startAngle + totalArc * newNorm;

  // Color interpolation based on reduction
  const gaugeColor =
    reduction > 80
      ? "#3fb950"
      : reduction > 50
        ? "#4ade80"
        : reduction > 20
          ? "#d29922"
          : reduction > 5
            ? "#e3b341"
            : "#f85149";

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Track */}
        <path
          d={describeArc(startAngle, endAngle)}
          fill="none"
          stroke="#21262d"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
        {/* Original Pc arc (dim) */}
        {origNorm > 0.01 && (
          <path
            d={describeArc(startAngle, origEnd)}
            fill="none"
            stroke="#f8514940"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
          />
        )}
        {/* New Pc arc (bright) */}
        {newNorm > 0.01 && (
          <path
            d={describeArc(startAngle, newEnd)}
            fill="none"
            stroke={gaugeColor}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            style={{
              filter: `drop-shadow(0 0 4px ${gaugeColor}80)`,
              transition: "d 0.4s ease-out",
            }}
          />
        )}
        {/* Center text */}
        <text
          x={cx}
          y={cy - 3}
          textAnchor="middle"
          fill={gaugeColor}
          fontSize="11"
          fontFamily="'JetBrains Mono', monospace"
          fontWeight="bold"
        >
          {reduction > 0.1 ? `-${reduction.toFixed(0)}%` : "—"}
        </text>
        <text
          x={cx}
          y={cy + 10}
          textAnchor="middle"
          fill="#484f58"
          fontSize="7"
          fontFamily="'JetBrains Mono', monospace"
        >
          Pc REDUCTION
        </text>
      </svg>
    </div>
  );
}

/* ── Miss distance visual diagram ────────────────────────────────── */
function MissDiagram({
  originalMiss,
  newMiss,
  feasible,
}: {
  originalMiss: number;
  newMiss: number;
  feasible: boolean;
}) {
  // Normalize positions: map miss distances to visual space
  const maxMiss = Math.max(newMiss, originalMiss * 3, 2000);
  const origPx = Math.max(8, (originalMiss / maxMiss) * 100);
  const newPx = Math.max(8, (newMiss / maxMiss) * 100);
  const improvement = newMiss - originalMiss;

  return (
    <div className="relative w-full h-[52px] bg-[#0d1117] border border-[#21262d] rounded overflow-hidden">
      {/* Background grid lines */}
      {[25, 50, 75].map((p) => (
        <div
          key={p}
          className="absolute top-0 bottom-0 border-l border-[#21262d30]"
          style={{ left: `${p}%` }}
        />
      ))}

      {/* Original miss marker */}
      <div
        className="absolute top-[8px] h-[36px] border-l-2 border-dashed border-[#f8514960] transition-all duration-500"
        style={{ left: `${(origPx / 100) * 100}%` }}
      >
        <div className="absolute -top-[1px] -left-[3px] w-[6px] h-[6px] rounded-full bg-[#f85149]" />
        <div className="absolute -bottom-[1px] left-1 text-[7px] text-[#f85149] font-data whitespace-nowrap opacity-60">
          ORIG
        </div>
      </div>

      {/* New miss marker */}
      <div
        className="absolute top-[8px] h-[36px] border-l-2 transition-all duration-500 ease-out"
        style={{
          left: `${(newPx / 100) * 100}%`,
          borderColor: feasible ? "#3fb950" : "#d29922",
        }}
      >
        <div
          className="absolute -top-[1px] -left-[3px] w-[6px] h-[6px] rounded-full transition-colors duration-300"
          style={{ backgroundColor: feasible ? "#3fb950" : "#d29922" }}
        />
        <div
          className="absolute -bottom-[1px] left-1 text-[7px] font-data whitespace-nowrap transition-colors duration-300"
          style={{ color: feasible ? "#3fb950" : "#d29922" }}
        >
          NEW
        </div>
      </div>

      {/* Improvement zone fill */}
      {improvement > 0 && (
        <div
          className="absolute top-[10px] h-[32px] transition-all duration-500 ease-out"
          style={{
            left: `${(origPx / 100) * 100}%`,
            width: `${Math.max(0, ((newPx - origPx) / 100) * 100)}%`,
            background: `linear-gradient(90deg, ${feasible ? "#3fb95015" : "#d2992215"}, ${feasible ? "#3fb95030" : "#d2992230"})`,
          }}
        />
      )}

      {/* Objects */}
      <div className="absolute left-[4px] top-1/2 -translate-y-1/2 flex items-center gap-[3px]">
        <div className="w-[8px] h-[8px] rounded-full bg-[#58a6ff] shadow-[0_0_6px_#58a6ff80] animate-pulse" />
        <div className="w-[8px] h-[8px] rounded-full bg-[#ff6b6b] shadow-[0_0_6px_#ff6b6b80] animate-pulse" style={{ animationDelay: "0.5s" }} />
      </div>

      {/* Right label: distance gained */}
      {improvement > 1 && (
        <div className="absolute right-2 top-1/2 -translate-y-1/2 text-right">
          <div
            className="text-[10px] font-data font-bold transition-colors duration-300"
            style={{ color: feasible ? "#3fb950" : "#d29922" }}
          >
            +{improvement < 1000 ? `${improvement.toFixed(0)}m` : `${(improvement / 1000).toFixed(1)}km`}
          </div>
          <div className="text-[7px] text-[#484f58] uppercase">separation</div>
        </div>
      )}
    </div>
  );
}

/* ── Fuel bar ────────────────────────────────────────────────────── */
function FuelBar({ fuelKg, maxFuel = 5 }: { fuelKg: number; maxFuel?: number }) {
  const pct = Math.min((fuelKg / maxFuel) * 100, 100);
  const color =
    pct > 80 ? "#f85149" : pct > 50 ? "#d29922" : pct > 25 ? "#e3b341" : "#3fb950";

  return (
    <div className="w-full">
      <div className="flex justify-between text-[9px] mb-1">
        <span className="text-[#484f58] uppercase">Fuel Required</span>
        <span className="font-data text-[#7d8590]">
          {fuelKg.toFixed(3)} kg
        </span>
      </div>
      <div className="w-full h-[4px] bg-[#21262d] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}90, ${color})`,
            boxShadow: `0 0 8px ${color}40`,
          }}
        />
      </div>
    </div>
  );
}

/* ── Main Component ──────────────────────────────────────────────── */
export default function ManeuverTradeoff({
  cdmId,
  disabled,
}: {
  cdmId: string;
  disabled?: boolean;
}) {
  const [deltaV, setDeltaV] = useState(0.5);
  const [mass, setMass] = useState(500);
  const [isp, setIsp] = useState(220);
  const [result, setResult] = useState<TradeoffResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    let active = true;
    const compute = async () => {
      setLoading(true);
      try {
        const data = await fetchTradeoff(cdmId, {
          delta_v_mps: deltaV,
          satellite_mass_kg: mass,
          isp: isp,
        });
        if (active) {
          setResult(data);
          if (
            data.ghost_offset_m !== undefined &&
            typeof window !== "undefined"
          ) {
            window.dispatchEvent(
              new CustomEvent("updateGhostOrbit", {
                detail: data.ghost_offset_m,
              })
            );
          }
        }
      } catch (e) {
        console.error("Tradeoff error", e);
      } finally {
        if (active) setLoading(false);
      }
    };

    const timer = setTimeout(compute, 120);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [cdmId, deltaV, mass, isp]);

  // Slider active track percentage
  const sliderPct = (deltaV / 2) * 100;

  // Effectiveness color for slider glow
  const sliderColor =
    deltaV > 1.5
      ? "#3fb950"
      : deltaV > 0.8
        ? "#4ade80"
        : deltaV > 0.3
          ? "#d29922"
          : "#e3b341";

  return (
    <div className="px-4 py-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold">
          Maneuver Tradeoff
        </div>
        {result?.hypothetical && (
          <div className="flex items-center gap-1.5">
            <div className="w-[5px] h-[5px] rounded-full bg-[#d29922] animate-pulse" />
            <span className="text-[8px] text-[#d29922] uppercase tracking-wider font-semibold">
              Hypothetical · 6h Lead
            </span>
          </div>
        )}
        {loading && (
          <div className="w-3 h-3 border border-[#30363d] border-t-[#58a6ff] rounded-full animate-spin" />
        )}
      </div>

      {disabled ? (
        <div className="text-[12px] text-[#7d8590] mt-1 mb-2">
          Tradeoff unavailable — neither object has propulsion capability
        </div>
      ) : (
        <>
          {/* ΔV slider with active track */}
          <div className="mb-4">
            <div className="flex justify-between text-[11px] mb-2">
              <span className="text-[#7d8590]">ΔV</span>
              <span className="font-data text-[#e6edf3] flex items-center gap-1.5">
                <AnimatedValue
                  value={deltaV}
                  format={(v) => v.toFixed(2)}
                  className="tabular-nums"
                />
                <span className="text-[#484f58] text-[9px]">m/s</span>
              </span>
            </div>
            <div className="relative">
              {/* Custom active track behind the native input */}
              <div className="absolute top-1/2 -translate-y-1/2 left-0 right-0 h-[4px] rounded-full bg-[#21262d] pointer-events-none">
                <div
                  className="h-full rounded-full transition-all duration-150"
                  style={{
                    width: `${sliderPct}%`,
                    background: `linear-gradient(90deg, ${sliderColor}60, ${sliderColor})`,
                    boxShadow: isDragging
                      ? `0 0 12px ${sliderColor}60, 0 0 4px ${sliderColor}40`
                      : `0 0 6px ${sliderColor}30`,
                  }}
                />
              </div>
              <input
                type="range"
                min="0"
                max="2"
                step="0.01"
                value={deltaV}
                onChange={(e) => setDeltaV(parseFloat(e.target.value))}
                onMouseDown={() => setIsDragging(true)}
                onMouseUp={() => setIsDragging(false)}
                onTouchStart={() => setIsDragging(true)}
                onTouchEnd={() => setIsDragging(false)}
                className="w-full relative z-10"
                style={{ background: "transparent" }}
              />
            </div>
            {/* Tick marks */}
            <div className="flex justify-between text-[7px] text-[#484f58] font-data mt-0.5 px-[2px]">
              <span>0</span>
              <span>0.5</span>
              <span>1.0</span>
              <span>1.5</span>
              <span>2.0</span>
            </div>
          </div>

          {/* Mass / Isp inputs */}
          <div className="flex gap-3 mb-4">
            <div className="flex-1">
              <label className="text-[9px] text-[#484f58] uppercase tracking-wider block mb-1">
                Mass (kg)
              </label>
              <input
                type="number"
                value={mass}
                onChange={(e) => setMass(Number(e.target.value))}
                className="w-full bg-[#0d1117] border border-[#30363d] px-2 py-1 text-[12px] text-[#e6edf3] font-data focus:outline-none focus:border-[#484f58] transition-colors"
              />
            </div>
            <div className="flex-1">
              <label className="text-[9px] text-[#484f58] uppercase tracking-wider block mb-1">
                Isp (s)
              </label>
              <input
                type="number"
                value={isp}
                onChange={(e) => setIsp(Number(e.target.value))}
                className="w-full bg-[#0d1117] border border-[#30363d] px-2 py-1 text-[12px] text-[#e6edf3] font-data focus:outline-none focus:border-[#484f58] transition-colors"
              />
            </div>
          </div>

          {/* Visual results */}
          {result && (
            <div className="space-y-3">
              {/* Miss distance diagram */}
              <MissDiagram
                originalMiss={result.original_miss_distance_m ?? 0}
                newMiss={result.new_miss_distance_m}
                feasible={result.feasible}
              />

              {/* Gauge + stats row */}
              <div className="flex items-start gap-3">
                {/* Pc Gauge */}
                <PcGauge
                  originalPc={result.original_pc ?? 0}
                  newPc={result.new_pc}
                />

                {/* Right-side stats */}
                <div className="flex-1 space-y-1.5 pt-1">
                  {/* New Miss */}
                  <div className="flex justify-between py-[2px]">
                    <span className="text-[10px] text-[#484f58] uppercase">
                      New miss
                    </span>
                    <AnimatedValue
                      value={result.new_miss_distance_m}
                      format={(v) =>
                        v < 1000
                          ? `${v.toFixed(0)} m`
                          : `${(v / 1000).toFixed(2)} km`
                      }
                      className={`font-data text-[12px] ${result.feasible ? "text-[#3fb950]" : "text-[#f85149]"}`}
                    />
                  </div>
                  {/* New Pc */}
                  <div className="flex justify-between py-[2px]">
                    <span className="text-[10px] text-[#484f58] uppercase">
                      New Pc
                    </span>
                    <span className="font-data text-[12px] text-[#7d8590]">
                      {result.new_pc.toExponential(2)}
                    </span>
                  </div>
                  {/* Status */}
                  <div className="flex justify-between py-[2px]">
                    <span className="text-[10px] text-[#484f58] uppercase">
                      Status
                    </span>
                    <span
                      className={`font-data text-[10px] uppercase font-bold ${result.feasible ? "text-[#3fb950]" : "text-[#f85149]"}`}
                    >
                      {result.feasible ? "ACHIEVABLE" : "EXCEEDS LIMITS"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Fuel bar */}
              <FuelBar fuelKg={result.fuel_cost_kg} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
