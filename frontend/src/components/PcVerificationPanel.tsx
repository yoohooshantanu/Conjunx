"use client";

import { useState, useEffect } from "react";
import { fetchPcAnalysis } from "@/lib/api";
import PcSensitivityChart from "./PcSensitivityChart";

interface PcAnalysis {
  cdm_id: string;
  pc_foster: number;
  pc_spacetrack: number;
  delta_percent: number;
  miss_distance_computed: number;
  miss_distance_cdm: number;
  miss_distance_agreement: boolean;
  hard_body_radius: number;
  relative_speed: number;
  tle_age_hours: number;
  covariance_source: string;
  computation_valid: boolean;
  failure_reason: string | null;
  interpretation: string;
  analysis_notes?: string[];
  risk_assessment?: string;
  sensitivity_analysis?: {
    base?: number;
    covariance_x2?: number;
    covariance_x0_5?: number;
    curve?: { scale: number; pc: number }[];
  };
}

function DeltaArrow({ delta }: { delta: number }) {
  const abs = Math.abs(delta);
  let color: string;
  let arrow: string;

  if (abs <= 20) {
    color = "#3fb950"; // green
  } else if (abs <= 50) {
    color = "#d29922"; // orange
  } else {
    color = "#f85149"; // red
  }

  if (delta < 0) {
    arrow = "▼";
  } else if (delta > 0) {
    arrow = "▲";
  } else {
    arrow = "—";
  }

  const label = delta < 0 ? "lower" : delta > 0 ? "higher" : "equal";

  return (
    <span style={{ color }} className="font-data">
      {arrow} {abs.toFixed(1)}% {label}
    </span>
  );
}

function InfoTooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  return (
    <span
      className="relative inline-block ml-1 cursor-help"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span className="text-[9px] text-[#484f58] border border-[#30363d] rounded-full px-1 py-0">?</span>
      {show && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 w-52 bg-[#1c2128] border border-[#30363d] text-[10px] text-[#7d8590] p-2 rounded z-50 shadow-lg">
          {text}
        </span>
      )}
    </span>
  );
}

export default function PcVerificationPanel({ cdmId }: { cdmId: string }) {
  const [data, setData] = useState<PcAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchPcAnalysis(cdmId)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [cdmId]);

  if (loading) {
    return (
      <div className="px-3 py-3">
        <div className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold mb-2">
          Independent Pc Verification
        </div>
        <div className="text-[11px] text-[#484f58] font-data animate-pulse">
          Computing Foster Pc…
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="px-3 py-3">
        <div className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold mb-2">
          Independent Pc Verification
        </div>
        <div className="text-[11px] text-[#f8514960]">
          Pc analysis unavailable
        </div>
      </div>
    );
  }

  if (!data.computation_valid) {
    return (
      <div className="px-3 py-3">
        <div className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold mb-2">
          Independent Pc Verification
        </div>
        <div className="text-[11px] text-[#484f58] font-data">
          Computation invalid: {data.failure_reason || "Unknown"}
        </div>
      </div>
    );
  }

  const rows: [string, React.ReactNode, React.ReactNode?][] = [
    [
      "Space-Track (18 SDS)",
      <span key="st" className="font-data text-[#e6edf3]">
        {data.pc_spacetrack.toExponential(2)}
      </span>,
    ],
    [
      "Conjunx (Foster method)",
      <span key="cj" className="font-data text-[#e6edf3]">
        {data.pc_foster.toExponential(2)}
      </span>,
    ],
    [
      "Agreement",
      <DeltaArrow key="da" delta={data.delta_percent} />,
    ],
    [
      "Hard-body radius",
      <span key="hbr" className="font-data text-[#7d8590]">
        {data.hard_body_radius.toFixed(1)} m
      </span>,
    ],
    [
      "Relative speed",
      <span key="rs" className="font-data text-[#7d8590]">
        {data.relative_speed.toLocaleString(undefined, { maximumFractionDigits: 0 })} m/s
      </span>,
    ],
    [
      "TLE age at TCA",
      <span key="ta" className="font-data text-[#7d8590]">
        {data.tle_age_hours.toFixed(1)} hours
      </span>,
    ],
  ];

  return (
    <div className="px-3 py-3">
      <div className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold mb-2">
        Independent Pc Verification
      </div>

      <div className="space-y-[3px]">
        {rows.map(([label, value], i) => (
          <div key={i} className="flex justify-between items-center gap-3 py-[1px]">
            <span className="text-[10px] text-[#484f58] shrink-0">{label}</span>
            <span className="text-[11px] text-right">{value}</span>
          </div>
        ))}

        {/* Covariance source with info tooltip */}
        <div className="flex justify-between items-center gap-3 py-[1px]">
          <span className="text-[10px] text-[#484f58] shrink-0">
            Covariance
            <InfoTooltip text="Public CDMs from Space-Track do not include covariance matrices. This analysis uses estimated covariance based on object RCS size and type." />
          </span>
          <span className="text-[11px] font-data text-[#484f58] text-right">
            RCS-default
          </span>
        </div>
      </div>

      {/* Interpretation */}
      {data.interpretation && (
        <div className="mt-2 pt-2 border-t border-[#21262d]">
          <p className="text-[10px] text-[#484f58] leading-relaxed">
            {data.interpretation}
          </p>
        </div>
      )}

      {/* ANALYSIS INSIGHTS */}
      {(data.analysis_notes?.length ? true : false || data.risk_assessment) && (
        <div className="mt-3 pt-3 border-t border-[#21262d]">
          <div className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold mb-2 flex items-center gap-1">
            <span className="text-[12px]">🔍</span> ANALYSIS INSIGHTS
          </div>

          <div className="space-y-3">
            {data.risk_assessment && (
              <div>
                <div className="text-[9px] text-[#484f58] uppercase mb-1">Risk Level</div>
                <div className={`text-[11px] font-data font-bold ${
                  data.risk_assessment.startsWith("HIGH") ? "text-[#f85149]" :
                  data.risk_assessment.startsWith("MEDIUM") ? "text-[#d29922]" :
                  "text-[#3fb950]"
                }`}>
                  {data.risk_assessment}
                </div>
              </div>
            )}

            {data.analysis_notes && data.analysis_notes.length > 0 && (
              <div>
                <div className="text-[9px] text-[#484f58] uppercase mb-1">Notes</div>
                <ul className="text-[11px] text-[#7d8590] list-disc list-outside ml-3 space-y-1">
                  {data.analysis_notes.map((note, idx) => (
                    <li key={idx} className="leading-tight">{note}</li>
                  ))}
                </ul>
              </div>
            )}

            {data.sensitivity_analysis && Object.keys(data.sensitivity_analysis).length > 0 && (
              <div>
                {data.sensitivity_analysis.curve && data.sensitivity_analysis.curve.length >= 2 ? (
                  <PcSensitivityChart data={data.sensitivity_analysis} />
                ) : (
                  <>
                    <div className="text-[9px] text-[#484f58] uppercase mb-1">Sensitivity</div>
                    <div className="text-[11px] font-data text-[#8b949e] space-y-[2px]">
                      {data.sensitivity_analysis.covariance_x2 !== undefined && (
                        <div>If uncertainty doubles → Pc = <span className="text-[#e6edf3]">{data.sensitivity_analysis.covariance_x2.toExponential(2)}</span></div>
                      )}
                      {data.sensitivity_analysis.covariance_x0_5 !== undefined && (
                        <div>If uncertainty halves&nbsp;&nbsp;→ Pc = <span className="text-[#e6edf3]">{data.sensitivity_analysis.covariance_x0_5.toExponential(2)}</span></div>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
