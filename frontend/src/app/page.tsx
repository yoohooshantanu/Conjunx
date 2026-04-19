import { fetchConjunctions } from "@/lib/api";
import ConjunctionList from "@/components/ConjunctionList";

export const dynamic = "force-dynamic";


import { Suspense } from "react";

function HeaderFallback() {
  return (
    <header className="border-b border-[#30363d] bg-[#161b22] px-4 md:px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
      <div className="flex items-center gap-4">
        <h1 className="text-[15px] font-semibold text-[#e6edf3] tracking-tight">CONJUNX</h1>
        <span className="text-[12px] text-[#484f58]">Conjunction Analysis Engine</span>
      </div>
      <div className="flex flex-wrap items-center gap-3 md:gap-5 text-[12px] font-data text-[#484f58] animate-pulse">
        <span>Loading events...</span>
      </div>
    </header>
  );
}

function ListFallback() {
  return (
    <div className="w-full flex items-center justify-center py-20">
      <div className="flex flex-col items-center gap-4">
        <div className="w-6 h-6 rounded-full border-2 border-[#30363d] border-t-[#e6edf3] animate-spin"></div>
        <div className="text-[#8b949e] font-data text-[11px] animate-pulse uppercase tracking-wider">Analyzing Conjunctions...</div>
      </div>
    </div>
  );
}

async function ConjunctionsData() {
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
    <>
      <header className="border-b border-[#30363d] bg-[#161b22] px-4 md:px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <h1 className="text-[15px] font-semibold text-[#e6edf3] tracking-tight">
            CONJUNX
          </h1>
          <span className="text-[12px] text-[#484f58]">
            Conjunction Analysis Engine
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-3 md:gap-5 text-[12px] font-data">
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

      <div className="w-full overflow-x-auto">
        <div className="min-w-[650px]">
          <ConjunctionList data={conjunctions} />
        </div>
      </div>
    </>
  );
}

export default function Home() {
  return (
    <main className="min-h-screen">
      <Suspense fallback={<><HeaderFallback /><ListFallback /></>}>
        <ConjunctionsData />
      </Suspense>
    </main>
  );
}
