import React, { useEffect, useMemo, useState } from "react"
import { Music, PlaySquare, X } from "lucide-react"
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
  splitScreen:      ["SPLIT_SCREEN"],
  noFace:           ["NO_FACE"],
  multipleFaces:    ["MULTIPLE_PEOPLE", "MULTIPLE_FACES"],
  noise:            ["AUDIO_VAD", "NOISE"],
  multipleMonitors: ["MULTIPLE_MONITORS"],
  mobilePhone:      ["MOBILE_PHONE"],
  gazeAway:         ["GAZE_AWAY"],
  faceCovered:      ["FACE_COVERED"],
}

/** Human-readable label for each filter key */
const FILTER_KEY_LABELS = {
  tabSwitched:      "Tab Switches",
  splitScreen:      "Split Screen",
  noFace:           "Face Missing",
  multipleFaces:    "Multiple Faces",
  noise:            "Noise Events",
  multipleMonitors: "External Monitor",
  mobilePhone:      "Mobile Phone",
  gazeAway:         "Looking Away",
  faceCovered:      "Face Covered",
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
  SPLIT_SCREEN:      'Split Screen Detected',
  MULTIPLE_MONITORS: 'Multiple Monitors Detected',
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

export function SessionTimeline({ events, sessionKey, violationFilter, onClearFilter }) {
  const [preview, setPreview] = useState(null)

  const sortedEvents = useMemo(() => {
    const parseTime = (val) => {
      if (!val) return 0;
      let d = new Date(val);
      if (!isNaN(d.getTime())) return d.getTime();
      d = new Date(`1970/01/01 ${val}`);
      if (!isNaN(d.getTime())) return d.getTime();
      return 0;
    };
    return [...events].sort((a, b) => {
      const ta = parseTime(a.timestamp || a.occurredAt);
      const tb = parseTime(b.timestamp || b.occurredAt);
      return tb - ta;
    })
  }, [events])

  // Apply violation type filter from SystemAnalysisOverview
  const filteredEvents = useMemo(() => {
    if (!violationFilter) return sortedEvents
    const allowedTypes = FILTER_KEY_TO_EVENT_TYPES[violationFilter] || []
    if (allowedTypes.length === 0) return sortedEvents
    return sortedEvents.filter((evt) => {
      const t = (evt.violationType || evt.type || '').toUpperCase()
      return allowedTypes.includes(t)
    })
  }, [sortedEvents, violationFilter])

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
        <div className="mb-5 shrink-0 flex items-center justify-between gap-2">
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-[#888888]">
            Session Activity Timeline
          </h3>
          {violationFilter && (
            <button
              type="button"
              onClick={onClearFilter}
              className="flex items-center gap-1 rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-semibold text-blue-300 hover:bg-blue-500/25 transition-colors"
            >
              Filtering: {FILTER_KEY_LABELS[violationFilter] || violationFilter}
              <X className="h-2.5 w-2.5" />
            </button>
          )}
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
                      <div className="relative z-10 mt-1 h-2.5 w-2.5 rounded-full bg-[#2563EB]" />
                    </div>

                    {/* Event content */}
                    <div className="min-w-0 flex-1 flex gap-3 items-start">
                      {/* Left: title + message + timestamp */}
                      <div className="min-w-0 flex-1">
                        <div className="mb-1 flex items-start justify-between gap-2">
                          <h4 className="text-sm font-semibold text-foreground">
                            {formatEventTitle(evt)}
                          </h4>
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
