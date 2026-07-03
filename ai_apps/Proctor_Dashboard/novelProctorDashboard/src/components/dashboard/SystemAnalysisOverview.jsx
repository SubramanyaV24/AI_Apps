import React, { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Copy, UserMinus, Users, AudioLines, Monitor, AppWindow } from "lucide-react"
import { MetricCard } from "./MetricCard"

const METRICS = [
  { key: "tabSwitched", icon: Copy, label: "Tab Switches" },
  { key: "splitScreen", icon: AppWindow, label: "Split Screen" },
  { key: "noFace", icon: UserMinus, label: "Face Missing" },
  { key: "multipleFaces", icon: Users, label: "Multiple Faces" },
  { key: "noise", icon: AudioLines, label: "Noise Events" },
  { key: "multipleMonitors", icon: Monitor, label: "External Monitor" },
]

export function SystemAnalysisOverview({ counters, sessionKey }) {
  const [animateCards, setAnimateCards] = useState(true)

  useEffect(() => {
    setAnimateCards(true)
    const timer = setTimeout(() => setAnimateCards(false), 900)
    return () => clearTimeout(timer)
  }, [sessionKey])

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-white/[0.06] bg-[#121212]">
      <motion.h3
        className="px-4 pt-4 text-[10px] font-bold uppercase tracking-widest text-muted-foreground"
        initial={animateCards ? { opacity: 0, y: -4 } : false}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
      >
        System Analysis Overview
      </motion.h3>
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
          />
        ))}
      </div>
    </div>
  )
}
