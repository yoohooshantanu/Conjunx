"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type ConjunctionSummary = {
  cdm_id: string;
  sat1_name: string;
  sat2_name: string;
  sat1_id?: string;
  sat2_id?: string;
  sat1_object_type?: string;
  sat2_object_type?: string;
  tca: string;
  miss_distance: number;
  pc: number;
  risk_score: number;
  risk_level: string;
  recommended_action: string;
  cdm_count?: number;
  delta_v_mps?: number;
};

const riskBorderClass: Record<string, string> = {
  CRITICAL: "risk-border-critical",
  HIGH: "risk-border-high",
  MEDIUM: "risk-border-medium",
  LOW: "risk-border-low",
};

const riskTextColor: Record<string, string> = {
  CRITICAL: "text-[#f85149]",
  HIGH: "text-[#d29922]",
  MEDIUM: "text-[#e3b341]",
  LOW: "text-[#3fb950]",
};

function formatPc(pc: number): string {
  if (pc === 0) return "0";
  if (pc < 1e-7) return "< 1e-7";
  return pc.toExponential(2);
}

function isDebris(objectType: string | undefined): boolean {
  if (!objectType) return false;
  const t = objectType.toUpperCase();
  return t.includes("DEBRIS") || t.includes("DEB") || t === "TBA" || t.includes("ROCKET BODY") || t.includes("R/B");
}

function formatDeltaV(dv: number) {
  if (dv === 0) return <><span className="text-[#484f58]">0.00</span><span className="text-[#484f58] text-[10px] ml-0.5 font-normal">m/s</span></>;
  
  if (dv >= 0.1) {
    return <><span className="text-[#cdd9e5]">{dv.toFixed(2)}</span><span className="text-[#484f58] text-[10px] ml-0.5 font-normal">m/s</span></>;
  }
  
  const cm = dv * 100;
  if (cm >= 0.1) {
    return <><span className="text-[#cdd9e5]">{cm.toFixed(1)}</span><span className="text-[#484f58] text-[10px] ml-0.5 font-normal">cm/s</span></>;
  }
  
  const mm = dv * 1000;
  return <><span className="text-[#cdd9e5]">{mm.toFixed(2)}</span><span className="text-[#484f58] text-[10px] ml-0.5 font-normal">mm/s</span></>;
}

function LiveCountdown({ tca }: { tca: string }) {
  const [display, setDisplay] = useState<string | null>(null);
  const [isPassed, setIsPassed] = useState(false);

  useEffect(() => {
    const target = new Date(tca).getTime();

    const update = () => {
      const now = Date.now();
      const diff = target - now;
      if (diff <= 0) {
        setDisplay("PASSED");
        setIsPassed(true);
        return;
      }
      setIsPassed(false);
      const d = Math.floor(diff / 86400000);
      const h = Math.floor((diff % 86400000) / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      const pad = (n: number) => n.toString().padStart(2, "0");
      setDisplay(
        d > 0
          ? `${d}d ${pad(h)}:${pad(m)}:${pad(s)}`
          : `${pad(h)}:${pad(m)}:${pad(s)}`
      );
    };

    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [tca]);

  if (display === null)
    return <span className="font-data text-[#484f58]">--:--:--</span>;

  return (
    <span
      className={`font-data ${isPassed ? "text-[#484f58]" : "text-[#e6edf3]"}`}
    >
      {isPassed ? "" : "T-"}
      {display}
    </span>
  );
}

export default function ConjunctionList({
  data,
}: {
  data: ConjunctionSummary[];
}) {
  const router = useRouter();

  return (
    <div className="w-full">
      {/* Table header */}
      <div className="grid grid-cols-[80px_1fr_100px_110px_120px_90px] gap-x-3 px-4 py-2 text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold border-b border-[#21262d]">
        <div>Risk</div>
        <div>Objects</div>
        <div className="text-right">Miss Dist</div>
        <div className="text-right">Pc</div>
        <div className="text-right leading-tight">
          TCA<br />
          <span className="text-[10px] text-[#484f58] normal-case tracking-normal font-normal">UTC</span>
        </div>
        <div className="text-right">ΔV / Type</div>
      </div>

      {/* Rows */}
      <div>
        {data.map((item) => {
          const borderClass =
            riskBorderClass[item.risk_level] || "risk-border-low";
          const textColor =
            riskTextColor[item.risk_level] || "text-[#3fb950]";
          const eitherDebris =
            isDebris(item.sat1_object_type) ||
            isDebris(item.sat2_object_type);

          return (
            <div
              key={item.cdm_id}
              onClick={() => router.push(`/conjunction/${item.cdm_id}`)}
              className={`grid grid-cols-[80px_1fr_100px_110px_120px_90px] gap-x-3 items-center px-4 py-[7px] ${borderClass} border-b border-[#21262d] bg-[#0d1117] hover:bg-[#161b22] cursor-pointer transition-colors duration-75`}
            >
              {/* Risk */}
              <div
                className={`font-data text-[11px] font-normal opacity-85 uppercase ${textColor}`}
              >
                {item.risk_level}
              </div>

              {/* Objects */}
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[13px] text-[#cdd9e5] truncate">
                    {item.sat1_name}
                  </span>
                  <span className="text-[10px] text-[#484f58]">×</span>
                  <span className="text-[13px] text-[#768390] truncate">
                    {item.sat2_name}
                  </span>
                  {item.cdm_count && item.cdm_count > 1 && (
                    <span className="font-data text-[10px] text-[#484f58] ml-0.5">
                      ×{item.cdm_count}
                    </span>
                  )}
                </div>
                {(item.sat1_id || item.sat2_id) && (
                  <div className="font-data text-[10px] text-[#484f58] mt-0.5">
                    {item.sat1_id || "—"} / {item.sat2_id || "—"}
                  </div>
                )}
              </div>

              {/* Miss Distance */}
              <div className="text-right font-data text-[12px] text-[#7d8590]">
                {item.miss_distance < 1000 ? (
                  <>
                    {item.miss_distance.toFixed(0)}
                    <span className="text-[10px] text-[#484f58] ml-0.5">
                      m
                    </span>
                  </>
                ) : (
                  <>
                    {(item.miss_distance / 1000).toFixed(1)}
                    <span className="text-[10px] text-[#484f58] ml-0.5">
                      km
                    </span>
                  </>
                )}
              </div>

              {/* Pc */}
              <div className="text-right font-data text-[12px] text-[#7d8590]">
                {formatPc(item.pc)}
              </div>

              {/* TCA Countdown */}
              <div className="text-right text-[12px]">
                <LiveCountdown tca={item.tca} />
              </div>

              {/* Delta-V or DEBRIS */}
              <div className="text-right font-data text-[12px]">
                {eitherDebris ? (
                  <span className="text-[#484f58] text-[11px]">N/A</span>
                ) : item.delta_v_mps !== undefined ? (
                  formatDeltaV(item.delta_v_mps)
                ) : (
                  <span className="text-[#7d8590] text-[11px]">—</span>
                )}
              </div>
            </div>
          );
        })}

        {data.length === 0 && (
          <div className="text-center py-12 text-[#484f58] text-[13px]">
            No active conjunction events.
          </div>
        )}
      </div>
    </div>
  );
}
