import React, { useState } from "react"
import { Clock, Download, User, Trash2, X, Hash, Calendar } from "lucide-react"
import { Button } from "../ui/button"

export function CandidateProfileHeader({
  userName,
  userEmail,
  candidatePhoto,
  sessionWindow,
  onDownloadReport,
  onDeleteCandidate,
  hasSession,
  atsId,
  testDate,
}) {
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  if (!hasSession) {
    return (
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Select a candidate to view session details.</p>
      </div>
    )
  }

  return (
    <>
      <div className="flex items-center justify-between gap-4 py-3">
        <div className="flex items-center gap-4 min-w-0">
          <div
            className={`h-16 w-16 shrink-0 overflow-hidden rounded-lg border border-white/10 bg-white/5 ${candidatePhoto ? 'cursor-pointer hover:opacity-80 transition-opacity' : ''}`}
            onClick={() => candidatePhoto && setIsPreviewOpen(true)}
          >
            {candidatePhoto ? (
              <img src={candidatePhoto} alt={userName} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-muted-foreground">
                <User className="h-8 w-8" />
              </div>
            )}
          </div>
          <div className="min-w-0">
            <h2 className="truncate text-xl font-bold text-foreground">{userName || "Candidate"}</h2>
            <p className="truncate text-sm text-muted-foreground">{userEmail || "No email"}</p>

            {/* ATS ID + Test Date row */}
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5">
              {atsId && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Hash className="h-3 w-3 shrink-0 text-blue-400" />
                  <span className="font-mono text-blue-300 font-medium">{atsId}</span>
                </span>
              )}
              {testDate && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Calendar className="h-3 w-3 shrink-0" />
                  <span>{testDate}</span>
                </span>
              )}
            </div>

            <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="h-3.5 w-3.5" />
              <span>{sessionWindow || "—"}</span>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="destructive"
            className="shrink-0 gap-2"
            onClick={onDeleteCandidate}
          >
            <Trash2 className="h-4 w-4" />
            Delete Record
          </Button>
          <Button
            variant="secondary"
            className="shrink-0 gap-2 border-white/10 bg-white/5 text-foreground hover:bg-white/10"
            onClick={onDownloadReport}
          >
            <Download className="h-4 w-4" />
            Download Report
          </Button>
        </div>
      </div>

      {isPreviewOpen && candidatePhoto && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
          onClick={() => setIsPreviewOpen(false)}
        >
          <div className="relative max-w-4xl max-h-full" onClick={(e) => e.stopPropagation()}>
            <Button
              variant="ghost"
              size="icon"
              className="absolute -top-12 right-0 text-white hover:bg-white/20 rounded-full"
              onClick={() => setIsPreviewOpen(false)}
            >
              <X className="h-6 w-6" />
            </Button>
            <img
              src={candidatePhoto}
              alt={userName}
              className="max-h-[85vh] w-auto rounded-lg object-contain shadow-2xl border border-white/20"
            />
          </div>
        </div>
      )}
    </>
  )
}
