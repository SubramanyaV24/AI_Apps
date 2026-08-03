import React, { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Copy, UserMinus, Users, AudioLines, Monitor, AppWindow, X, Smartphone, UserX, EyeOff } from "lucide-react"
import { MetricCard } from "./MetricCard"

const METRICS = [
  { key: "mobilePhone",      icon: Smartphone, label: "Mobile Phone",    violationTypes: ["MOBILE_PHONE"] },
  { key: "tabSwitched",      icon: Copy,       label: "Tab Switches",    violationTypes: ["TAB_SWITCHED"] },
  { key: "splitScreen",      icon: AppWindow,  label: "Split Screen",    violationTypes: ["SPLIT_SCREEN"] },
  { key: "noFace",           icon: UserMinus,  label: "Face Missing",    violationTypes: ["NO_FACE"] },
  { key: "multipleFaces",    icon: Users,      label: "Multiple Faces",  violationTypes: ["MULTIPLE_PEOPLE", "MULTIPLE_FACES"] },
  { key: "faceCovered",      icon: UserX,      label: "Face Covered",    violationTypes: ["FACE_COVERED"] },
  { key: "gazeAway",         icon: EyeOff,     label: "Looking Away",    violationTypes: ["GAZE_AWAY"] },
  { key: "noise",            icon: AudioLines, label: "Noise Events",    violationTypes: ["AUDIO_VAD", "NOISE"] },
  { key: "multipleMonitors", icon: Monitor,    label: "External Monitor",violationTypes: ["MULTIPLE_MONITORS"] },
]

export function SystemAnalysisOverview({ counters, sessionKey, activeViolationFilter, onViolationFilter }) {
  const [animateCards, setAnimateCards] = useState(true)

  useEffect(() => {
    setAnimateCards(true)
    const timer = setTimeout(() => setAnimateCards(false), 900)
    return () => clearTimeout(timer)
  }, [sessionKey])

  const handleClick = (key) => {
    if (!onViolationFilter) return
    // Toggle: clicking active filter clears it
    onViolationFilter(activeViolationFilter === key ? null : key)
  }

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-white/[0.06] bg-[#121212]">
      <div className="flex items-center justify-between px-4 pt-4 pb-1">
        <motion.h3
          className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground"
          initial={animateCards ? { opacity: 0, y: -4 } : false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: "easeOut" }}
        >
          System Analysis Overview
        </motion.h3>
        {activeViolationFilter && onViolationFilter && (
          <button
            type="button"
            onClick={() => onViolationFilter(null)}
            className="flex items-center gap-1 rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-semibold text-blue-300 hover:bg-blue-500/25 transition-colors"
            aria-label="Clear violation filter"
          >
            {METRICS.find(m => m.key === activeViolationFilter)?.label || activeViolationFilter}
            <X className="h-2.5 w-2.5" />
          </button>
        )}
      </div>
      {onViolationFilter && (
        <p className="px-4 pb-2 text-[9px] text-muted-foreground/60">Click a row to filter the timeline</p>
      )}
      <div className="flex-1 overflow-y-auto">
        {METRICS.map((metric, index) => (
          <MetricCard
            key={metric.key}
            icon={metric.icon}
            label={metric.label}
            value={counters?.[metric.key] || 0}
            animate={animateCards}
            delay={index * 0.07}
            isLast={index === METRICS.length - 1}
            onClick={onViolationFilter ? () => handleClick(metric.key) : undefined}
            isActive={activeViolationFilter === metric.key}
          />
        ))}
      </div>
    </div>
  )
}
