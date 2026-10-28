import React, { useEffect, useMemo, useState, useRef } from "react"
import { Music, PlaySquare, X, Clock, AlertTriangle, ChevronDown, ListFilter } from "lucide-react"
import {
  getEvidenceMediaType,
  isPreviewableEvidence,
  resolveEvidenceUrl,
} from "../../lib/evidenceUtils"
import { EvidencePreviewModal } from "./EvidencePreviewModal"

const MAX_PAGE_BUTTONS = 5

/** Maps the counter key used in SystemAnalysisOverview → event_type strings */
const FILTER_KEY_TO_EVENT_TYPES = {
  tabSwitched:      ["TAB_SWITCHED"],
  noFace:           ["NO_FACE"],
  multipleFaces:    ["MULTIPLE_PEOPLE", "MULTIPLE_FACES"],
  noise:            ["AUDIO_VAD", "NOISE"],
  multipleMonitors: ["MULTIPLE_MONITORS"],
  mobilePhone:      ["MOBILE_PHONE"],
  gazeAway:         ["GAZE_AWAY"],
  faceCovered:      ["FACE_COVERED"],
  fullScreenExit:   ["FULL_SCREEN_EXIT"],
  copyPaste:        ["COPY_PASTE"],
  rightClick:       ["RIGHT_CLICK"],
}

/** Human-readable label for each filter key */
const FILTER_KEY_LABELS = {
  tabSwitched:      "Tab Switches",
  noFace:           "Face Missing",
  multipleFaces:    "Multiple Faces",
  noise:            "Noise Events",
  multipleMonitors: "External Monitor",
  mobilePhone:      "Mobile Phone",
  gazeAway:         "Looking Away",
  faceCovered:      "Face Covered",
  fullScreenExit:   "Full Screen Exit",
  copyPaste:        "Copy/Paste",
  rightClick:       "Right-click Attempt",
}

const VIOLATION_LABELS = {
  MOBILE_PHONE:      'Mobile Phone Detected',
  TAB_SWITCHED:      'Tab / Window Switch',
  MULTIPLE_PEOPLE:   'Multiple People Detected',
  MULTIPLE_FACES:    'Multiple Faces Detected',
  NO_FACE:           'No Face Detected',
  GAZE_AWAY:         'Candidate Looking Away',
  FACE_COVERED:      'Face Covered',
  AUDIO_VAD:         'Background Noise / Voice Detected',
  MULTIPLE_MONITORS: 'Multiple Monitors Detected',
  FULL_SCREEN_EXIT:  'Full Screen Exited',
  COPY_PASTE:        'Copy/Paste Attempted',
  RIGHT_CLICK:       'Right-click Attempted',
}

const SEVERITY_COLORS = {
  critical: "bg-[#800000]/25 text-[#ff3333] border-[#ff3333]/20",
  high: "bg-[#ff5252]/15 text-[#ff5252] border-[#ff5252]/20",
  medium: "bg-[#ffab40]/15 text-[#ffab40] border-[#ffab40]/20",
  moderate: "bg-[#ffab40]/15 text-[#ffab40] border-[#ffab40]/20",
  low: "bg-[#22c55e]/15 text-[#22c55e] border-[#22c55e]/20",
}

const SEVERITY_DOT_COLORS = {
  critical: "bg-[#ff3333]",
  high: "bg-[#ff5252]",
  medium: "bg-[#ffab40]",
  moderate: "bg-[#ffab40]",
  low: "bg-[#22c55e]",
}

function formatEventTitle(evt) {
  // 1. Prefer human-readable label stored in metadata at violation time
  if (evt && typeof evt === 'object') {
    if (evt.label) return evt.label
    const type = evt.violationType || evt.type || evt.event_type
    // Known label map (consistent across both frontends)
    if (type && VIOLATION_LABELS[type]) return VIOLATION_LABELS[type]
    // Fall back to title-casing the raw enum
    if (type) return type.split('_').map((w) => w.charAt(0) + w.slice(1).toLowerCase()).join(' ')
    return 'Event'
  }
  // Legacy string call
  if (!evt) return 'Event'
  if (VIOLATION_LABELS[evt]) return VIOLATION_LABELS[evt]
  return evt.split('_').map((w) => w.charAt(0) + w.slice(1).toLowerCase()).join(' ')
}

function EvidenceThumbnail({ evt, onPreview }) {
  const [imgFailed, setImgFailed] = useState(false)
  const displayUrl = resolveEvidenceUrl(evt.evidence)
  const mediaType = getEvidenceMediaType(evt.evidence, evt.evidenceType, evt.violationType || evt.type)

  useEffect(() => {
    setImgFailed(false)
  }, [displayUrl])

  if (mediaType === "audio") {
    return (
      <button
        type="button"
        className="flex h-14 w-20 shrink-0 flex-col items-center justify-center gap-1 rounded border border-white/10 bg-blue-500/10 transition-all hover:ring-2 hover:ring-blue-500/50"
        onClick={onPreview}
        aria-label="Preview audio evidence"
      >
        <Music className="h-5 w-5 text-blue-400" />
        <span className="text-[9px] font-semibold text-blue-400">AUDIO</span>
      </button>
    )
  }

  return (
    <button
      type="button"
      className="group relative flex h-14 w-20 shrink-0 items-center justify-center overflow-hidden rounded border border-white/10 bg-black/40 transition-all hover:ring-2 hover:ring-blue-500/50"
      onClick={onPreview}
      aria-label="Preview evidence image"
    >
      {imgFailed || !displayUrl ? (
        <span className="text-[10px] font-semibold text-muted-foreground">Preview</span>
      ) : (
        <img
          src={displayUrl}
          alt="Evidence thumbnail"
          className="h-full w-full object-cover opacity-80 transition-opacity group-hover:opacity-100"
          onError={() => setImgFailed(true)}
        />
      )}
    </button>
  )
}

export function SessionTimeline({ events, sessionKey, violationFilter, onClearFilter, severityFilter = "ALL" }) {
  const [preview, setPreview] = useState(null)
  const [sortMethod, setSortMethod] = useState("time_desc")
  const [isSortOpen, setIsSortOpen] = useState(false)
  const sortRef = useRef(null)

  useEffect(() => {
    function handleClickOutside(event) {
      if (sortRef.current && !sortRef.current.contains(event.target)) {
        setIsSortOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const sortedEvents = useMemo(() => {
    const parseTime = (val) => {
      if (!val) return 0;
      let d = new Date(val);
      if (!isNaN(d.getTime())) return d.getTime();
      d = new Date(`1970/01/01 ${val}`);
      if (!isNaN(d.getTime())) return d.getTime();
      return 0;
    };

    const SEVERITY_WEIGHT = {
      critical: 4,
      high: 3,
      medium: 2,
      moderate: 2,
      low: 1,
    };

    return [...events].sort((a, b) => {
      if (sortMethod === "risk_desc" || sortMethod === "risk_asc") {
        // Primary sort: Severity tier weight (Critical > High > Moderate > Low)
        const wA = SEVERITY_WEIGHT[a.severity?.toLowerCase()] || 0;
        const wB = SEVERITY_WEIGHT[b.severity?.toLowerCase()] || 0;
        if (wA !== wB) return sortMethod === "risk_desc" ? wB - wA : wA - wB;

        // Secondary sort: Backend penalty points (most robust within the same tier)
        const pA = a.penalty_points || 0;
        const pB = b.penalty_points || 0;
        if (pA !== pB) return sortMethod === "risk_desc" ? pB - pA : pA - pB;
      }
      
      // Fallback/Time sort: Chronological descending
      const ta = parseTime(a.timestamp || a.occurredAt);
      const tb = parseTime(b.timestamp || b.occurredAt);
      return tb - ta;
    })
  }, [events, sortMethod])

  // Apply filters
  const filteredEvents = useMemo(() => {
    let result = sortedEvents
    
    // 1. Violation type filter (from SystemAnalysisOverview)
    if (violationFilter) {
      const allowedTypes = FILTER_KEY_TO_EVENT_TYPES[violationFilter] || []
      if (allowedTypes.length > 0) {
        result = result.filter((evt) => {
          const t = (evt.violationType || evt.type || '').toUpperCase()
          return allowedTypes.includes(t)
        })
      }
    }
    
    // 2. Severity filter (local segmented control)
    if (severityFilter !== "ALL") {
      result = result.filter((evt) => {
        const sev = (evt.severity || 'low').toUpperCase()
        if (severityFilter === 'MODERATE' && sev === 'MEDIUM') return true
        return sev === severityFilter
      })
    }
    
    return result
  }, [sortedEvents, violationFilter, severityFilter])

  useEffect(() => {
    // No page state to reset — just scroll to top when session changes
  }, [sessionKey])

  const openPreview = (evt) => {
    const url = resolveEvidenceUrl(evt.evidence)
    if (!url || !isPreviewableEvidence(url, evt.evidenceType, evt.violationType || evt.type)) return
    setPreview({
      evidence: url,
      evidenceType: evt.evidenceType,
      eventType: evt.violationType || evt.type,
      title: formatEventTitle(evt),
    })
  }

  return (
    <>
      <div className="flex h-full max-h-full min-h-0 flex-col overflow-hidden max-lg:max-h-[min(50vh,26rem)]">
        <div className="mb-4 shrink-0 flex items-center justify-between gap-4 border-b border-white/[0.06] pb-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <ListFilter className="h-4 w-4 text-gray-400" />
              <span className="text-sm font-semibold text-gray-200">Flags</span>
              <span className="flex items-center justify-center rounded-md bg-white/[0.06] px-2 py-0.5 text-xs font-medium text-gray-400">
                {filteredEvents.length}
              </span>
            </div>
            {violationFilter && (
              <>
                <div className="h-4 w-px bg-white/10 mx-1" />
                <div className="flex items-center gap-1.5 rounded-full bg-blue-500/10 px-2.5 py-1 text-xs font-medium text-blue-300 border border-blue-500/20">
                  {FILTER_KEY_LABELS[violationFilter] || violationFilter}
                  <button 
                    type="button" 
                    onClick={onClearFilter} 
                    className="p-0.5 hover:bg-blue-500/20 rounded-full transition-colors"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              </>
            )}
          </div>

          {/* Sort Dropdown */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-gray-500">Sort by:</span>
            <div className="relative" ref={sortRef}>
              <button 
                type="button"
                onClick={() => setIsSortOpen(!isSortOpen)}
                className="flex items-center justify-between min-w-[100px] bg-[#1a1a1a] border border-white/5 text-gray-300 text-xs font-medium rounded-lg px-3 py-1.5 hover:bg-[#222] transition-colors"
              >
                {sortMethod === 'time_desc' && 'Latest'}
                {sortMethod === 'risk_desc' && 'Highest Risk'}
                {sortMethod === 'risk_asc' && 'Lowest Risk'}
                <ChevronDown className="h-3.5 w-3.5 text-gray-500 ml-2" />
              </button>
              
              {isSortOpen && (
                <div className="absolute right-0 top-full mt-1 w-36 bg-[#1e1e1e] border border-white/10 rounded-lg shadow-xl overflow-hidden z-50 py-1">
                  <button
                    type="button"
                    onClick={() => { setSortMethod('time_desc'); setIsSortOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-xs font-medium transition-colors ${sortMethod === 'time_desc' ? 'bg-blue-500/10 text-blue-400' : 'text-gray-300 hover:bg-white/5'}`}
                  >
                    Latest
                  </button>
                  <button
                    type="button"
                    onClick={() => { setSortMethod('risk_desc'); setIsSortOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-xs font-medium transition-colors ${sortMethod === 'risk_desc' ? 'bg-blue-500/10 text-blue-400' : 'text-gray-300 hover:bg-white/5'}`}
                  >
                    Highest Risk
                  </button>
                  <button
                    type="button"
                    onClick={() => { setSortMethod('risk_asc'); setIsSortOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-xs font-medium transition-colors ${sortMethod === 'risk_asc' ? 'bg-blue-500/10 text-blue-400' : 'text-gray-300 hover:bg-white/5'}`}
                  >
                    Lowest Risk
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="timeline-scroll-area min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-2 max-lg:overflow-y-scroll">
          {sortedEvents.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No events recorded in this session.
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No {FILTER_KEY_LABELS[violationFilter] || violationFilter} events found.
              {onClearFilter && (
                <button
                  type="button"
                  onClick={onClearFilter}
                  className="mt-2 block mx-auto text-xs text-blue-400 underline hover:text-blue-300"
                >
                  Clear filter
                </button>
              )}
            </div>
          ) : (
            <div className="flex flex-col">
              {filteredEvents.map((evt, idx) => {
                const isLast = idx === filteredEvents.length - 1
                const eventKey = evt.eventId || evt.timestamp || `${evt.violationType}-${evt.occurredAt}`
                const resolvedEvidence = resolveEvidenceUrl(evt.evidence)
                const canPreview = isPreviewableEvidence(
                  resolvedEvidence,
                  evt.evidenceType,
                  evt.violationType || evt.type
                )

                return (
                  <div
                    key={eventKey}
                    className={`relative flex gap-3 ${isLast ? "pb-0" : "pb-10"}`}
                  >
                    {/* Vertical stepper rail */}
                    <div className="relative flex w-4 shrink-0 justify-center">
                      {!isLast && (
                        <div className="absolute left-1/2 top-2.5 bottom-0 -translate-x-1/2 border-l border-[#373737]" />
                      )}
                      <div className={`relative z-10 mt-1 h-2.5 w-2.5 rounded-full ${SEVERITY_DOT_COLORS[evt.severity?.toLowerCase()] || 'bg-[#2563EB]'}`} />
                    </div>

                    {/* Event content */}
                    <div className="min-w-0 flex-1 flex gap-3 items-start">
                      {/* Left: title + message + timestamp */}
                      <div className="min-w-0 flex-1">
                        <div className="mb-1 flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-semibold text-foreground">
                              {formatEventTitle(evt)}
                            </h4>
                            {evt.severity && (
                              <span 
                                title={`${evt.severity} Severity Flag`}
                                className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${SEVERITY_COLORS[evt.severity.toLowerCase()] || SEVERITY_COLORS.low}`}
                              >
                                {evt.severity}
                              </span>
                            )}
                          </div>
                          {/* Timestamp only when no thumbnail (thumbnail rows show time inline) */}
                          {(!canPreview || !resolvedEvidence) && (
                            <span className="shrink-0 font-mono text-xs text-[#888888]">
                              {evt.occurredAt}
                            </span>
                          )}
                        </div>
                        <p className="text-sm leading-relaxed text-[#a3a3a3]">{evt.message}</p>
                        {canPreview && resolvedEvidence && (
                          <span className="mt-0.5 block font-mono text-xs text-[#888888]">
                            {evt.occurredAt}
                          </span>
                        )}
                      </div>

                      {/* Right: VIEW REPLAY + thumbnail — same level as text */}
                      {canPreview && resolvedEvidence && (
                        <div className="flex shrink-0 items-center gap-2">
                          <button
                            type="button"
                            className="inline-flex items-center gap-1.5 text-xs font-semibold transition-opacity duration-200"
                            style={{ color: '#4B66A4', opacity: 0.5 }}
                            onMouseEnter={e => e.currentTarget.style.opacity = '1'}
                            onMouseLeave={e => e.currentTarget.style.opacity = '0.5'}
                            onClick={() => openPreview({ ...evt, evidence: resolvedEvidence })}
                          >
                            <PlaySquare className="h-3.5 w-3.5" />
                            VIEW REPLAY
                          </button>
                          <EvidenceThumbnail
                            evt={{ ...evt, evidence: resolvedEvidence }}
                            onPreview={() => openPreview({ ...evt, evidence: resolvedEvidence })}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      <EvidencePreviewModal
        open={!!preview}
        onClose={() => setPreview(null)}
        title={preview?.title}
        evidence={preview?.evidence}
        evidenceType={preview?.evidenceType}
        eventType={preview?.eventType}
      />
    </>
  )
}
