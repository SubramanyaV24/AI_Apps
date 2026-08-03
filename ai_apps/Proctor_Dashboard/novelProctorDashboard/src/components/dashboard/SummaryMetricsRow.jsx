import React, { useEffect, useState } from "react"
import { motion } from "framer-motion"
import {
  ShieldCheck,
  AlertTriangle,
  BadgeDollarSign,
  ClipboardList,
  Info,
  TrendingUp,
  Repeat,
  Activity,
  AlertOctagon,
  ChevronDown,
  ChevronUp
} from "lucide-react"
import { getTrustLabel } from "../../lib/eventSeverity"

const VIOLATION_LABELS = {
  MOBILE_PHONE:      'Mobile Phone Detected',
  TAB_SWITCHED:      'Tab / Window Switch',
  MULTIPLE_PEOPLE:   'Multiple People Detected',
  MULTIPLE_FACES:    'Multiple Faces Detected',
  NO_FACE:           'No Face Detected',
  GAZE_AWAY:         'Candidate Looking Away',
  FACE_COVERED:      'Face Covered',
  AUDIO_VAD:         'Background Noise / Voice Detected',
  SPLIT_SCREEN:      'Split Screen Detected',
  MULTIPLE_MONITORS: 'Multiple Monitors Detected',
};

function formatRuleLabel(type) {
  if (!type) return 'None';
  return VIOLATION_LABELS[type] || String(type).replace(/_/g, ' ');
}

const CARD_CLASS =
  "flex min-h-[100px] min-w-0 flex-1 flex-col rounded-[10px] border border-white/[0.06] bg-[#121212] px-5 py-4"

const LABEL_CLASS =
  "text-[10px] font-medium uppercase tracking-[0.1em] text-[#8f8f8f]"

function TrustScoreCard({ trustScore, animateOnLoad }) {
  const ringSize = 56
  const radius = 22
  const strokeWidth = 5
  const circumference = 2 * Math.PI * radius
  const isLoading = trustScore == null
  const displayScore = isLoading ? 0 : Math.min(Math.max(trustScore, 0), 100)
  const offset = circumference - (circumference * displayScore) / 100
  const { text, color } = getTrustLabel(isLoading ? 0 : trustScore)

  return (
    <div className={CARD_CLASS}>
      <p className={LABEL_CLASS}>Trust Score</p>
      <div className="mt-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <motion.span
            className="text-[32px] font-semibold leading-none tracking-tight"
            style={{ color: isLoading ? '#555' : color }}
            initial={animateOnLoad ? { opacity: 0, y: 6 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
          >
            {isLoading ? '—' : `${displayScore}%`}
          </motion.span>
          {!isLoading && (
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
          )}
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
              stroke={isLoading ? '#2b2b2b' : color}
              strokeWidth={strokeWidth}
              strokeLinecap="round"
              strokeDasharray={circumference}
              initial={animateOnLoad ? { strokeDashoffset: circumference } : false}
              animate={{ strokeDashoffset: offset }}
              transition={{ duration: 1, ease: "easeOut", delay: 0.1 }}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <ShieldCheck className="h-5 w-5" style={{ color: isLoading ? '#555' : color }} strokeWidth={2.25} />
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

export function SummaryMetricsRow({ trustScore, severityCounts, riskPayload }) {
  const [animateOnLoad, setAnimateOnLoad] = useState(true)
  const [isExplainOpen, setIsExplainOpen] = useState(false)

  useEffect(() => {
    setAnimateOnLoad(true)
    const timer = setTimeout(() => setAnimateOnLoad(false), 1200)
    return () => clearTimeout(timer)
  }, [trustScore])

  return (
    <div className="flex w-full flex-col gap-[18px]">
      <div className="grid w-full grid-cols-1 gap-[18px] sm:grid-cols-2 xl:grid-cols-5">
        <TrustScoreCard trustScore={trustScore} animateOnLoad={animateOnLoad} />
        <RiskMetricCard
          label="Critical Risk"
          count={severityCounts.critical || 0}
          icon={AlertOctagon}
          iconBgClass="bg-[#800000]/25"
          iconClass="text-[#ff3333]"
          animateOnLoad={animateOnLoad}
          delay={0.04}
        />
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
          iconBgClass="bg-[#22c55e]/15"
          iconClass="text-[#22c55e]"
          animateOnLoad={animateOnLoad}
          delay={0.24}
        />
      </div>

      {/* Severity Engine Explainability Panel (Parallel Run) */}
      {riskPayload && (() => {
        const trustVal = Math.round(100 - (riskPayload.risk_value ?? 0));
        const { text: trustText, color: trustColor } = getTrustLabel(trustVal);

        return (
          <motion.div
            className="flex flex-col rounded-[10px] border border-blue-500/20 bg-[#121212] p-5 shadow-[0_0_15px_rgba(59,130,246,0.05)]"
            initial={animateOnLoad ? { opacity: 0, y: 10 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.3, ease: "easeOut" }}
          >
            <div 
              className="flex items-center justify-between cursor-pointer select-none" 
              onClick={() => setIsExplainOpen(!isExplainOpen)}
            >
              <div className="flex items-center gap-2">
                <Info className="h-5 w-5 text-blue-400" />
                <h3 className="text-sm font-semibold tracking-wide text-white">
                  Why this score? <span className="ml-2 text-xs font-normal text-blue-400/80">(Trust Score Calculation)</span>
                </h3>
              </div>
              <div className="text-gray-400 hover:text-white transition-colors">
                {isExplainOpen ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
              </div>
            </div>

            {isExplainOpen && (
              <div className="flex flex-col gap-4 mt-5 pt-4 border-t border-white/[0.06]">
                <p className="text-xs text-gray-400 leading-relaxed font-normal">
                  The candidate's final <strong className="text-white font-semibold">Trust Score ({trustVal}%)</strong> starts at <strong className="text-white font-semibold">100%</strong> (Full Trust) and is reduced by deductions for their worst violation, repeated behaviors, or suspicious combined patterns.
                </p>
                
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <div className="flex flex-col gap-1 rounded-md bg-white/[0.02] p-3 border border-white/[0.04]">
                    <span className="flex items-center gap-1.5 text-xs text-gray-400 font-medium">
                      <TrendingUp className="h-3.5 w-3.5 text-red-400" /> Worst Violation Deduction
                    </span>
                    <div className="flex items-baseline gap-2">
                      <span className="text-xl font-semibold text-white">-{riskPayload.severity_anchor || 0}%</span>
                      <span className="text-[10px] text-gray-500 truncate" title={formatRuleLabel(riskPayload.anchor_rule)}>
                        via {formatRuleLabel(riskPayload.anchor_rule)}
                      </span>
                    </div>
                    <p className="text-[10px] text-gray-500 leading-normal mt-1">
                      The initial trust reduction for the candidate's worst single action.
                    </p>
                  </div>

                  <div className="flex flex-col gap-1 rounded-md bg-white/[0.02] p-3 border border-white/[0.04]">
                    <span className="flex items-center gap-1.5 text-xs text-gray-400 font-medium">
                      <Repeat className="h-3.5 w-3.5 text-amber-400" /> Repeated Action Penalty
                    </span>
                    <div className="flex items-baseline gap-2">
                      <span className="text-xl font-semibold text-white">-{riskPayload.repeat_bonus || 0}%</span>
                    </div>
                    <p className="text-[10px] text-gray-500 leading-normal mt-1">
                      Further trust deducted when the candidate repeats the same violation.
                    </p>
                  </div>

                  <div className="flex flex-col gap-1 rounded-md bg-white/[0.02] p-3 border border-white/[0.04]">
                    <span className="flex items-center gap-1.5 text-xs text-gray-400 font-medium">
                      <Activity className="h-3.5 w-3.5 text-blue-400" /> Suspicious Pattern Penalty
                    </span>
                    <div className="flex items-baseline gap-2">
                      <span className="text-xl font-semibold text-white">-{riskPayload.correlation_bonus || 0}%</span>
                    </div>
                    <p className="text-[10px] text-gray-500 leading-normal mt-1">
                      Further trust deducted when different violations occur within 30 seconds.
                    </p>
                  </div>
                </div>
                
                <div className="mt-1 flex items-center justify-between border-t border-white/[0.06] pt-3 text-xs">
                  <span className="text-gray-400 font-normal">
                    Total Calculated Trust: <strong className="text-white">{trustVal}% / 100%</strong>
                  </span>
                  <span 
                    className="rounded px-2 py-0.5 font-semibold text-[10px] uppercase tracking-wider"
                    style={{
                      color: trustColor,
                      backgroundColor: `${trustColor}1f`,
                      border: `1px solid ${trustColor}2d`
                    }}
                  >
                    {trustText}
                  </span>
                </div>
              </div>
            )}
          </motion.div>
        );
      })()}
    </div>
  )
}
