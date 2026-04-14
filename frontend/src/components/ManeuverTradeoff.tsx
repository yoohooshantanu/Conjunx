"use client";

import { useState, useEffect } from "react";
import { fetchTradeoff } from "@/lib/api";

interface TradeoffResult {
  delta_v_mps: number;
  new_miss_distance_m: number;
  new_pc: number;
  fuel_cost_kg: number;
  feasible: boolean;
  effective_time_s: number;
  ghost_offset_m?: number;
}

export default function ManeuverTradeoff({ cdmId, disabled }: { cdmId: string; disabled?: boolean }) {
  const [deltaV, setDeltaV] = useState(0.5);
  const [mass, setMass] = useState(500);
  const [isp, setIsp] = useState(220);
  const [result, setResult] = useState<TradeoffResult | null>(null);
  const [loading, setLoading] = useState(false);

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
          if (data.ghost_offset_m !== undefined && typeof window !== "undefined") {
            window.dispatchEvent(new CustomEvent("updateGhostOrbit", { detail: data.ghost_offset_m }));
          }
        }
      } catch (e) {
        console.error("Tradeoff error", e);
      } finally {
        if (active) setLoading(false);
      }
    };

    const timer = setTimeout(compute, 150);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [cdmId, deltaV, mass, isp]);

  return (
    <div className="px-4 py-3">
      <div className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold mb-3">
        Maneuver Tradeoff
      </div>

      {disabled ? (
        <div className="text-[12px] text-[#7d8590] mt-1 mb-2">
          Tradeoff unavailable — neither object has propulsion capability
        </div>
      ) : (
        <>
          {/* ΔV slider */}
          <div className="mb-3">
        <div className="flex justify-between text-[11px] mb-1.5">
          <span className="text-[#7d8590]">ΔV</span>
          <span className="font-data text-[#e6edf3]">{deltaV.toFixed(2)} m/s</span>
        </div>
        <input
          type="range"
          min="0" max="2" step="0.01"
          value={deltaV}
          onChange={e => setDeltaV(parseFloat(e.target.value))}
          className="w-full"
        />
      </div>

      {/* Mass / Isp inputs */}
      <div className="flex gap-3 mb-3">
        <div className="flex-1">
          <label className="text-[9px] text-[#484f58] uppercase tracking-wider block mb-1">Mass (kg)</label>
          <input
            type="number"
            value={mass}
            onChange={e => setMass(Number(e.target.value))}
            className="w-full bg-[#0d1117] border border-[#30363d] px-2 py-1 text-[12px] text-[#e6edf3] font-data focus:outline-none focus:border-[#484f58]"
          />
        </div>
        <div className="flex-1">
          <label className="text-[9px] text-[#484f58] uppercase tracking-wider block mb-1">Isp (s)</label>
          <input
            type="number"
            value={isp}
            onChange={e => setIsp(Number(e.target.value))}
            className="w-full bg-[#0d1117] border border-[#30363d] px-2 py-1 text-[12px] text-[#e6edf3] font-data focus:outline-none focus:border-[#484f58]"
          />
        </div>
      </div>

      {/* Results */}
      {result && (
        <div className="border-t border-[#21262d] pt-2 space-y-0.5">
          <div className="flex justify-between py-[2px]">
            <span className="text-[10px] text-[#484f58] uppercase">New miss</span>
            <span className={`font-data text-[12px] ${result.feasible ? "text-[#3fb950]" : "text-[#f85149]"}`}>
              {(result.new_miss_distance_m / 1000).toFixed(2)} km
            </span>
          </div>
          <div className="flex justify-between py-[2px]">
            <span className="text-[10px] text-[#484f58] uppercase">New Pc</span>
            <span className="font-data text-[12px] text-[#7d8590]">{result.new_pc.toExponential(2)}</span>
          </div>
          <div className="flex justify-between py-[2px]">
            <span className="text-[10px] text-[#484f58] uppercase">Fuel</span>
            <span className="font-data text-[12px] text-[#d29922]">{result.fuel_cost_kg.toFixed(3)} kg</span>
          </div>
          <div className="flex justify-between py-[2px]">
            <span className="text-[10px] text-[#484f58] uppercase">Status</span>
            <span className={`font-data text-[10px] uppercase ${result.feasible ? "text-[#3fb950]" : "text-[#f85149]"}`}>
              {result.feasible ? "ACHIEVABLE" : "EXCEEDS LIMITS"}
            </span>
          </div>
        </div>
      )}
      </>)}
    </div>
  );
}
