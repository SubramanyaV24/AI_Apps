import React, { useEffect, useMemo, useState } from "react"
import { ChevronLeft, ChevronRight, Music, PlaySquare } from "lucide-react"
import {
  getEvidenceMediaType,
  isPreviewableEvidence,
  resolveEvidenceUrl,
} from "../../lib/evidenceUtils"
import { EvidencePreviewModal } from "./EvidencePreviewModal"

const PAGE_SIZE = 5
const MAX_PAGE_BUTTONS = 5

/** Timeline rail — light gray nodes + connector (Figma stepper) */
const TIMELINE_DOT = "relative z-10 mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[#2563EB]"
const TIMELINE_LINE = "absolute left-1/2 top-3 h-full w-px -translate-x-1/2 bg-[#5a5a5a]"

const VIOLATION_LABELS = {
  MOBILE_PHONE:      'Mobile Phone Detected',
  TAB_SWITCHED:      'Tab / Window Switch',
  MULTIPLE_PEOPLE:   'Multiple People Detected',
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

function getPageNumbers(current, total) {
  if (total <= MAX_PAGE_BUTTONS) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }
  let start = Math.max(1, current - 2)
  let end = Math.min(total, start + MAX_PAGE_BUTTONS - 1)
  start = Math.max(1, end - MAX_PAGE_BUTTONS + 1)
  return Array.from({ length: end - start + 1 }, (_, i) => start + i)
}

function TimelinePagination({ page, totalPages, totalItems, onPageChange }) {
  if (totalPages <= 1) return null

  const pageNumbers = getPageNumbers(page, totalPages)
  const rangeStart = (page - 1) * PAGE_SIZE + 1
  const rangeEnd = Math.min(page * PAGE_SIZE, totalItems)

  return (
    <div className="mt-4 shrink-0 border-t border-white/10 pt-4">
      <p className="mb-2 text-center text-[10px] text-muted-foreground">
        Showing {rangeStart}–{rangeEnd} of {totalItems} events
      </p>
      <div className="flex items-center justify-center gap-1">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        {pageNumbers[0] > 1 && (
          <>
            <button
              type="button"
              onClick={() => onPageChange(1)}
              className="flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-xs font-semibold text-muted-foreground hover:bg-white/10"
            >
              1
            </button>
            {pageNumbers[0] > 2 && <span className="px-1 text-muted-foreground">…</span>}
          </>
        )}
        {pageNumbers.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onPageChange(p)}
            className={`flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-xs font-semibold transition-colors
              ${p === page
                ? "bg-blue-600 text-white"
                : "text-muted-foreground hover:bg-white/10 hover:text-foreground"}`}
          >
            {p}
          </button>
        ))}
        {pageNumbers[pageNumbers.length - 1] < totalPages && (
          <>
            {pageNumbers[pageNumbers.length - 1] < totalPages - 1 && (
              <span className="px-1 text-muted-foreground">…</span>
            )}
            <button
              type="button"
              onClick={() => onPageChange(totalPages)}
              className="flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-xs font-semibold text-muted-foreground hover:bg-white/10"
            >
              {totalPages}
            </button>
          </>
        )}
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
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

export function SessionTimeline({ events, sessionKey }) {
  const [page, setPage] = useState(1)
  const [preview, setPreview] = useState(null)

  const sortedEvents = useMemo(() => {
    return [...events].sort((a, b) => {
      const ta = new Date(a.timestamp || a.occurredAt || 0).getTime()
      const tb = new Date(b.timestamp || b.occurredAt || 0).getTime()
      return tb - ta
    })
  }, [events])

  const totalPages = Math.max(1, Math.ceil(sortedEvents.length / PAGE_SIZE))

  const paginatedEvents = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE
    return sortedEvents.slice(start, start + PAGE_SIZE)
  }, [sortedEvents, page])

  useEffect(() => {
    setPage(1)
  }, [sessionKey])

  useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

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
        <h3 className="mb-5 shrink-0 text-[10px] font-bold uppercase tracking-widest text-[#888888]">
          Session Activity Timeline
        </h3>

        <div className="timeline-scroll-area min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-2 max-lg:overflow-y-scroll">
          {sortedEvents.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No events recorded in this session.
            </div>
          ) : (
            <div className="flex flex-col">
              {paginatedEvents.map((evt, idx) => {
                const isLast = idx === paginatedEvents.length - 1
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

        {sortedEvents.length > 0 && (
          <TimelinePagination
            page={page}
            totalPages={totalPages}
            totalItems={sortedEvents.length}
            onPageChange={setPage}
          />
        )}
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
