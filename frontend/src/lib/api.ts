// Server components need absolute URLs. Client components need relative URLs to use the proxy (CORS).
export const API_URL = typeof window !== "undefined"
  ? "/api"
  : (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000");

export interface ConjunctionSummary {
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
}

export interface PcHistoryPoint {
  cdm_id: string;
  pc: number;
  created: string;
  miss_distance: number;
}

export interface ManeuverData {
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
}

export interface ConjunctionDetail {
  TCA?: string;
  tca?: string;
  MISS_DISTANCE?: number | string;
  MIN_RNG?: number | string;
  PC?: number | string;
  SAT_1_ID?: number | string;
  SAT2_NORAD_CAT_ID?: number | string;
  SAT1_NORAD_CAT_ID?: number | string;
  SAT_2_ID?: number | string;
  SAT_1_NAME?: string;
  SAT_2_NAME?: string;
  SAT1_OBJECT_NAME?: string;
  SAT2_OBJECT_NAME?: string;
  covariance_radii_1?: number[];
  covariance_radii_2?: number[];
  satcat_1?: Record<string, unknown>;
  satcat_2?: Record<string, unknown>;
  risk?: { level?: string };
  maneuver?: ManeuverData;
  [key: string]: unknown;
}


export async function fetchConjunctions(): Promise<ConjunctionSummary[]> {
  const res = await fetch(`${API_URL}/conjunctions`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch conjunctions");
  return res.json() as Promise<ConjunctionSummary[]>;
}

export async function fetchConjunctionDetail(id: string): Promise<ConjunctionDetail> {
  const res = await fetch(`${API_URL}/conjunctions/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch conjunction detail");
  return res.json() as Promise<ConjunctionDetail>;
}

export async function fetchOrbitData(id: string) {
  const res = await fetch(`${API_URL}/conjunctions/${id}/orbit-data`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch orbit data");
  return res.json();
}

export async function recomputeManeuver(id: string, payload: { satellite_mass_kg: number, isp: number }) {
  const res = await fetch(`${API_URL}/conjunctions/${id}/maneuver`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to recompute maneuver");
  return res.json();
}

export async function fetchTradeoff(id: string, payload: { delta_v_mps: number, satellite_mass_kg: number, isp: number }) {
  const res = await fetch(`${API_URL}/conjunctions/${id}/tradeoff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to evaluate tradeoff");
  return res.json();
}

export async function fetchPcAnalysis(id: string) {
  const res = await fetch(`${API_URL}/conjunctions/${id}/pc-analysis`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch Pc analysis");
  return res.json();
}

export async function fetchPcHistory(id: string): Promise<PcHistoryPoint[]> {
  const res = await fetch(`${API_URL}/conjunctions/${id}/pc-history`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch Pc history");
  return res.json() as Promise<PcHistoryPoint[]>;
}

export async function fetchAiExplanation(id: string) {
  const res = await fetch(`${API_URL}/conjunctions/${id}/explanation`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch AI explanation");
  return res.json();
}
