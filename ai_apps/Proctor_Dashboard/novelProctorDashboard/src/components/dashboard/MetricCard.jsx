import React from "react"
import { motion } from "framer-motion"
import { cn } from "../../lib/utils"

export function MetricCard({ icon: Icon, label, value, animate = false, delay = 0, isLast = false }) {
  const isDisabled = value === 0 || value === "0";
  console.log('MetricCard rendered with value:', value, 'isDisabled:', isDisabled);

  return (
    <motion.div
      className={cn(
        "flex h-[70px] items-center justify-between rounded-xl p-4",
        !isLast && "border-b border-white/[0.06]",
        isDisabled && "pointer-events-none"
      )}
      initial={animate ? { opacity: 0, y: 10 } : false}
      animate={{
        opacity: isDisabled ? 0.35 : 1,
        y: 0,
      }}
      transition={{ duration: 0.4, delay, ease: "easeOut" }}
      aria-disabled={isDisabled || undefined}
    >
      <div className="flex items-center gap-3">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
          style={{ border: "1.67px solid var(--Primary, #2563EB)", background: "#0B1A3C8A" }}
        >
                    <Icon className="h-4 w-4" style={{ stroke: "#143ED6", fill: "#0B1A3C8A" }} strokeWidth={2} />
        </div>
        <span className="text-xs font-bold uppercase tracking-wider text-foreground">{label}</span>
      </div>
      <span className="text-xl font-black text-foreground">{value}</span>
    </motion.div>
  )
}
