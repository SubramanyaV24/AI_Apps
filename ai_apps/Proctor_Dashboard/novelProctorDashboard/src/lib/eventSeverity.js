const HIGH_TYPES = new Set([
  'NO_FACE',
  'MULTIPLE_PEOPLE',
  'MOBILE_PHONE',
  'FACE_COVERED',
  'MULTIPLE_MONITORS',
]);

const MODERATE_TYPES = new Set([
  'TAB_SWITCHED',
  'GAZE_AWAY',
  'AUDIO_VAD',
  'NOISE',
]);

export function getEventSeverity(type) {
  const t = (type || '').toUpperCase();
  if (HIGH_TYPES.has(t)) return 'high';
  if (MODERATE_TYPES.has(t)) return 'moderate';
  return 'low';
}

export function countEventsBySeverity(events = []) {
  const counts = { high: 0, moderate: 0, low: 0 };
  events.forEach((e) => {
    const key = getEventSeverity(e.violationType || e.type);
    counts[key] += 1;
  });
  return counts;
}

export function getTrustLabel(score) {
  if (score >= 80) return { text: 'Trusted', color: '#4ade80' };
  if (score >= 50) return { text: 'Moderate', color: '#fb923c' };
  return { text: 'At Risk', color: '#f87171' };
}

export function getTrustBadgeClass(score) {
  if (score >= 80) return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25';
  if (score >= 50) return 'bg-orange-500/15 text-orange-400 border-orange-500/25';
  return 'bg-red-500/15 text-red-400 border-red-500/25';
}
