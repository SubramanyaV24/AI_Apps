import React, { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Filter, Loader2, Search, SlidersHorizontal, X, ChevronLeft, ChevronRight } from "lucide-react"
import { Card } from "../ui/card"
import { Badge } from "../ui/badge"
import { Checkbox } from "../ui/checkbox"
import { Slider } from "../ui/slider"
import { getTrustBadgeClass } from "../../lib/eventSeverity"
import { filterSessions, getTotalCandidates } from "../../api/Proctor_Dashboard_Session_Api"

// ─── Constants ───────────────────────────────────────────────────────────────

const RISK_OPTIONS = [
  { value: "CRITICAL", label: "Critical Risk", dot: "bg-[#800000]" },
  { value: "HIGH",     label: "High Risk",     dot: "bg-red-500" },
  { value: "MEDIUM",   label: "Moderate Risk", dot: "bg-amber-400" },
  { value: "LOW",      label: "Low Risk",      dot: "bg-emerald-400" },
]

const DEFAULT_FILTERS = {
  riskLevels: [],
  trustMin: 0,
  trustMax: 100,
}

function isLiveSession(status) {
  return status === "STARTED" || status === "IN_PROGRESS"
}

// ─── Filter Popover ───────────────────────────────────────────────────────────

function FilterPopover({ filters, onChange, onReset, onClose }) {
  const { riskLevels, trustMin, trustMax } = filters

  const toggleRisk = (val) => {
    const next = riskLevels.includes(val)
      ? riskLevels.filter((r) => r !== val)
      : [...riskLevels, val]
    onChange({ ...filters, riskLevels: next })
  }

  const activeCount = riskLevels.length + (trustMin > 0 || trustMax < 100 ? 1 : 0)

  return (
    <div className="absolute right-0 top-10 z-50 w-64 rounded-xl border border-white/10 bg-[#1a1a1a] p-4 shadow-2xl">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-[#888]" />
          <span className="text-xs font-bold uppercase tracking-widest text-[#888]">Filter</span>
        </div>
        <div className="flex items-center gap-2">
          {activeCount > 0 && (
            <button
              type="button"
              onClick={onReset}
              className="text-xs font-semibold text-red-600 hover:text-red-500 transition-colors"
            >
              Clear
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded p-0.5 text-red-600 hover:bg-red-600/10 hover:text-red-500 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Risk Level */}
      <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#666]">Risk Level</p>
      <div className="mb-4 flex flex-col gap-1.5">
        {RISK_OPTIONS.map(({ value, label, dot }) => (
          <label
            key={value}
            className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-white/5"
          >
            <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
            <Checkbox
              checked={riskLevels.includes(value)}
              onCheckedChange={() => toggleRisk(value)}
            />
            <span className="text-sm text-foreground">{label}</span>
          </label>
        ))}
      </div>

      {/* Trust Score range */}
      <p className="mb-1 mt-6 text-[10px] font-bold uppercase tracking-widest text-[#666]">Risk Rate</p>
      <p className="text-xs font-semibold text-foreground mb-4">
        {trustMin}% – {trustMax}%
      </p>
      <Slider
        min={0}
        max={100}
        value={[trustMin, trustMax]}
        onValueChange={([lo, hi]) => onChange({ ...filters, trustMin: lo, trustMax: hi })}
      />
    </div>
  )
}

// ─── CandidateList ────────────────────────────────────────────────────────────

export function CandidateList({
  sessions: propSessions,
  selectedSessionId,
  onSelectSession,
}) {
  const [search, setSearch] = useState("")
  const [filterOpen, setFilterOpen] = useState(false)
  const [filters, setFilters] = useState(DEFAULT_FILTERS)

  // Remote-filtered sessions state
  const [sessions, setSessions] = useState(propSessions || [])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [totalCandidates, setTotalCandidates] = useState(0)

  const popoverRef = useRef(null)
  const abortRef   = useRef(null)

  // ── Active filter count badge ──
  const activeFilters = useMemo(() => {
    let n = filters.riskLevels.length
    if (filters.trustMin > 0 || filters.trustMax < 100) n++
    return n
  }, [filters])

  // ── Fetch overall candidate count (independent of filters) ──
  const fetchTotalCandidates = useCallback(async () => {
    try {
      const result = await getTotalCandidates()
      if (typeof result?.total_candidates === "number") {
        setTotalCandidates(result.total_candidates)
      }
    } catch (err) {
      console.error("getTotalCandidates error:", err)
    }
  }, [])

  useEffect(() => {
    fetchTotalCandidates()
    const interval = setInterval(fetchTotalCandidates, 5000)
    return () => clearInterval(interval)
  }, [fetchTotalCandidates])

  // ── Close popover on outside click ──
  useEffect(() => {
    if (!filterOpen) return
    const handle = (e) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setFilterOpen(false)
      }
    }
    document.addEventListener("mousedown", handle)
    return () => document.removeEventListener("mousedown", handle)
  }, [filterOpen])

  // ── Fetch from API whenever search/filters/page change ──
  const fetchFiltered = useCallback(async (query, f, p) => {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    try {
      const result = await filterSessions({
        query,
        riskLevels: f.riskLevels,
        trustMin: f.trustMin,
        trustMax: f.trustMax,
        page: p,
        limit: 25,
      })
      if (controller.signal.aborted) return
      setSessions(result?.sessions || [])
      setTotalPages(result?.total_pages || 1)
      setTotal(result?.total || 0)
    } catch (err) {
      if (!controller.signal.aborted) {
        console.error("filterSessions error:", err)
        // Fallback: show prop sessions filtered client-side
        setSessions(propSessions || [])
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [propSessions])

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => {
      setPage(1)
      fetchFiltered(search, filters, 1)
    }, 300)
    return () => clearTimeout(t)
  }, [search, filters, fetchFiltered])

  useEffect(() => {
    fetchFiltered(search, filters, page)
  }, [page]) // eslint-disable-line react-hooks/exhaustive-deps

  const resetFilters = () => {
    setFilters(DEFAULT_FILTERS)
    setFilterOpen(false)
  }

  // Generate pagination blocks
  const getPaginationItems = () => {
    const items = []
    if (totalPages <= 5) {
      for (let i = 1; i <= totalPages; i++) items.push(i)
    } else {
      if (page <= 3) {
        items.push(1, 2, 3, '...', totalPages - 1, totalPages)
      } else if (page >= totalPages - 2) {
        items.push(1, 2, '...', totalPages - 2, totalPages - 1, totalPages)
      } else {
        items.push(1, '...', page - 1, page, page + 1, '...', totalPages)
      }
    }
    return items
  }

  return (
    <Card className="flex h-full min-h-0 flex-col overflow-hidden border-white/10 bg-[#111111]">

      {/* ── Total Candidates Card ── */}
      <div className="shrink-0 p-3 pb-0">
        <div className="relative overflow-hidden rounded-xl border border-blue-500/20 bg-gradient-to-br from-blue-500/10 to-transparent p-4">
          <div className="absolute right-4 top-4 h-2 w-2 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.8)]"></div>
          <p className="mb-2 text-[10px] font-bold tracking-wider text-blue-500 uppercase">
            Total Candidates
          </p>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-blue-500">{totalCandidates}</span>
            <span className="text-xs text-[#666]">Candidates analyzed</span>
          </div>
        </div>
      </div>

      {/* ── Search + Filter bar ── */}
      <div className="shrink-0 border-b border-white/10 p-3 pt-4">
        <div className="flex items-center gap-2">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#555]" />
            <input
              type="text"
              placeholder="Search candidate…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 py-2 pl-8 pr-3 text-sm text-foreground transition-all focus:outline-none focus:ring-1 focus:ring-blue-500 placeholder:text-[#555]"
            />
          </div>

          {/* Filter toggle */}
          <div className="relative" ref={popoverRef}>
            <button
              type="button"
              onClick={() => setFilterOpen((o) => !o)}
              className={`relative flex h-9 w-9 items-center justify-center rounded-lg border transition-all duration-200
                ${filterOpen || activeFilters > 0
                  ? "border-blue-500/50 bg-blue-500/10 text-blue-400"
                  : "border-white/10 bg-white/5 text-[#888] hover:bg-white/10 hover:text-white"}`}
              aria-label="Open filters"
            >
              <SlidersHorizontal className="h-4 w-4" />
              {activeFilters > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-blue-500 text-[9px] font-bold text-white">
                  {activeFilters}
                </span>
              )}
            </button>

            {filterOpen && (
              <FilterPopover
                filters={filters}
                onChange={(f) => { setFilters(f); setPage(1) }}
                onReset={resetFilters}
                onClose={() => setFilterOpen(false)}
              />
            )}
          </div>
        </div>

        {/* Active filter chips */}
        {activeFilters > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {filters.riskLevels.map((r) => (
              <span
                key={r}
                className="flex items-center gap-1 rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-semibold text-blue-300"
              >
                {r}
                <button
                  type="button"
                  onClick={() => setFilters((f) => ({ ...f, riskLevels: f.riskLevels.filter((x) => x !== r) }))}
                  className="hover:text-white"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            ))}
            {(filters.trustMin > 0 || filters.trustMax < 100) && (
              <span className="flex items-center gap-1 rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-semibold text-blue-300">
                Trust {filters.trustMin}–{filters.trustMax}%
                <button
                  type="button"
                  onClick={() => setFilters((f) => ({ ...f, trustMin: 0, trustMax: 100 }))}
                  className="hover:text-white"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Session list ── */}
      <div className="candidate-list-scroll min-h-0 flex-1 space-y-0.5 overflow-y-auto overflow-x-hidden p-2">
        {loading && sessions.length === 0 ? (
          <div className="flex items-center justify-center gap-2 py-10 text-xs text-[#555]">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : sessions.length === 0 ? (
          <div className="py-10 text-center text-sm text-[#555]">No candidates found.</div>
        ) : (
          sessions.map((session) => {
            const trust = session.trust_score ?? 100
            const isSelected = selectedSessionId === session.name
            const badgeColor = getTrustBadgeClass(trust)
            const live = isLiveSession(session.status)

            return (
              <button
                key={session.name}
                type="button"
                onClick={() => onSelectSession(session.name)}
                className={`flex w-full flex-col gap-1 rounded-lg border px-3 py-2.5 text-left transition-all duration-200
                  ${isSelected
                    ? "border-blue-500/40 bg-blue-950/50 shadow-[0_0_12px_rgba(59,130,246,0.15)]"
                    : "border-transparent bg-transparent hover:bg-white/5"}`}
              >
                <div className="flex w-full items-center justify-between gap-2">
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
                    {session.user_name || session.user_id || "Unknown"}
                  </span>
                  <Badge variant="outline" className={`shrink-0 font-mono text-[10px] ${badgeColor}`}>
                    {trust}% Trust
                  </Badge>
                </div>

                {/* Sub-row: live indicator or violation count */}
                <div className="flex items-center gap-2">
                  {live && (
                    <span className="flex items-center gap-1 text-[10px] font-medium text-emerald-400">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                      Live
                    </span>
                  )}
                  {session.violation_count > 0 && (
                    <span className="text-[10px] text-[#666]">
                      {session.violation_count} violation{session.violation_count !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </button>
            )
          })
        )}

        {/* Loading more indicator */}
        {loading && sessions.length > 0 && (
          <div className="flex items-center justify-center gap-2 py-3 text-xs text-[#555]">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Updating…
          </div>
        )}
      </div>

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="shrink-0 border-t border-white/10 px-3 py-4">
          <div className="flex items-center justify-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="flex h-9 w-9 items-center justify-center rounded-md bg-[#1a1a1a] text-[#666] hover:bg-white/10 hover:text-white disabled:bg-transparent disabled:opacity-50 disabled:pointer-events-none transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>

            {getPaginationItems().map((p, i) => (
              p === '...' ? (
                <span key={i} className="flex h-9 w-9 items-center justify-center bg-transparent text-[#666] text-sm font-medium tracking-widest">
                  ...
                </span>
              ) : (
                <button
                  key={i}
                  type="button"
                  onClick={() => setPage(p)}
                  className={`flex h-9 w-9 items-center justify-center rounded-md text-sm font-bold transition-colors ${
                    page === p
                      ? "border border-blue-600 bg-transparent text-blue-500"
                      : "bg-[#1a1a1a] text-[#666] hover:bg-white/10 hover:text-white"
                  }`}
                >
                  {p}
                </button>
              )
            ))}

            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="flex h-9 w-9 items-center justify-center rounded-md bg-[#1a1a1a] text-[#666] hover:bg-white/10 hover:text-white disabled:bg-transparent disabled:opacity-50 disabled:pointer-events-none transition-colors"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </Card>
  )
}
