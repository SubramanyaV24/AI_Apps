import { getEventSeverity } from './eventSeverity'
import { resolveEvidenceUrl } from './evidenceUtils'

function formatViolationType(type) {
  if (!type) return 'Event'
  return type
    .split('_')
    .map((w) => w.charAt(0) + w.slice(1).toLowerCase())
    .join(' ')
}

function sortEventsChronologically(events = []) {
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
}

function escapeCsvCell(value) {
  const s = String(value ?? '')
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}


/**
 * @param {object} report
 */
export function downloadSessionReportCSV(report) {
  const events = sortEventsChronologically(report.events)
  const rows = []

  const meta = [
    ['Proctor Session Report'],
    ['Generated', new Date().toLocaleString()],
    ['Session ID', report.sessionId || ''],
    ['Candidate', report.userName || ''],
    ['Email', report.userEmail || ''],
    ['Quiz / Entity', report.quizCode || ''],
    ['Session Window', report.sessionWindow || ''],
    ['Status', report.sessionStatus || ''],
    ['Trust Score', `${report.trustScore ?? 0}%`],
    ['Risk Level', report.riskBand || ''],
    [],
    ['Summary — Violations by Severity'],
    ['High Risk', report.severityCounts?.high ?? 0],
    ['Moderate Risk', report.severityCounts?.moderate ?? 0],
    ['Low Risk', report.severityCounts?.low ?? 0],
    [],
    ['System Analysis'],
    ['Mobile Phone', report.counters?.mobilePhone ?? 0],
    ['Tab Switches', report.counters?.tabSwitched ?? 0],
    ['Face Missing', report.counters?.noFace ?? 0],
    ['Multiple Faces', report.counters?.multipleFaces ?? 0],
    ['Face Covered', report.counters?.faceCovered ?? 0],
    ['Looking Away', report.counters?.gazeAway ?? 0],
    ['Noise Events', report.counters?.noise ?? 0],
    ['External Monitor', report.counters?.multipleMonitors ?? 0],
    [],
    ['Session Activity Timeline (all events)'],
    ['#', 'Violation Type', 'Severity', 'Occurred At', 'Message', 'Evidence URL'],
  ]

  meta.forEach((row) => rows.push(row.map(escapeCsvCell).join(',')))

  events.forEach((evt, idx) => {
    const evidenceRaw = evt.report_evidence || evt.evidence
    const evidence = evidenceRaw ? (evidenceRaw.includes('sharepoint.com') ? evidenceRaw : resolveEvidenceUrl(evidenceRaw)) : ''
    rows.push(
      [
        idx + 1,
        formatViolationType(evt.violationType || evt.type),
        getEventSeverity(evt.violationType || evt.type).toUpperCase(),
        evt.occurredAt || '',
        evt.message || '',
        evidence,
      ]
        .map(escapeCsvCell)
        .join(',')
    )
  })

  const blob = new Blob([rows.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `proctor_report_${report.sessionId || 'session'}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

export function downloadSessionReportPDF(report) {
  if (!report.sessionId) return;
  const url = `/api/method/ai_apps.api.proctor_api.export.generate_pdf?session_id=${report.sessionId}`;
  
  const link = document.createElement('a');
  link.href = url;
  link.download = `Session_Report_${report.sessionId}.pdf`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function buildReportPayload({
  sessionId,
  userName,
  userEmail,
  quizCode,
  sessionWindow,
  sessionStatus,
  trustScore,
  riskBand,
  severityCounts,
  counters,
  events,
}) {
  return {
    sessionId,
    userName,
    userEmail,
    quizCode,
    sessionWindow,
    sessionStatus,
    trustScore,
    riskBand,
    severityCounts,
    counters,
    events,
  }
}
