// Server components need absolute URLs. Client components need relative URLs to use the proxy (CORS).
export const API_URL = typeof window !== "undefined"
  ? "/api"
  : (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000");


export async function fetchConjunctions() {
  const res = await fetch(`${API_URL}/conjunctions`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch conjunctions");
  return res.json();
}

export async function fetchConjunctionDetail(id: string) {
  const res = await fetch(`${API_URL}/conjunctions/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch conjunction detail");
  return res.json();
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

export async function fetchPcHistory(id: string) {
  const res = await fetch(`${API_URL}/conjunctions/${id}/pc-history`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch Pc history");
  return res.json();
}

export async function fetchAiExplanation(id: string) {
  const res = await fetch(`${API_URL}/conjunctions/${id}/explanation`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch AI explanation");
  return res.json();
}
