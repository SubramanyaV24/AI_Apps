import React from "react"
import { motion } from "framer-motion"
import { cn } from "../../lib/utils"

export function MetricCard({ icon: Icon, label, value, animate = false, delay = 0, isLast = false, onClick, isActive = false }) {
  const isDisabled = value === 0 || value === "0";

  return (
    <motion.div
      className={cn(
        "flex h-[70px] items-center justify-between rounded-xl p-4 transition-all duration-200",
        !isLast && "border-b border-white/[0.06]",
        isDisabled && !isActive && "pointer-events-none",
        onClick && !isDisabled && "cursor-pointer",
        isActive
          ? "bg-blue-500/10 ring-1 ring-blue-500/40"
          : onClick && !isDisabled && "hover:bg-white/5"
      )}
      initial={animate ? { opacity: 0, y: 10 } : false}
      animate={{
        opacity: isDisabled && !isActive ? 0.35 : 1,
        y: 0,
      }}
      transition={{ duration: 0.4, delay, ease: "easeOut" }}
      aria-disabled={isDisabled && !isActive || undefined}
      onClick={onClick && !isDisabled ? onClick : undefined}
      role={onClick && !isDisabled ? "button" : undefined}
      tabIndex={onClick && !isDisabled ? 0 : undefined}
      onKeyDown={onClick && !isDisabled ? (e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); } : undefined}
    >
      <div className="flex items-center gap-3">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
          style={{
            border: isActive ? "1.67px solid #60a5fa" : "1.67px solid var(--Primary, #2563EB)",
            background: isActive ? "#1d3563" : "#0B1A3C8A"
          }}
        >
          <Icon className="h-4 w-4" style={{ stroke: isActive ? "#93c5fd" : "#143ED6", fill: isActive ? "#1d3563" : "#0B1A3C8A" }} strokeWidth={2} />
        </div>
        <span className={cn("text-xs font-bold uppercase tracking-wider", isActive ? "text-blue-300" : "text-foreground")}>{label}</span>
      </div>
      <span className={cn("text-xl font-black", isActive ? "text-blue-300" : "text-foreground")}>{value}</span>
    </motion.div>
  )
}
