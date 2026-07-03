import React, { useEffect, useState } from "react"
import { motion } from "framer-motion"
import {
  ShieldCheck,
  AlertTriangle,
  BadgeDollarSign,
  ClipboardList,
} from "lucide-react"
import { getTrustLabel } from "../../lib/eventSeverity"

const CARD_CLASS =
  "flex min-h-[100px] min-w-0 flex-1 flex-col rounded-[10px] border border-white/[0.06] bg-[#121212] px-5 py-4"

const LABEL_CLASS =
  "text-[10px] font-medium uppercase tracking-[0.1em] text-[#8f8f8f]"

function TrustScoreCard({ trustScore, animateOnLoad }) {
  const ringSize = 56
  const radius = 22
  const strokeWidth = 5
  const circumference = 2 * Math.PI * radius
  const clampedScore = Math.min(Math.max(trustScore, 0), 100)
  const offset = circumference - (circumference * clampedScore) / 100
  const { text, color } = getTrustLabel(trustScore)

  return (
    <div className={CARD_CLASS}>
      <p className={LABEL_CLASS}>Trust Score</p>
      <div className="mt-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <motion.span
            className="text-[32px] font-semibold leading-none tracking-tight"
            style={{ color }}
            initial={animateOnLoad ? { opacity: 0, y: 6 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
          >
            {clampedScore}%
          </motion.span>
          <motion.span
            className="inline-flex h-6 items-center rounded-md px-2.5 text-[11px] font-medium"
            style={{
              color,
              backgroundColor: `${color}1f`,
            }}
            initial={animateOnLoad ? { opacity: 0, scale: 0.92 } : false}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4, delay: 0.15, ease: "easeOut" }}
          >
            {text}
          </motion.span>
        </div>
        <motion.div
          className="relative shrink-0"
          style={{ width: ringSize, height: ringSize }}
          initial={animateOnLoad ? { opacity: 0, scale: 0.85 } : false}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        >
          <svg
            className="h-full w-full -rotate-90"
            viewBox={`0 0 ${ringSize} ${ringSize}`}
            aria-hidden
          >
            <circle
              cx={ringSize / 2}
              cy={ringSize / 2}
              r={radius}
              fill="none"
              stroke="#2b2b2b"
              strokeWidth={strokeWidth}
            />
            <motion.circle
              cx={ringSize / 2}
              cy={ringSize / 2}
              r={radius}
              fill="none"
              stroke={color}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              strokeDasharray={circumference}
              initial={animateOnLoad ? { strokeDashoffset: 0 } : false}
              animate={{ strokeDashoffset: offset }}
              transition={{ duration: 1, ease: "easeOut", delay: 0.1 }}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <ShieldCheck className="h-5 w-5" style={{ color }} strokeWidth={2.25} />
          </div>
        </motion.div>
      </div>
    </div>
  )
}

function RiskMetricCard({ label, count, icon: Icon, iconBgClass, iconClass, animateOnLoad, delay = 0 }) {
  return (
    <motion.div
      className={CARD_CLASS}
      initial={animateOnLoad ? { opacity: 0, y: 10 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: "easeOut" }}
    >
      <p className={LABEL_CLASS}>{label}</p>
      <div className="mt-3 flex items-center justify-between gap-3">
        <p className="flex items-baseline gap-1.5">
          <span className="text-[32px] font-semibold leading-none text-white">{count}</span>
          <span className="pb-0.5 text-[13px] font-normal text-[#9a9a9a]">Violations</span>
        </p>
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] ${iconBgClass}`}
        >
          <Icon className={`h-5 w-5 ${iconClass}`} strokeWidth={2.25} />
        </div>
      </div>
    </motion.div>
  )
}

export function SummaryMetricsRow({ trustScore, severityCounts }) {
  const [animateOnLoad, setAnimateOnLoad] = useState(true)

  useEffect(() => {
    setAnimateOnLoad(true)
    const timer = setTimeout(() => setAnimateOnLoad(false), 1200)
    return () => clearTimeout(timer)
  }, [trustScore])

  return (
    <div className="grid w-full grid-cols-1 gap-[18px] sm:grid-cols-2 xl:grid-cols-4">
      <TrustScoreCard trustScore={trustScore} animateOnLoad={animateOnLoad} />
      <RiskMetricCard
        label="High Risk"
        count={severityCounts.high}
        icon={AlertTriangle}
        iconBgClass="bg-[#ff5252]/15"
        iconClass="text-[#ff5252]"
        animateOnLoad={animateOnLoad}
        delay={0.08}
      />
      <RiskMetricCard
        label="Moderate Risk"
        count={severityCounts.moderate}
        icon={BadgeDollarSign}
        iconBgClass="bg-[#ffab40]/15"
        iconClass="text-[#ffab40]"
        animateOnLoad={animateOnLoad}
        delay={0.16}
      />
      <RiskMetricCard
        label="Low Risk"
        count={severityCounts.low}
        icon={ClipboardList}
        iconBgClass="bg-[#22c55e]/30"
        iconClass="text-[#448aff]"
        animateOnLoad={animateOnLoad}
        delay={0.24}
      />
    </div>
  )
}
