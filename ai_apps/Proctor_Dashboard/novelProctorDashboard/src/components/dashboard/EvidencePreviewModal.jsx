import React, { useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { Loader2, Music, X } from "lucide-react"
import {
  getEvidenceMediaType,
  resolveEvidenceUrl,
  resolvePlayableAudioSrc,
} from "../../lib/evidenceUtils"

export function EvidencePreviewModal({ open, onClose, title, evidence, evidenceType, eventType }) {
  const [imgError, setImgError] = useState(false)
  const [audioSrc, setAudioSrc] = useState(null)
  const [audioLoading, setAudioLoading] = useState(false)
  const [audioError, setAudioError] = useState(null)
  const blobUrlRef = useRef(null)

  const displayUrl = resolveEvidenceUrl(evidence)

  useEffect(() => {
    setImgError(false)
  }, [displayUrl, open])

  useEffect(() => {
    if (!open || !evidence) {
      setAudioSrc(null)
      setAudioError(null)
      setAudioLoading(false)
      return undefined
    }

    const mediaType = getEvidenceMediaType(evidence, evidenceType, eventType)
    if (mediaType !== "audio") {
      setAudioSrc(null)
      setAudioError(null)
      return undefined
    }

    let cancelled = false
    setAudioLoading(true)
    setAudioError(null)
    setAudioSrc(null)

    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }

    resolvePlayableAudioSrc(evidence).then(({ src, error, isBlob }) => {
      if (cancelled) {
        if (isBlob && src) URL.revokeObjectURL(src)
        return
      }
      setAudioLoading(false)
      if (!src) {
        setAudioError(error || "Unable to load audio")
        return
      }
      if (isBlob) blobUrlRef.current = src
      setAudioSrc(src)
      if (error) setAudioError(error)
    })

    return () => {
      cancelled = true
    }
  }, [open, evidence, evidenceType, eventType])

  useEffect(() => {
    return () => {
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current)
        blobUrlRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open || !evidence) return null

  const mediaType = getEvidenceMediaType(evidence, evidenceType, eventType)
  const openInNewTab = () => {
    if (displayUrl) window.open(displayUrl, "_blank", "noopener,noreferrer")
  }

  const content = (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={title || "Evidence preview"}
    >
      <div
        className="relative flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-white/10 bg-[#1a1a1a] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-3">
          <h4 className="truncate pr-4 text-sm font-semibold text-foreground">
            {title || "Evidence Preview"}
          </h4>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground"
            aria-label="Close preview"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex min-h-[200px] flex-1 items-center justify-center overflow-auto bg-black/50 p-6">
          {mediaType === "audio" ? (
            <div className="w-full max-w-lg space-y-4 text-center">
              <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-blue-500/15">
                <Music className="h-10 w-10 text-blue-400" />
              </div>
              {audioLoading && (
                <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading audio…
                </div>
              )}
              {!audioLoading && audioSrc && (
                <audio
                  key={audioSrc}
                  controls
                  preload="auto"
                  src={audioSrc}
                  className="w-full"
                  onError={() => setAudioError("Playback failed. Try opening in a new tab.")}
                />
              )}
              {!audioLoading && !audioSrc && displayUrl && (
                <audio
                  key={displayUrl}
                  controls
                  preload="auto"
                  src={displayUrl}
                  className="w-full"
                  onError={() => setAudioError("Playback failed. Try opening in a new tab.")}
                />
              )}
              {!audioLoading && audioError && (
                <p className="text-sm text-red-400">{audioError}</p>
              )}
              <p className="text-xs text-muted-foreground">Audio evidence clip</p>
              <button
                type="button"
                onClick={openInNewTab}
                className="text-xs font-semibold text-blue-400 hover:text-blue-300 hover:underline"
              >
                Open in new tab
              </button>
            </div>
          ) : mediaType === "video" ? (
            <video
              key={displayUrl}
              controls
              src={displayUrl}
              className="max-h-[calc(92vh-140px)] w-full max-w-full rounded-lg"
            />
          ) : imgError || !displayUrl ? (
            <div className="space-y-3 text-center">
              <p className="text-sm text-muted-foreground">Could not load image preview.</p>
              <button
                type="button"
                onClick={openInNewTab}
                className="text-sm font-semibold text-blue-400 hover:underline"
              >
                Open evidence in new tab
              </button>
            </div>
          ) : (
            <img
              key={displayUrl}
              src={displayUrl}
              alt={title || "Evidence"}
              className="max-h-[calc(92vh-140px)] w-auto max-w-full rounded-lg object-contain"
              onError={() => setImgError(true)}
            />
          )}
        </div>
      </div>
    </div>
  )

  return createPortal(content, document.body)
}
