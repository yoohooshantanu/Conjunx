"use client";

import dynamic from "next/dynamic";

const CesiumViewer = dynamic(() => import("@/components/CesiumViewer"), { 
  ssr: false,
  loading: () => <div className="w-full h-full min-h-[400px] flex items-center justify-center bg-[#0d1117] text-[#484f58] text-[11px] font-data uppercase tracking-wider">Initializing viewer...</div>
});

interface Props {
  tca: string;
  missDistance: number;
  riskLevel: string;
  cdmId: string;
  covarianceRadii1?: number[];
  covarianceRadii2?: number[];
}

export default function CesiumWrapper(props: Props) {
  return <CesiumViewer {...props} />;
}
