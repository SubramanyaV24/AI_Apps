const CRITICAL_TYPES = new Set([
  'MULTIPLE_MONITORS',
  'NO_VIDEO',
  'MIC_DISABLED',
  'CAMERA_DISABLED',
]);

const HIGH_TYPES = new Set([
  'MULTIPLE_PEOPLE',
  'MULTIPLE_FACES',
  'MOBILE_PHONE',
  'TAB_SWITCHED',
  'NO_AUDIO',
]);

const MODERATE_TYPES = new Set([
  'NO_FACE',
  'FULLSCREEN_EXITED',
  'FULLSCREEN_EXIT',
  'AUDIO_VAD',
]);

export function getEventSeverity(type) {
  const t = (type || '').toUpperCase();
  if (CRITICAL_TYPES.has(t)) return 'critical';
  if (HIGH_TYPES.has(t)) return 'high';
  if (MODERATE_TYPES.has(t)) return 'moderate';
  return 'low';
}

export function countEventsBySeverity(events = []) {
  const counts = { critical: 0, high: 0, moderate: 0, low: 0 };
  events.forEach((e) => {
    // Only count events that triggered a violation
    if (e.isViolation === false) return;
    
    let key;
    if (e.severity) {
      key = e.severity.toLowerCase();
    } else {
      key = getEventSeverity(e.violationType || e.type);
    }
    
    // Map backend severity levels to frontend severity counts
    if (key === 'medium') key = 'moderate';
    
    if (counts[key] !== undefined) {
      counts[key] += 1;
    }
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
