export default function Loading() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0d1117] px-6">
      <div className="flex flex-col items-center gap-4 text-center">
        {/* Spinner */}
        <div className="w-8 h-8 rounded-full border-2 border-[#30363d] border-t-[#e6edf3] animate-spin"></div>
        <div className="text-[#8b949e] font-data text-[13px] animate-pulse tracking-wide uppercase">
          Fetching Conjunction Events...
        </div>
      </div>
    </div>
  );
}
