"use client";

import { useState } from "react";

type Explanation = {
  situation_summary: string;
  risk_rationale: string;
  maneuver_recommendation: string;
  no_action_scenario: string;
  operator_urgency: string;
};

export default function AIExplainer({ explanation }: { explanation: Explanation }) {
  const [showAll, setShowAll] = useState(false);

  if (!explanation) return null;

  const urgencyColor: Record<string, string> = {
    ACT_NOW: "text-[#f85149]",
    MONITOR: "text-[#d29922]",
    WATCH: "text-[#7d8590]",
  };

  return (
    <div className="px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold">
          AI Situation Brief
        </span>
        <span className={`font-data text-[10px] font-bold uppercase tracking-wider ${urgencyColor[explanation.operator_urgency] || "text-[#7d8590]"}`}>
          {explanation.operator_urgency?.replace("_", " ")}
        </span>
      </div>

      <p className="text-[13px] text-[#e6edf3] leading-[1.65] mb-3">
        {explanation.situation_summary}
      </p>

      {showAll ? (
        <div className="space-y-3">
          {explanation.risk_rationale && (
            <div>
              <div className="text-[10px] text-[#484f58] uppercase tracking-wider mb-1">Risk Rationale</div>
              <p className="text-[12px] text-[#7d8590] leading-relaxed">{explanation.risk_rationale}</p>
            </div>
          )}
          {explanation.maneuver_recommendation && (
            <div>
              <div className="text-[10px] text-[#484f58] uppercase tracking-wider mb-1">Recommendation</div>
              <p className="text-[12px] text-[#7d8590] leading-relaxed">{explanation.maneuver_recommendation}</p>
            </div>
          )}
          {explanation.no_action_scenario && (
            <div>
              <div className="text-[10px] text-[#484f58] uppercase tracking-wider mb-1">No-Action Scenario</div>
              <p className="text-[12px] text-[#7d8590] leading-relaxed">{explanation.no_action_scenario}</p>
            </div>
          )}
          <button
            onClick={() => setShowAll(false)}
            className="text-[11px] text-[#484f58] hover:text-[#7d8590] transition-colors"
          >
            — collapse
          </button>
        </div>
      ) : (
        <button
          onClick={() => setShowAll(true)}
          className="text-[11px] text-[#484f58] hover:text-[#7d8590] transition-colors"
        >
          + show full analysis
        </button>
      )}
    </div>
  );
}
