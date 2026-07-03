import React from "react"
import { Monitor, Chrome } from "lucide-react"
import { Card } from "../ui/card"
import { TrustScoreWidget } from "./TrustScoreWidget"
import { SystemAnalysisOverview } from "./SystemAnalysisOverview"

export function RiskAnalysisPanel({ trustScore, riskBand, counters }) {
  // Compute total violations
  const totalViolations = (counters?.tabSwitched || 0) + 
                          (counters?.noFace || 0) + 
                          (counters?.multipleFaces || 0) + 
                          (counters?.noise || 0) + 
                          (counters?.multipleMonitors || 0);

  return (
    <Card className="flex flex-col h-full bg-card/60 backdrop-blur-xl border-white/5 p-6 overflow-y-auto">
      <h3 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-6">
        Risk Analysis
      </h3>

      {/* Trust Score */}
      <div className="mb-10">
        <TrustScoreWidget trustScore={trustScore} riskBand={riskBand} />
      </div>

      {/* Violations Summary */}
      <div className="flex items-center justify-between mb-10 pb-6 border-b border-white/10">
        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-bold text-orange-500">{totalViolations}</span>
          <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Total Violations</span>
        </div>
        <div className="flex gap-1.5">
          {[...Array(3)].map((_, i) => (
            <div key={i} className={`h-2 w-2 rounded-full ${i < Math.min(totalViolations, 3) ? 'bg-orange-500' : 'bg-white/10'}`} />
          ))}
        </div>
      </div>

      {/* Device Information */}
      <div className="mb-10">
        <h3 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-4">
          Device Information
        </h3>
        <div className="space-y-3">
          <div className="flex items-center gap-3 text-sm text-foreground font-medium">
            <Monitor className="h-4 w-4 text-muted-foreground" />
            <span>Desktop Environment</span>
          </div>
          <div className="flex items-center gap-3 text-sm text-foreground font-medium">
            <Chrome className="h-4 w-4 text-muted-foreground" />
            <span>Web Browser</span>
          </div>
        </div>
      </div>

      {/* System Analysis Overview */}
      <div className="mt-auto">
        <SystemAnalysisOverview counters={counters} />
      </div>
    </Card>
  )
}
