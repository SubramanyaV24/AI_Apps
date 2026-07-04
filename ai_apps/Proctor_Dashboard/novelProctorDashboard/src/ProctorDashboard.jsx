import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import './ProctorDashboard.css';
import proctorApi from './api/Proctor_Dashboard_Api';
import { listSessions, getSessionDetails } from './api/Proctor_Dashboard_Session_Api';

import { CandidateList } from './components/dashboard/CandidateList';
import { CandidateProfileHeader } from './components/dashboard/CandidateProfileHeader';
import { SummaryMetricsRow } from './components/dashboard/SummaryMetricsRow';
import { SessionTimeline } from './components/dashboard/SessionTimeline';
import { SystemAnalysisOverview } from './components/dashboard/SystemAnalysisOverview';
import { countEventsBySeverity } from './lib/eventSeverity';
import { getEvidenceProxyUrl, isSharePointUrl, resolveEvidenceUrl, resolveProfilePhotoUrl } from './lib/evidenceUtils';
import {
  buildReportPayload,
  downloadSessionReportCSV,
  downloadSessionReportPDF,
} from './lib/generateSessionReport';
import { Shield } from 'lucide-react';




// Inline SVGs for elegant UI icons
const ShieldIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '8px' }}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);

const UserIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const DownloadIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '6px' }}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

const AlertIcon = ({ color = "currentColor" }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '8px', flexShrink: 0 }}>
    <polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const LIVE_SESSION_STATUSES = new Set(['STARTED', 'IN_PROGRESS']);

function isLiveSessionStatus(status) {
  return LIVE_SESSION_STATUSES.has(status);
}

const ALERT_COOLDOWNS = {
  MULTIPLE_MONITORS: 30000, // 30 seconds
  MOBILE_PHONE: 30000,      // 30 seconds
  MULTIPLE_PEOPLE: 10000,   // 10 seconds
  NO_FACE: 10000,           // 10 seconds
  GAZE_AWAY: 5000,          // 5 seconds
  FACE_COVERED: 10000,      // 10 seconds
  AUDIO_VAD: 10000,         // 10 seconds
  TAB_SWITCHED: 5000,       // 5 seconds
};

// Human-readable display names for each violation type
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
};
function violationLabel(type) {
  return VIOLATION_LABELS[type] || (type || '').replace(/_/g, ' ');
}

export default function App() {
  // Session configuration states
  const [userName, setUserName] = useState("");
  const [userEmail, setUserEmail] = useState("");
  const [quizCode, setQuizCode] = useState("");

  // Dashboard & Proctoring states
  const [sessionActive, setSessionActive] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  // Session list & remote monitoring states

  const [sidebarSessions, setSidebarSessions] = useState([]);
  const [sidebarLoadedPage, setSidebarLoadedPage] = useState(1);
  const [sidebarTotalPages, setSidebarTotalPages] = useState(1);
  const [sidebarLoadingMore, setSidebarLoadingMore] = useState(false);
  const sidebarLoadingMoreRef = useRef(false);
  const sidebarLoadedPageRef = useRef(1);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [sessionEndAt, setSessionEndAt] = useState(null);

  const [remoteScreenshot, setRemoteScreenshot] = useState(null);
  const analysisIntervalRef = useRef(null);
  const pollingIntervalRef = useRef(null);
  /* filter dropdown removed */

  // Dynamic metrics from API/local state
  const [trustScore, setTrustScore] = useState(100);
  const [riskBand, setRiskBand] = useState("LOW");
  const [counters, setCounters] = useState({
    tabSwitched: 0,
    splitScreen: 0,
    noFace: 0,
    multipleFaces: 0,
    noise: 0,
    multipleMonitors: 0
  });
  const [startedAt, setStartedAt] = useState("--:--");
  const [submittedAt, setSubmittedAt] = useState(null);
  const [events, setEvents] = useState([]);

  const sessionIdRef = useRef(null);
  const sessionActiveRef = useRef(false);
  const monitoringEnabledRef = useRef(false);

  const SIDEBAR_PAGE_LIMIT = 25;

  const sortSessionsByCreation = useCallback((sessions) => {
    return [...sessions].sort(
      (a, b) => new Date(b.creation || 0) - new Date(a.creation || 0)
    );
  }, []);

  const mergeSidebarWithFirstPage = useCallback((prev, pageOneSessions) => {
    const byName = new Map(prev.map((s) => [s.name, s]));
    pageOneSessions.forEach((s) => byName.set(s.name, s));
    return sortSessionsByCreation([...byName.values()]);
  }, [sortSessionsByCreation]);

  const fetchSidebarSessions = useCallback(async () => {
    try {
      const first = await listSessions({}, 1, SIDEBAR_PAGE_LIMIT);
      if (!first?.sessions) return;

      setSidebarTotalPages(first.total_pages || 1);
      let shouldResetLoadedPage = false;
      setSidebarSessions((prev) => {
        shouldResetLoadedPage = prev.length === 0;
        if (shouldResetLoadedPage) {
          return sortSessionsByCreation(first.sessions);
        }
        return mergeSidebarWithFirstPage(prev, first.sessions);
      });
      if (shouldResetLoadedPage) {
        sidebarLoadedPageRef.current = 1;
        setSidebarLoadedPage(1);
      }
    } catch (err) {
      console.error("Failed to load sessions:", err);
    }
  }, [mergeSidebarWithFirstPage, sortSessionsByCreation]);

  const loadMoreSidebarSessions = useCallback(async () => {
    if (sidebarLoadingMoreRef.current || sidebarLoadedPageRef.current >= sidebarTotalPages) return;

    sidebarLoadingMoreRef.current = true;
    setSidebarLoadingMore(true);
    try {
      const nextPage = sidebarLoadedPageRef.current + 1;
      const page = await listSessions({}, nextPage, SIDEBAR_PAGE_LIMIT);
      if (page?.sessions?.length) {
        setSidebarSessions((prev) => {
          const ids = new Set(prev.map((s) => s.name));
          const appended = page.sessions.filter((s) => !ids.has(s.name));
          if (!appended.length) return prev;
          return sortSessionsByCreation([...prev, ...appended]);
        });
        sidebarLoadedPageRef.current = nextPage;
        setSidebarLoadedPage(nextPage);
      }
    } catch (err) {
      console.error("Failed to load more sessions:", err);
    } finally {
      sidebarLoadingMoreRef.current = false;
      setSidebarLoadingMore(false);
    }
  }, [sidebarTotalPages, sortSessionsByCreation]);

  useEffect(() => {
    fetchSidebarSessions();
    const interval = setInterval(fetchSidebarSessions, 5000);
    return () => clearInterval(interval);
  }, [fetchSidebarSessions]);

  // Auto-select the latest session when none is selected or the current one disappears
  useEffect(() => {
    if (sidebarSessions.length === 0) return;

    setSelectedSessionId((current) => {
      if (current && sidebarSessions.some((s) => s.name === current)) {
        return current;
      }
      return sidebarSessions[0].name;
    });
  }, [sidebarSessions]);




  // NOTE: Trust score is read from the session document inside pollSessionDetails.
  // A separate poller was removed because it was reading from Redis (with a recovery bonus)
  // while pollSessionDetails reads the DB-saved score, causing the number to flicker
  // between two different values every few seconds.




  const stopMonitoring = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    setSessionActive(false);
    sessionActiveRef.current = false;
    monitoringEnabledRef.current = false;
    setSessionId(null);
    sessionIdRef.current = null;
    setRemoteScreenshot(null);
    setUserName("");
    setUserEmail("");
    setQuizCode("");
    setTrustScore(100);
    setRiskBand("LOW");
    setCounters({
      tabSwitched: 0,
      splitScreen: 0,
      noFace: 0,
      multipleFaces: 0,
      noise: 0,
      multipleMonitors: 0
    });
    setEvents([]);
    setSessionEndAt(null);
  }, []);

  const pollSessionDetails = useCallback(async (sId) => {
    try {
      const data = await getSessionDetails(sId);
      if (!data || data.error || !data.session) {
        if (data?.error?.includes("not found")) stopMonitoring();
        return;
      }

      const detail = data.message || data;
      const s = detail.session;
      const live = isLiveSessionStatus(s.status);
      monitoringEnabledRef.current = live;
      sessionActiveRef.current = live;
      setSessionActive(live);

      setUserName(s.user_name || s.user_id || "Candidate");
      setUserEmail(s.user_email || "No email");
      setQuizCode(s.entity_id || "Quiz");
      setTrustScore(s.trust_score ?? 100);
      setRiskBand(s.risk_level || "LOW");

      if (s.creation) {
        setStartedAt(new Date(s.creation).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
      }
      const endSource = s.modified || s.end_time || s.submitted_at;
      if (s.status === 'ENDED' || s.status === 'FAILED') {
        const endFormatted = endSource
          ? new Date(endSource).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        setSubmittedAt(endFormatted);
        setSessionEndAt(endFormatted);
      } else {
        setSessionEndAt(null);
        setSubmittedAt(null);
      }

      const rawEvents = detail.events || [];
      const evidenceList = detail.evidence || [];
      const evidenceByEventId = {};
      const orphanEvidence = [];

      evidenceList.forEach((ev) => {
        const url = getEvidenceProxyUrl(ev.name) || resolveEvidenceUrl(ev.thumbnail_url || ev.sharepoint_url);
        const originalUrl = ev.original_sharepoint_url || ev.sharepoint_url;
        const entry = {
          url,
          originalUrl,
          evidenceId: ev.name,
          evidenceType: ev.evidence_type,
          capturedAt: ev.captured_at || ev.creation,
        };
        if (ev.event) {
          evidenceByEventId[ev.event] = entry;
        } else {
          orphanEvidence.push(entry);
        }
      });

      const formattedEvents = rawEvents
        .filter((e) => !['SESSION_START', 'SESSION_END'].includes(e.event_type))
        .map((e) => {
          let msg = e.event_type;
          let evidenceUrl = null;
          let evidenceType = null;
          let metaLabel = null;
          if (e.metadata) {
            try {
              const meta = JSON.parse(e.metadata);
              msg = meta.message || e.event_type;
              metaLabel = meta.label || null;
              if (meta.evidence && !isSharePointUrl(meta.evidence)) {
                const metaUrl = resolveEvidenceUrl(meta.evidence);
                if (metaUrl) {
                  evidenceUrl = metaUrl;
                  if (meta.mime_type?.includes('audio') || String(meta.evidence).startsWith('data:audio')) {
                    evidenceType = 'audio';
                  } else if (meta.mime_type?.includes('image') || String(meta.evidence).startsWith('data:image')) {
                    evidenceType = 'screenshot';
                  }
                }
              }
            } catch (_) { /* ignore */ }
          }

          let originalEvidenceUrl = null;
          const linked = evidenceByEventId[e.name];
          if (linked?.url) {
            evidenceUrl = linked.url;
            originalEvidenceUrl = linked.originalUrl;
            evidenceType = linked.evidenceType || evidenceType;
          } else if (!evidenceUrl && orphanEvidence.length > 0) {
            const vt = (e.event_type || '').toUpperCase();
            // Browser-only events (tab switch, split screen) never trigger the camera,
            // so they must never receive a screenshot from the orphan pool.
            const BROWSER_ONLY_EVENTS = new Set(['TAB_SWITCHED', 'SPLIT_SCREEN']);
            if (!BROWSER_ONLY_EVENTS.has(vt)) {
              const eventTime = new Date(e.occurred_at || e.creation).getTime();
              let bestIdx = -1;
              let bestDiff = Infinity;
              orphanEvidence.forEach((o, idx) => {
                // Filter by evidence type compatibility
                if (vt === 'AUDIO_VAD' || vt === 'NOISE') {
                  if (o.evidenceType !== 'audio') return;
                } else {
                  if (!(o.evidenceType === 'screenshot' || o.evidenceType === 'image')) return;
                }
                const oTime = new Date(o.capturedAt || o.creation).getTime();
                const diff = Math.abs(eventTime - oTime);
                if (diff < bestDiff) {
                  bestDiff = diff;
                  bestIdx = idx;
                }
              });
              if (bestIdx >= 0) {
                const pick = orphanEvidence.splice(bestIdx, 1)[0];
                evidenceUrl = pick.url;
                originalEvidenceUrl = pick.originalUrl;
                evidenceType = pick.evidenceType;
              }
            }
          }

          return {
            eventId: e.name,
            violationType: e.event_type,
            type: e.event_type,
            // Label: prefer stored metadata label, then known map, then null (SessionTimeline will title-case)
            label: metaLabel || VIOLATION_LABELS[e.event_type] || null,
            message: msg,
            occurredAt: e.occurred_at
              ? new Date(e.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
              : new Date(e.creation).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            timestamp: e.occurred_at || e.creation,
            evidence: evidenceUrl,
            report_evidence: originalEvidenceUrl || evidenceUrl,
            evidenceType,
          };
        });
      setEvents(formattedEvents);

      const newCounters = {
        tabSwitched: 0,
        splitScreen: 0,
        noFace: 0,
        multipleFaces: 0,
        noise: 0,
        multipleMonitors: 0
      };
      rawEvents.forEach(e => {
        const type = e.event_type;
        if (type === 'TAB_SWITCHED') newCounters.tabSwitched++;
        else if (type === 'SPLIT_SCREEN') newCounters.splitScreen++;
        else if (type === 'NO_FACE') newCounters.noFace++;
        else if (type === 'MULTIPLE_PEOPLE') newCounters.multipleFaces++;
        else if (type === 'AUDIO_VAD' || type === 'NOISE') newCounters.noise++;
        else if (type === 'MULTIPLE_MONITORS') newCounters.multipleMonitors++;
      });
      setCounters(newCounters);

      // Profile photo: only use the face-capture from the SESSION_START event.
      setRemoteScreenshot(resolveProfilePhotoUrl(rawEvents, evidenceByEventId, evidenceList));
    } catch (err) {
      console.error("Error polling session details:", err);
      stopMonitoring();
    }
  }, [stopMonitoring]);

  useEffect(() => {
    if (!selectedSessionId) {
      monitoringEnabledRef.current = false;
      sessionActiveRef.current = false;
      setSessionActive(false);
      return undefined;
    }

    setSessionId(selectedSessionId);
    sessionIdRef.current = selectedSessionId;

    const row = sidebarSessions.find((s) => s.name === selectedSessionId);
    const live = row ? isLiveSessionStatus(row.status) : false;
    monitoringEnabledRef.current = live;
    sessionActiveRef.current = live;
    setSessionActive(live);

    pollSessionDetails(selectedSessionId);
    const pollMs = live ? 3000 : 30000;
    const interval = setInterval(() => pollSessionDetails(selectedSessionId), pollMs);
    return () => clearInterval(interval);
  }, [selectedSessionId, pollSessionDetails, sidebarSessions]);

  const startMonitoring = () => {
    if (!selectedSessionId) {
      alert("Please select an active session to monitor.");
      return;
    }
    if (sessionActive) return;
    if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current);

    setSessionId(selectedSessionId);
    sessionIdRef.current = selectedSessionId;
    setSessionActive(true);
    sessionActiveRef.current = true;

    pollSessionDetails(selectedSessionId);
    pollingIntervalRef.current = setInterval(() => {
      pollSessionDetails(selectedSessionId);
    }, 3000);
  };

  const severityCounts = useMemo(() => countEventsBySeverity(events), [events]);

  const sessionWindow = useMemo(() => {
    if (!selectedSessionId || !startedAt || startedAt === '--:--') return null;
    const end = sessionEndAt || submittedAt;
    return end ? `${startedAt} – ${end}` : `${startedAt} – Present`;
  }, [selectedSessionId, startedAt, sessionEndAt, submittedAt]);

  const getReportPayload = useCallback(() => {
    const row = sidebarSessions.find((s) => s.name === selectedSessionId);
    return buildReportPayload({
      sessionId: selectedSessionId || sessionId,
      userName,
      userEmail,
      quizCode,
      sessionWindow,
      sessionStatus: row?.status || '',
      trustScore,
      riskBand,
      severityCounts,
      counters,
      events,
    });
  }, [
    sidebarSessions,
    selectedSessionId,
    sessionId,
    userName,
    userEmail,
    quizCode,
    sessionWindow,
    trustScore,
    riskBand,
    severityCounts,
    counters,
    events,
  ]);

  const downloadReportCSV = () => {
    if (!selectedSessionId) {
      alert('Please select a session first.');
      return;
    }
    downloadSessionReportCSV(getReportPayload());
  };

  const downloadReportPDF = () => {
    if (!selectedSessionId) {
      alert('Please select a session first.');
      return;
    }
    try {
      downloadSessionReportPDF(getReportPayload());
    } catch (err) {
      console.error('Failed to generate PDF report:', err);
      alert('Failed to generate report. Please try again.');
    }
  };

  // Determine trust score status color
  const getTrustScoreColor = () => {
    if (trustScore >= 80) return "#10b981"; // Success (Green)
    if (trustScore >= 50) return "#f59e0b"; // Warning (Orange)
    return "#ef4444"; // Danger (Red)
  };

  // Circular Trust Score Stroke calculations
  const radius = 36;
  const strokeCircumference = 2 * Math.PI * radius; // ~226.19
  const strokeOffset = strokeCircumference - (strokeCircumference * trustScore) / 100;

  const handleDeleteCandidate = async () => {
    if (!selectedSessionId) {
      alert("Please select a session to delete.");
      return;
    }
    const confirmDelete = window.confirm("Are you sure you want to delete this candidate's record? This action cannot be undone.");
    if (!confirmDelete) return;

    try {
      await proctorApi.deleteCandidateData(selectedSessionId);
      alert("Candidate record deleted successfully.");
      setSelectedSessionId("");
      fetchSidebarSessions();
    } catch (err) {
      console.error("Failed to delete candidate record:", err);
      alert("Failed to delete candidate record: " + err.message);
    }
  };

  return (
    <div className="dark flex h-screen flex-col overflow-hidden bg-[#0a0a0a] text-foreground">
      <header className="z-10 flex shrink-0 items-center border-b border-white/10 bg-[#111111] px-6 py-3">
        <div className="flex items-center gap-3">
          <Shield className="h-6 w-6 text-blue-400" />
          <h1 className="text-lg font-bold tracking-tight">Proctor</h1>
        </div>
      </header>

      <main className="grid h-[calc(100vh-57px)] flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-[280px_1fr]">
        <aside className="flex h-full min-h-0 flex-col overflow-hidden max-lg:max-h-[min(40vh,20rem)] lg:max-h-full">
          <CandidateList
            sessions={sidebarSessions}
            selectedSessionId={selectedSessionId}
            onSelectSession={setSelectedSessionId}
          />
        </aside>

        <section className="flex min-h-0 flex-col gap-[18px] overflow-y-auto overflow-x-hidden pr-2">
          <CandidateProfileHeader
            onDownloadReport={downloadReportPDF}
            onDeleteCandidate={handleDeleteCandidate}
            userName={userName}
            userEmail={userEmail}
            candidatePhoto={remoteScreenshot}
            sessionWindow={sessionWindow}
            hasSession={!!selectedSessionId}
          />

          <SummaryMetricsRow trustScore={trustScore} severityCounts={severityCounts} />

          <div className="grid min-h-0 flex-1 shrink-0 grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">
            <div className="flex min-h-0 flex-col max-lg:max-h-[min(50vh,26rem)] lg:h-[600px]">
              <SessionTimeline events={events} sessionKey={selectedSessionId} />
            </div>
            <div className="min-h-0 overflow-hidden lg:h-[600px]">
              <SystemAnalysisOverview counters={counters} sessionKey={selectedSessionId} />
            </div>
          </div>
        </section>
      </main>

      
    </div>
  );
}
