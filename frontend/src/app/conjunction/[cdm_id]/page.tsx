import { fetchConjunctionDetail, fetchPcHistory } from "@/lib/api";
import Link from "next/link";
import AIExplainer from "@/components/AIExplainer";
import PcEvolutionChart from "@/components/PcEvolutionChart";
import ManeuverPanel from "@/components/ManeuverPanel";
import CesiumWrapper from "@/components/CesiumWrapper";
import ManeuverTradeoff from "@/components/ManeuverTradeoff";
import PcVerificationPanel from "@/components/PcVerificationPanel";

function SatMetadataPanel({ title, data, fields }: { title: string; data: Record<string, any>; fields: string[] }) {
  return (
    <div className="border border-[#30363d] bg-[#161b22]">
      <div className="px-3 py-1.5 border-b border-[#21262d] text-[10px] text-[#484f58] uppercase tracking-[0.08em] font-semibold">
        {title}
      </div>
      <div className="px-3 py-2 space-y-0.5">
        {fields.map((key) => {
          const val = data[key];
          if (val === undefined || val === null || val === "") return null;
          return (
            <div key={key} className="flex justify-between gap-3 py-[1px]">
              <span className="text-[10px] text-[#484f58] uppercase shrink-0">{key}</span>
              <span className="font-data text-[11px] text-[#7d8590] text-right truncate">{String(val)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default async function ConjunctionDetail({ params }: { params: Promise<{ cdm_id: string }> }) {
  const { cdm_id } = await params;
  let data: any;
  let pcHistory: any[] = [];

  try {
    data = await fetchConjunctionDetail(cdm_id);
  } catch (e) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="border border-[#30363d] bg-[#161b22] p-6 text-center max-w-md">
          <div className="text-[#f85149] text-[13px] font-semibold mb-2">Connection Error</div>
          <p className="text-[#7d8590] text-[12px]">Unable to reach the backend. Make sure the API is running on port 8000.</p>
        </div>
      </div>
    );
  }

  try {
    pcHistory = await fetchPcHistory(cdm_id);
  } catch {}

  const tca = data.TCA || data.tca || new Date().toISOString();
  const missDistance = parseFloat(data.MISS_DISTANCE || data.MIN_RNG) || 1000;
  const riskLevel = data.risk?.level || "UNKNOWN";
  const sat1Name = data.satcat_1?.OBJECT_NAME || data.SAT_1_NAME || data.SAT1_OBJECT_NAME || "SAT-1";
  const sat2Name = data.satcat_2?.OBJECT_NAME || data.SAT_2_NAME || data.SAT2_OBJECT_NAME || "SAT-2";
  const pc = parseFloat(data.PC) || 0;
  const norad1 = data.SAT_1_ID || data.SAT1_NORAD_CAT_ID || "";
  const norad2 = data.SAT_2_ID || data.SAT2_NORAD_CAT_ID || "";

  const riskColor: Record<string, string> = {
    CRITICAL: "text-[#f85149]",
    HIGH: "text-[#d29922]",
    MEDIUM: "text-[#e3b341]",
    LOW: "text-[#3fb950]",
  };

  // CDM fields to display for each satellite
  const sat1Fields = ["OBJECT_NAME", "OBJECT_ID", "OBJECT_TYPE", "INCLINATION", "APOAPSIS", "PERIAPSIS", "SEMI_MAJOR_AXIS", "ECCENTRICITY", "RCS_SIZE", "COUNTRY_CODE", "LAUNCH_DATE"];
  const sat2Fields = [...sat1Fields];

  // Build sat metadata from satcat data or raw CDM fields
  const sat1Data: Record<string, any> = { ...data.satcat_1 };
  const sat2Data: Record<string, any> = { ...data.satcat_2 };

  // Populate from CDM root if satcat is sparse
  if (!sat1Data.OBJECT_NAME) sat1Data.OBJECT_NAME = sat1Name;
  if (!sat2Data.OBJECT_NAME) sat2Data.OBJECT_NAME = sat2Name;

  const tcaDate = new Date(tca);
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const tcaFormatted = `${months[tcaDate.getUTCMonth()]} ${tcaDate.getUTCDate()}, ${tcaDate.getUTCFullYear()} ${tcaDate.getUTCHours().toString().padStart(2,"0")}:${tcaDate.getUTCMinutes().toString().padStart(2,"0")}:${tcaDate.getUTCSeconds().toString().padStart(2,"0")} UTC`;

  const isDebris = (type: string | undefined) => {
    if (!type) return false;
    const t = type.toUpperCase();
    return t.includes("DEBRIS") || t.includes("DEB") || t === "TBA";
  };
  const isBothDebris = isDebris(sat1Data.OBJECT_TYPE) && isDebris(sat2Data.OBJECT_TYPE);

  return (
    <main className="min-h-screen flex flex-col h-screen">
      {/* Header */}
      <header className="px-4 py-2 border-b border-[#30363d] bg-[#161b22] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-[#484f58] hover:text-[#e6edf3] transition-colors text-[13px]">
            ←
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[14px] font-semibold text-[#e6edf3]">
                {sat1Name} <span className="text-[#484f58] text-[12px]">vs</span> {sat2Name}
              </h1>
            </div>
            <div className="font-data text-[11px] text-[#484f58] flex items-center gap-3">
              <span>CDM {cdm_id}</span>
              {norad1 && <span>NORAD {norad1} / {norad2}</span>}
              <span>TCA {tcaFormatted}</span>
            </div>
          </div>
        </div>

        {/* Quick stats — plain text, no badges */}
        <div className="flex items-center gap-5 font-data text-[12px]">
          <div className="text-right">
            <div className="text-[9px] text-[#484f58] uppercase tracking-wider">Miss</div>
            <div className="text-[#7d8590]">
              {missDistance < 1000 ? `${missDistance.toFixed(0)} m` : `${(missDistance / 1000).toFixed(1)} km`}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[9px] text-[#484f58] uppercase tracking-wider">Pc</div>
            <div className="text-[#7d8590]">{pc.toExponential(2)}</div>
          </div>
          <div className="text-right">
            <div className="text-[9px] text-[#484f58] uppercase tracking-wider">Risk</div>
            <div className={`font-bold ${riskColor[riskLevel] || "text-[#7d8590]"}`}>
              {riskLevel}
            </div>
          </div>
        </div>
      </header>

      {/* Two-column layout */}
      <div className="flex-1 overflow-hidden flex flex-col md:flex-row">
        {/* Left: 60% — Cesium globe */}
        <div className="w-full md:w-[60%] h-full relative">
          <CesiumWrapper
            cdmId={cdm_id}
            tca={tca}
            missDistance={missDistance}
            riskLevel={riskLevel}
            covarianceRadii1={data.covariance_radii_1}
            covarianceRadii2={data.covariance_radii_2}
          />
        </div>

        {/* Right: 40% — Data panels */}
        <div className="w-full md:w-[40%] h-full overflow-y-auto bg-[#0d1117] border-l border-[#30363d] shrink-0">
          {/* Satellite metadata — two panels side by side */}
          <div className="grid grid-cols-2 gap-0">
            <SatMetadataPanel title={`SAT1 · ${sat1Name}`} data={sat1Data} fields={sat1Fields} />
            <SatMetadataPanel title={`SAT2 · ${sat2Name}`} data={sat2Data} fields={sat2Fields} />
          </div>

          {/* Independent Pc verification */}
          <div className="border-t border-[#30363d]">
            <PcVerificationPanel cdmId={cdm_id} />
          </div>

          {/* Pc maturation chart */}
          {pcHistory.length > 1 && (
            <div className="border-t border-[#30363d]">
              <PcEvolutionChart history={pcHistory} />
            </div>
          )}

          {/* Maneuver panels */}
          {data.maneuver && (
            <div className="border-t border-[#30363d]">
              <ManeuverPanel maneuver={data.maneuver} cdmId={cdm_id} />
            </div>
          )}

          <div className="border-t border-[#30363d]">
            <ManeuverTradeoff cdmId={cdm_id} disabled={isBothDebris} />
          </div>

          {/* AI Brief — plain paragraphs with thin top border separator */}
          <div className="border-t border-[#30363d]">
            <AIExplainer explanation={data.explanation} />
          </div>
        </div>
      </div>
    </main>
  );
}
