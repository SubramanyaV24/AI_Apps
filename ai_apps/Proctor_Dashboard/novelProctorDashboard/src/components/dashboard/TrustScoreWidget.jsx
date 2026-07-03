import React from "react"
import { Card } from "../ui/card"
import { Badge } from "../ui/badge"
import { motion } from "framer-motion"

export function TrustScoreWidget({ trustScore, riskBand }) {
  const getTrustColor = () => {
    if (trustScore >= 90) return "#22c55e"
    if (trustScore >= 60) return "#f97316"
    return "#ef4444"
  }

  const getRiskColorClass = () => {
    if (riskBand?.toUpperCase() === 'LOW') return "text-green-500"
    if (riskBand?.toUpperCase() === 'MEDIUM') return "text-orange-500"
    return "text-red-500"
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-between items-start">
        <div className="flex items-baseline gap-1">
          <span className="text-5xl font-black tracking-tighter" style={{ color: getTrustColor() }}>
            {trustScore}
          </span>
          <span className="text-xl font-bold text-muted-foreground">%</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Risk Profile:</span>
          <span className={`text-xs font-bold ${getRiskColorClass()}`}>{riskBand || "LOW"}</span>
        </div>
      </div>
      
      <div className="space-y-2">
        <span className="text-xs font-bold text-primary tracking-widest uppercase">Trust Score</span>
        <div className="h-2 w-full bg-black/40 rounded-full overflow-hidden flex gap-1">
          <motion.div 
            className="h-full bg-green-500 rounded-full" 
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(trustScore, 33)}%` }}
            transition={{ duration: 1, ease: "easeOut" }}
          />
          <motion.div 
            className="h-full bg-orange-500 rounded-full" 
            initial={{ width: 0 }}
            animate={{ width: `${Math.max(0, Math.min(trustScore - 33, 33))}%` }}
            transition={{ duration: 1, ease: "easeOut", delay: 0.2 }}
          />
          <motion.div 
            className="h-full bg-red-500 rounded-full" 
            initial={{ width: 0 }}
            animate={{ width: `${Math.max(0, trustScore - 66)}%` }}
            transition={{ duration: 1, ease: "easeOut", delay: 0.4 }}
          />
        </div>
      </div>
    </div>
  )
}
