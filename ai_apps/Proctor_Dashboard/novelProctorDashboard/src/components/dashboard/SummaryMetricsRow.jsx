import React, { useEffect, useState } from "react"
import { motion } from "framer-motion"
import {
  ShieldCheck,
  AlertOctagon,
  AlertTriangle,
  AlertCircle,
  CheckCircle,
  Info,
  ChevronRight,
  ChevronDown,
  ChevronUp
} from "lucide-react"
import { getTrustLabel } from "../../lib/eventSeverity"
import { ScoreBreakdownDrawer } from "./ScoreBreakdownDrawer"

const VIOLATION_LABELS = {
  MOBILE_PHONE: 'Mobile Phone Detected',
  TAB_SWITCHED: 'Tab / Window Switch',
  MULTIPLE_PEOPLE: 'Multiple People Detected',
  MULTIPLE_FACES: 'Multiple Faces Detected',
  NO_FACE: 'No Face Detected',
  GAZE_AWAY: 'Candidate Looking Away',
  FACE_COVERED: 'Face Covered',
  AUDIO_VAD: 'Background Noise / Voice Detected',
  MULTIPLE_MONITORS: 'Multiple Monitors Detected',
};

function formatRuleLabel(type) {
  if (!type) return 'None';
  return VIOLATION_LABELS[type] || String(type).replace(/_/g, ' ');
}

const CARD_CLASS =
  "flex min-h-[100px] min-w-0 flex-1 flex-col rounded-[10px] border border-white/[0.06] bg-[#121212] px-5 py-4"

function TrustScoreSegment({ trustScore, animateOnLoad, onClick, postTestAnalysisStatus }) {
  const ringSize = 60
  const radius = 24
  const strokeWidth = 3
  const circumference = 2 * Math.PI * radius
  const isPending = postTestAnalysisStatus === 'PENDING'
  const isLoading = trustScore == null
  const displayScore = isLoading ? 0 : Math.min(Math.max(trustScore, 0), 100)
  const offset = circumference - (circumference * displayScore) / 100
  const { text, color } = getTrustLabel(isLoading ? 0 : trustScore)

  return (
    <div
      className="flex flex-col justify-between h-full min-h-[76px] flex-1 cursor-pointer opacity-90 hover:opacity-100 px-4 transition-opacity w-full xl:w-auto"
      onClick={onClick}
    >
      <span className="text-sm font-medium uppercase text-[#999999] tracking-wide">Trust Score</span>

      <div className="flex items-center justify-between w-full mt-1">
        <div className="flex items-end gap-2">
          {isPending ? (
            <div className="flex flex-col gap-1">
              <span className="text-[18px] font-semibold leading-tight tracking-tight text-[#f59e0b] animate-pulse">
                Final Score Pending
              </span>
              <span className="text-xs text-[#888] leading-tight">Post-test analysis in progress…</span>
            </div>
          ) : (
            <>
              <span className="text-[32px] font-semibold leading-[25px] tracking-tight" style={{ color: isLoading ? '#555' : color }}>
                {isLoading ? '—' : `${displayScore}%`}
              </span>
              {!isLoading && (
                <span
                  className="whitespace-nowrap flex items-center justify-center rounded-[2px] px-1.5 py-0.5 text-[11px] font-medium tracking-[0.6px] mb-0.5"
                  style={{ color, backgroundColor: `${color}1a` }}
                >
                  {text}
                </span>
              )}
            </>
          )}
        </div>

        <div className="relative shrink-0" style={{ width: ringSize, height: ringSize }}>
          <svg className="h-full w-full -rotate-90" viewBox={`0 0 ${ringSize} ${ringSize}`}>
            <circle cx={ringSize / 2} cy={ringSize / 2} r={radius} fill="#202020" />
            <circle cx={ringSize / 2} cy={ringSize / 2} r={radius} fill="none" stroke="#2b2b2b" strokeWidth={strokeWidth} />
            <motion.circle
              cx={ringSize / 2} cy={ringSize / 2} r={radius} fill="none"
              stroke={isPending ? '#f59e0b' : (isLoading ? '#2b2b2b' : color)}
              strokeWidth={strokeWidth} strokeLinecap="round" strokeDasharray={circumference}
              initial={animateOnLoad ? { strokeDashoffset: circumference } : false}
              animate={{ strokeDashoffset: isPending ? circumference * 0.7 : offset }}
              transition={{ duration: 1, ease: "easeOut", delay: 0.1 }}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <ShieldCheck className="h-5 w-5" style={{ color: isPending ? '#f59e0b' : (isLoading ? '#555' : color) }} strokeWidth={2} />
          </div>
        </div>
      </div>
    </div>
  )
}

function RiskSegment({ label, count, icon: Icon, colorHex, isActive, onClick }) {
  return (
    <div
      onClick={onClick}
      className={`flex flex-col justify-between h-full min-h-[76px] flex-1 cursor-pointer px-4 transition-opacity w-full xl:w-auto ${isActive ? 'opacity-100' : 'opacity-70 hover:opacity-100'
        }`}
    >
      <span className="text-sm font-medium uppercase text-[#999999] tracking-wide">{label}</span>

      <div className="flex items-center justify-between w-full mt-1 gap-2">
        <div className="flex items-baseline shrink-0">
          <span className="text-[32px] font-semibold leading-[25px] text-white mr-1.5">{count}</span>
          <span className="text-xs font-medium text-[#737373] uppercase tracking-wider">Flags</span>
        </div>
        <div className="flex h-[48px] w-[48px] shrink-0 items-center justify-center rounded-[14px] bg-black/20">
          <Icon className="h-5 w-5" style={{ color: colorHex }} strokeWidth={2} />
        </div>
      </div>
    </div>
  )
}

export function SummaryMetricsRow({ trustScore, severityCounts, riskPayload, events = [], activeSeverityFilter, onSeverityFilter, postTestAnalysisStatus }) {
  const [animateOnLoad, setAnimateOnLoad] = useState(true)
  const [isExplainOpen, setIsExplainOpen] = useState(false)

  useEffect(() => {
    setAnimateOnLoad(true)
    const timer = setTimeout(() => setAnimateOnLoad(false), 1200)
    return () => clearTimeout(timer)
  }, [trustScore])

  const toggleFilter = (tier) => {
    if (activeSeverityFilter === tier) {
      onSeverityFilter('ALL')
    } else {
      onSeverityFilter(tier)
    }
  }

  const isLoading = trustScore == null;

  return (
    <div className="flex w-full flex-col gap-[18px]">
      {/* Unified Metrics Bar */}
      <div className="relative flex w-full flex-col xl:flex-row items-center justify-between rounded-[12px] border border-[#181818] bg-[#141414] px-2 py-3 xl:h-[108px] overflow-x-auto overflow-y-hidden isolate shadow-sm gap-4 xl:gap-0">

        <div className="z-10 w-full xl:flex-1">
          <TrustScoreSegment
            trustScore={trustScore}
            animateOnLoad={animateOnLoad}
            postTestAnalysisStatus={postTestAnalysisStatus}
            onClick={() => { if (!isLoading && riskPayload) setIsExplainOpen(true) }}
          />
        </div>

        <div className="hidden xl:block h-[96px] w-px bg-white/[0.04] mx-1 z-10 shrink-0" />

        <div className="z-10 w-full xl:flex-1">
          <RiskSegment
            label="Critical Risk"
            count={severityCounts.critical || 0}
            icon={AlertOctagon}
            colorHex="#ff3333"
            isActive={activeSeverityFilter === 'CRITICAL'}
            onClick={() => toggleFilter('CRITICAL')}
          />
        </div>

        <div className="hidden xl:block h-[96px] w-px bg-white/[0.04] mx-1 z-10 shrink-0" />

        <div className="z-10 w-full xl:flex-1">
          <RiskSegment
            label="High Risk"
            count={severityCounts.high || 0}
            icon={AlertTriangle}
            colorHex="#F59E0B"
            isActive={activeSeverityFilter === 'HIGH'}
            onClick={() => toggleFilter('HIGH')}
          />
        </div>

        <div className="hidden xl:block h-[96px] w-px bg-white/[0.04] mx-1 z-10 shrink-0" />

        <div className="z-10 w-full xl:flex-1">
          <RiskSegment
            label="Moderate Risk"
            count={severityCounts.moderate || 0}
            icon={AlertCircle}
            colorHex="#EE7C20"
            isActive={activeSeverityFilter === 'MODERATE'}
            onClick={() => toggleFilter('MODERATE')}
          />
        </div>

        <div className="hidden xl:block h-[96px] w-px bg-white/[0.04] mx-1 z-10 shrink-0" />

        <div className="z-10 w-full xl:flex-1">
          <RiskSegment
            label="Low Risk"
            count={severityCounts.low || 0}
            icon={CheckCircle}
            colorHex="#039A03"
            isActive={activeSeverityFilter === 'LOW'}
            onClick={() => toggleFilter('LOW')}
          />
        </div>
      </div>

      <ScoreBreakdownDrawer
        isOpen={isExplainOpen}
        onClose={() => setIsExplainOpen(false)}
        trustScore={trustScore}
        riskPayload={riskPayload}
      />
    </div>
  )
}
