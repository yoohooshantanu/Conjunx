import { fetchConjunctions } from "@/lib/api";
import ConjunctionList from "@/components/ConjunctionList";

export const dynamic = "force-dynamic";


export default async function Home() {
  let conjunctions = [];
  try {
    conjunctions = await fetchConjunctions();
  } catch (e) {
    console.error(e);
  }

  const critCount = conjunctions.filter((c: any) => c.risk_level === "CRITICAL").length;
  const highCount = conjunctions.filter((c: any) => c.risk_level === "HIGH").length;
  const totalCount = conjunctions.length;

  return (
    <main className="min-h-screen">
      {/* Top bar */}
      <header className="border-b border-[#30363d] bg-[#161b22] px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-[15px] font-semibold text-[#e6edf3] tracking-tight">
            CONJUNX
          </h1>
          <span className="text-[12px] text-[#484f58]">
            Conjunction Analysis Engine
          </span>
        </div>

        <div className="flex items-center gap-5 text-[12px] font-data">
          <span className="text-[#7d8590]">
            {totalCount} events
          </span>
          {critCount > 0 && (
            <span className="text-[#f85149]">
              {critCount} CRITICAL
            </span>
          )}
          {highCount > 0 && (
            <span className="text-[#d29922]">
              {highCount} HIGH
            </span>
          )}
        </div>
      </header>

      {/* Event list */}
      <div className="px-6 py-0">
        <ConjunctionList data={conjunctions} />
      </div>
    </main>
  );
}
