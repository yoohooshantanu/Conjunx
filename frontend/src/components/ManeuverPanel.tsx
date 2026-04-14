"use client";

import { useState } from "react";
import { recomputeManeuver } from "@/lib/api";

type ManeuverData = {
  delta_v_mps: number;
  delta_v_direction: number[];
  burn_duration_s: number;
  burn_time: string;
  fuel_cost_kg: number;
  pc_before: number;
  pc_after: number;
  maneuver_feasible: boolean;
  reason: string;
  target_miss_distance_m?: number;
};

function parseBurnTime(raw: string): string {
  const cleaned = raw.replace(/([+-]\d{2}:\d{2})Z$/, '$1');
  const d = new Date(cleaned);
  if (isNaN(d.getTime())) return "—";
  const hh = d.getUTCHours().toString().padStart(2, '0');
  const mm = d.getUTCMinutes().toString().padStart(2, '0');
  return `${hh}:${mm} UTC`;
}

function DataRow({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="flex justify-between items-center py-[2px]">
      <span className="text-[10px] text-[#484f58] uppercase">{label}</span>
      <span className="font-data text-[11px] text-[#7d8590]">
        {value}{unit && <span className="text-[#484f58] ml-0.5">{unit}</span>}
      </span>
    </div>
  );
}

export default function ManeuverPanel({ maneuver, cdmId }: { maneuver: ManeuverData; cdmId: string }) {
  const [data, setData] = useState(maneuver);
  const [loading, setLoading] = useState(false);
  const [mass, setMass] = useState(500);
  const [isp, setIsp] = useState(220);

  const handleRecompute = async () => {
    setLoading(true);
    try {
      const resp = await recomputeManeuver(cdmId, { satellite_mass_kg: mass, isp });
      setData(resp);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  if (!data.maneuver_feasible) {
    return (
      <div className="px-4 py-3">
        <div className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold mb-2">
          Maneuver Assessment
        </div>
        <div className="text-[12px] text-[#f85149] mb-1">NOT FEASIBLE</div>
        <p className="text-[12px] text-[#7d8590] leading-relaxed">{data.reason}</p>
      </div>
    );
  }

  const reduction = data.pc_before > 0 ? ((1 - data.pc_after / data.pc_before) * 100) : 0;

  // Determine callout color based on Pc reduction effectiveness
  const calloutColor = reduction > 90 ? "#3fb950" : reduction > 50 ? "#d29922" : "#f85149";

  return (
    <div className="px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold">
          Recommended Maneuver
        </span>
        <span className="font-data text-[10px] text-[#3fb950]">
          −{reduction.toFixed(0)}% Pc
        </span>
      </div>

      {/* Decision callout banner */}
      <div
        className="mb-3 px-3 py-2 border rounded-sm flex items-center gap-2"
        style={{
          borderColor: `${calloutColor}30`,
          background: `${calloutColor}08`,
        }}
      >
        <span className="text-[14px] shrink-0">🚀</span>
        <div className="text-[11px] leading-snug">
          <span className="font-data text-[#e6edf3]">+{data.delta_v_mps.toFixed(4)} m/s</span>
          <span className="text-[#7d8590]"> along-track → Pc drops </span>
          <span className="font-data text-[#e6edf3]">{data.pc_before.toExponential(1)}</span>
          <span className="text-[#7d8590]"> → </span>
          <span className="font-data" style={{ color: calloutColor }}>{data.pc_after.toExponential(1)}</span>
          <span className="text-[#7d8590]"> (</span>
          <span className="font-data font-bold" style={{ color: calloutColor }}>−{reduction.toFixed(0)}%</span>
          <span className="text-[#7d8590]">)</span>
        </div>
      </div>

      <div className="space-y-0">
        <DataRow label="ΔV" value={data.delta_v_mps.toFixed(4)} unit="m/s" />
        <DataRow label="Burn time" value={parseBurnTime(data.burn_time)} />
        <DataRow label="Fuel cost" value={data.fuel_cost_kg.toFixed(3)} unit="kg" />
        <DataRow label="Pc before" value={data.pc_before.toExponential(2)} />
        <DataRow label="Pc after" value={data.pc_after.toExponential(2)} />
      </div>

      {/* Recompute controls */}
      <div className="flex gap-2 items-end mt-3 pt-2 border-t border-[#21262d]">
        <div className="flex-1">
          <label className="text-[9px] text-[#484f58] uppercase tracking-wider block mb-1">Mass (kg)</label>
          <input
            type="number"
            className="w-full bg-[#0d1117] border border-[#30363d] px-2 py-1 text-[12px] font-data text-[#e6edf3] focus:border-[#484f58] focus:outline-none"
            value={mass}
            onChange={(e) => setMass(Number(e.target.value))}
          />
        </div>
        <div className="flex-1">
          <label className="text-[9px] text-[#484f58] uppercase tracking-wider block mb-1">Isp (s)</label>
          <input
            type="number"
            className="w-full bg-[#0d1117] border border-[#30363d] px-2 py-1 text-[12px] font-data text-[#e6edf3] focus:border-[#484f58] focus:outline-none"
            value={isp}
            onChange={(e) => setIsp(Number(e.target.value))}
          />
        </div>
        <button
          onClick={handleRecompute}
          disabled={loading}
          className="px-3 py-1 border border-[#30363d] bg-[#161b22] text-[11px] font-data text-[#7d8590] hover:bg-[#1c2128] hover:text-[#e6edf3] disabled:opacity-40 transition-colors"
        >
          {loading ? "..." : "Update"}
        </button>
      </div>
    </div>
  );
}
