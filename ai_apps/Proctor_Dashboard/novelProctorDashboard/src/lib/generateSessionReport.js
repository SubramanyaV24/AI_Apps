import { jsPDF } from 'jspdf'
import { getEventSeverity, getTrustLabel } from './eventSeverity'
import { resolveEvidenceUrl } from './evidenceUtils'

function formatViolationType(type) {
  if (!type) return 'Event'
  return type
    .split('_')
    .map((w) => w.charAt(0) + w.slice(1).toLowerCase())
    .join(' ')
}

function sortEventsChronologically(events = []) {
  return [...events].sort((a, b) => {
    const ta = new Date(a.timestamp || a.occurredAt || 0).getTime()
    const tb = new Date(b.timestamp || b.occurredAt || 0).getTime()
    return tb - ta
  })
}

function escapeCsvCell(value) {
  const s = String(value ?? '')
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

function wrapText(pdf, text, maxWidth) {
  return pdf.splitTextToSize(String(text ?? ''), maxWidth)
}

function addFooter(pdf, pageNum, totalPages) {
  const w = pdf.internal.pageSize.getWidth()
  const h = pdf.internal.pageSize.getHeight()
  pdf.setFontSize(8)
  pdf.setTextColor(120, 120, 120)
  pdf.text(
    `Proctor Report — Page ${pageNum} of ${totalPages}`,
    w / 2,
    h - 8,
    { align: 'center' }
  )
  pdf.setTextColor(0, 0, 0)
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
    ['Tab Switches', report.counters?.tabSwitched ?? 0],
    ['Face Missing', report.counters?.noFace ?? 0],
    ['Multiple Faces', report.counters?.multipleFaces ?? 0],
    ['Noise Events', report.counters?.noise ?? 0],
    ['External Monitor', report.counters?.multipleMonitors ?? 0],
    [],
    ['Session Activity Timeline (all events)'],
    ['#', 'Violation Type', 'Severity', 'Occurred At', 'Message', 'Evidence URL'],
  ]

  meta.forEach((row) => rows.push(row.map(escapeCsvCell).join(',')))

  events.forEach((evt, idx) => {
    const evidence = evt.evidence ? resolveEvidenceUrl(evt.evidence) : ''
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

/**
 * Structured multi-page PDF with full timeline (not UI screenshot).
 * @param {object} report
 */
export function downloadSessionReportPDF(report) {
  const pdf = new jsPDF({ orientation: 'p', unit: 'mm', format: 'a4' })
  const pageW = pdf.internal.pageSize.getWidth()
  const pageH = pdf.internal.pageSize.getHeight()
  const margin = 14
  const contentW = pageW - margin * 2
  const lineH = 5.5
  let y = margin

  const ensureSpace = (height) => {
    if (y + height > pageH - 18) {
      pdf.addPage()
      y = margin
    }
  }

  const sectionTitle = (title) => {
    ensureSpace(12)
    pdf.setFont('helvetica', 'bold')
    pdf.setFontSize(11)
    pdf.setTextColor(30, 64, 175)
    pdf.text(title, margin, y)
    y += 7
    pdf.setDrawColor(200, 200, 200)
    pdf.line(margin, y, pageW - margin, y)
    y += 5
    pdf.setTextColor(0, 0, 0)
    pdf.setFont('helvetica', 'normal')
    pdf.setFontSize(10)
  }

  const labelValue = (label, value) => {
    ensureSpace(lineH + 1)
    pdf.setFont('helvetica', 'bold')
    pdf.text(`${label}:`, margin, y)
    pdf.setFont('helvetica', 'normal')
    const lines = wrapText(pdf, value || '—', contentW - 42)
    pdf.text(lines, margin + 40, y)
    y += Math.max(lineH, lines.length * lineH)
  }

  const events = sortEventsChronologically(report.events)
  const trustLabel = getTrustLabel(report.trustScore ?? 0)

  // —— Cover / summary ——
  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(18)
  pdf.text('Proctor Session Report', margin, y)
  y += 10

  pdf.setFont('helvetica', 'normal')
  pdf.setFontSize(9)
  pdf.setTextColor(100, 100, 100)
  pdf.text(`Generated ${new Date().toLocaleString()}`, margin, y)
  y += 10
  pdf.setTextColor(0, 0, 0)
  pdf.setFontSize(10)

  sectionTitle('Candidate & Session')
  labelValue('Candidate', report.userName)
  labelValue('Email', report.userEmail)
  labelValue('Session ID', report.sessionId)
  labelValue('Quiz / Entity', report.quizCode)
  labelValue('Session Window', report.sessionWindow)
  labelValue('Status', report.sessionStatus)

  sectionTitle('Trust & Risk Summary')
  labelValue('Trust Score', `${report.trustScore ?? 0}% (${trustLabel.text})`)
  labelValue('Risk Level', report.riskBand)
  labelValue('High Risk Violations', String(report.severityCounts?.high ?? 0))
  labelValue('Moderate Risk Violations', String(report.severityCounts?.moderate ?? 0))
  labelValue('Low Risk Violations', String(report.severityCounts?.low ?? 0))
  labelValue('Total Events', String(events.length))

  sectionTitle('System Analysis Overview')
  labelValue('Tab Switches', String(report.counters?.tabSwitched ?? 0))
  labelValue('Face Missing', String(report.counters?.noFace ?? 0))
  labelValue('Multiple Faces', String(report.counters?.multipleFaces ?? 0))
  labelValue('Noise Events', String(report.counters?.noise ?? 0))
  labelValue('External Monitor', String(report.counters?.multipleMonitors ?? 0))

  // —— Full activity timeline (all pages, not UI pagination) ——
  pdf.addPage()
  y = margin
  sectionTitle(`Session Activity Timeline (${events.length} events)`)

  if (events.length === 0) {
    ensureSpace(lineH)
    pdf.text('No events recorded in this session.', margin, y)
    y += lineH
  } else {
    events.forEach((evt, idx) => {
      const title = `${idx + 1}. ${formatViolationType(evt.violationType || evt.type)}`
      const severity = getEventSeverity(evt.violationType || evt.type).toUpperCase()
      const time = evt.occurredAt || '—'
      const msgLines = wrapText(pdf, evt.message || '—', contentW)
      const evidence = evt.evidence ? resolveEvidenceUrl(evt.evidence) : null
      const evidenceLines = evidence ? wrapText(pdf, evidence, contentW - 8) : []

      const blockH = 8 + msgLines.length * lineH + (evidence ? 5 + evidenceLines.length * lineH : 0)
      ensureSpace(blockH)

      pdf.setFont('helvetica', 'bold')
      pdf.setFontSize(10)
      pdf.text(title, margin, y)
      pdf.setFont('helvetica', 'normal')
      pdf.setFontSize(9)
      pdf.setTextColor(80, 80, 80)
      pdf.text(`${time}  ·  ${severity} risk`, margin, y + 5)
      y += 10
      pdf.setTextColor(0, 0, 0)
      pdf.setFontSize(10)

      msgLines.forEach((line) => {
        pdf.text(line, margin, y)
        y += lineH
      })

      if (evidence) {
        pdf.setFontSize(8)
        pdf.setTextColor(30, 64, 175)
        pdf.text('Evidence:', margin, y)
        y += 4
        evidenceLines.forEach((line) => {
          pdf.text(line, margin + 4, y)
          y += 4
        })
        pdf.setTextColor(0, 0, 0)
        pdf.setFontSize(10)
      }

      y += 4
      pdf.setDrawColor(230, 230, 230)
      pdf.line(margin, y, pageW - margin, y)
      y += 6
    })
  }

  const totalPages = pdf.getNumberOfPages()
  for (let p = 1; p <= totalPages; p++) {
    pdf.setPage(p)
    addFooter(pdf, p, totalPages)
  }

  pdf.save(`proctor_report_${report.sessionId || 'session'}.pdf`)
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
