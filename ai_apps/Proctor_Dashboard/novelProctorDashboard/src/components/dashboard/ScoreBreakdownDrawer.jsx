import React, { useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { X, Info } from "lucide-react"

const VIOLATION_LABELS = {
  MOBILE_PHONE:      'Mobile Phone',
  TAB_SWITCHED:      'Tab Switch',
  MULTIPLE_PEOPLE:   'Multiple People',
  MULTIPLE_FACES:    'Multiple Faces',
  NO_FACE:           'No Face',
  GAZE_AWAY:         'Gaze Away',
  FACE_COVERED:      'Face Covered',
  AUDIO_VAD:         'Voice Detected',
  MULTIPLE_MONITORS: 'Multiple Monitors',
}

function formatRuleLabel(type) {
  if (!type) return 'Unknown'
  return VIOLATION_LABELS[type] || String(type).replace(/_/g, ' ')
}

export function ScoreBreakdownDrawer({ isOpen, onClose, trustScore, riskPayload }) {
  // Prevent body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [isOpen])

  const trustVal = trustScore == null ? 0 : Math.min(Math.max(trustScore, 0), 100)
  
  const anchorPenalty = riskPayload?.severity_anchor || 0
  const anchorRule = riskPayload?.anchor_rule
  const repeatPenalty = riskPayload?.repeat_bonus || 0
  const correlationPenalty = riskPayload?.correlation_bonus || 0
  
  // Calculate total deductions and starting score
  const totalDeductions = anchorPenalty + repeatPenalty + correlationPenalty
  const startingScore = 100
  const calculatedScore = Math.max(0, startingScore - totalDeductions)

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100]"
            onClick={onClose}
          />
          
          {/* Drawer */}
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 200 }}
            className="fixed inset-y-0 right-0 w-full max-w-sm bg-[#121212] border-l border-white/10 shadow-2xl z-[101] flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-white/5">
              <h2 className="text-lg font-semibold text-white">Trust Score Breakdown</h2>
              <button 
                onClick={onClose}
                className="p-1.5 rounded-full text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            
            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-8">
              
              {/* Receipt */}
              <div className="flex flex-col gap-3 font-mono text-sm">
                <div className="flex justify-between items-center text-lg mb-4">
                  <span className="text-white font-semibold">Current score</span>
                  <span className="text-white font-bold">{trustVal}</span>
                </div>
                
                <div className="flex justify-between text-gray-400">
                  <span>Starting score</span>
                  <span>100</span>
                </div>
                
                {/* Deductions */}
                {anchorPenalty > 0 && (
                  <div className="flex justify-between text-red-400">
                    <span className="truncate pr-4">{formatRuleLabel(anchorRule)}</span>
                    <span>-{anchorPenalty}</span>
                  </div>
                )}
                
                {repeatPenalty > 0 && (
                  <div className="flex justify-between text-red-400">
                    <span className="truncate pr-4">Repeated action penalty</span>
                    <span>-{repeatPenalty}</span>
                  </div>
                )}
                
                {correlationPenalty > 0 && (
                  <div className="flex justify-between text-red-400">
                    <span className="truncate pr-4">Suspicious pattern penalty</span>
                    <span>-{correlationPenalty}</span>
                  </div>
                )}
                
                {/* Total Line */}
                <div className="mt-2 border-t border-white/10 pt-3 flex justify-between font-bold text-white">
                  <span>Final Calculation</span>
                  <span>{calculatedScore}</span>
                </div>
              </div>

              {/* Rationale Section */}
              <div className="flex flex-col gap-3 mt-4">
                <div className="flex items-center gap-2">
                  <Info className="h-4 w-4 text-blue-400" />
                  <h3 className="text-sm font-semibold text-white tracking-wide">Why is this risky?</h3>
                </div>
                <div className="text-xs text-gray-400 leading-relaxed space-y-3">
                  <p>
                    The candidate's score started at 100% and was reduced based on isolated incidents, repeated offenses, and suspicious combinations of behavior.
                  </p>
                  {anchorPenalty > 0 && (
                    <p>
                      The largest single deduction came from a <strong className="text-white">{formatRuleLabel(anchorRule)}</strong> violation, which establishes the baseline penalty of -{anchorPenalty}%.
                    </p>
                  )}
                  {repeatPenalty > 0 && (
                    <p>
                      Because the candidate repeated identical violations during the session, an additional escalating multiplier applied a -{repeatPenalty}% penalty.
                    </p>
                  )}
                  {correlationPenalty > 0 && (
                    <p>
                      Furthermore, the candidate triggered different violations within a short 30-second window. This suspicious behavioral pattern resulted in an additional -{correlationPenalty}% deduction.
                    </p>
                  )}
                </div>
              </div>
              
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
