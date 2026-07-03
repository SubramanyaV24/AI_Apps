import proctorApi from '../api/Proctor_Dashboard_Api'

export function pcmToWavDataUri(pcmBase64) {
  try {
    const binaryString = atob(pcmBase64)
    const len = binaryString.length
    const bytes = new Uint8Array(len)
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i)
    }
    const buffer = new ArrayBuffer(44 + len)
    const view = new DataView(buffer)

    const writeString = (offset, string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i))
      }
    }

    writeString(0, 'RIFF')
    view.setUint32(4, 36 + len, true)
    writeString(8, 'WAVE')
    writeString(12, 'fmt ')
    view.setUint32(16, 16, true)
    view.setUint16(20, 1, true)
    view.setUint16(22, 1, true)
    view.setUint32(24, 16000, true)
    view.setUint32(28, 32000, true)
    view.setUint16(32, 2, true)
    view.setUint16(34, 16, true)
    writeString(36, 'data')
    view.setUint32(40, len, true)

    const u8Buffer = new Uint8Array(buffer)
    u8Buffer.set(bytes, 44)

    let binary = ''
    for (let i = 0; i < u8Buffer.byteLength; i++) {
      binary += String.fromCharCode(u8Buffer[i])
    }
    return `data:audio/wav;base64,${btoa(binary)}`
  } catch (err) {
    console.error('Failed to convert PCM to WAV:', err)
    return null
  }
}

const EVIDENCE_FILE_METHOD =
  '/api/method/ai_apps.api.proctor_api.proctor_session.get_evidence_file'

export function isSharePointUrl(url) {
  if (!url || typeof url !== 'string') return false
  return /sharepoint\.com/i.test(url)
}

/** Same-origin Frappe proxy URL used for profile photo and timeline previews. */
export function getEvidenceProxyUrl(evidenceId) {
  if (!evidenceId) return null
  return `${proctorApi.frappeBaseUrl}${EVIDENCE_FILE_METHOD}?evidence_id=${encodeURIComponent(evidenceId)}`
}

export function resolveEvidenceUrl(url) {
  if (!url || typeof url !== 'string') return null
  const trimmed = url.trim()
  if (!trimmed) return null

  if (isSharePointUrl(trimmed)) {
    return null
  }

  if (trimmed.startsWith('data:')) {
    return trimmed
  }

  if (trimmed.startsWith('/')) {
    return `${proctorApi.frappeBaseUrl}${trimmed}`
  }

  if (trimmed.includes('get_evidence_file')) {
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      return trimmed
    }
    try {
      const parsed = new URL(trimmed, proctorApi.frappeBaseUrl)
      return parsed.href
    } catch {
      return `${proctorApi.frappeBaseUrl}${trimmed.startsWith('/') ? '' : '/'}${trimmed}`
    }
  }

  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return trimmed
  }

  if (/^[A-Za-z0-9+/=]+$/.test(trimmed) && trimmed.length > 200) {
    return pcmToWavDataUri(trimmed) || `data:application/octet-stream;base64,${trimmed}`
  }

  return trimmed
}

/** Normalize embedded PCM / octet-stream data URIs to browser-playable WAV. */
export function normalizeAudioDataUri(evidence) {
  const resolved = resolveEvidenceUrl(evidence)
  if (!resolved) return null

  if (resolved.startsWith('data:audio/')) return resolved

  if (resolved.startsWith('data:application/octet-stream')) {
    const b64 = resolved.split(',')[1]
    return pcmToWavDataUri(b64) || resolved
  }

  if (resolved.startsWith('data:')) {
    const b64 = resolved.split(',')[1]
    if (b64) {
      const wav = pcmToWavDataUri(b64)
      if (wav) return wav
    }
  }

  return resolved
}

/**
 * Resolve a URL the browser <audio> element can play (data URI or blob URL).
 * Caller must revoke blob URLs when done.
 */
export async function resolvePlayableAudioSrc(evidence) {
  const normalized = normalizeAudioDataUri(evidence)
  if (!normalized) return { src: null, error: 'No audio source' }

  if (normalized.startsWith('data:audio/')) {
    return { src: normalized, error: null }
  }

  if (isSharePointUrl(normalized)) {
    return { src: null, error: 'Use Frappe evidence proxy URL for audio' }
  }

  return { src: normalized, error: null }
}

/** @returns {'image'|'audio'|'video'|'unknown'} */
export function getEvidenceMediaType(evidence, evidenceType, eventType) {
  const e = (evidence || '').toLowerCase()
  const et = (evidenceType || '').toLowerCase()
  const vt = (eventType || '').toUpperCase()

  if (e.startsWith('data:image')) return 'image'
  if (e.startsWith('data:audio') || e.startsWith('data:audio/')) return 'audio'
  if (e.startsWith('data:application/octet-stream')) return 'audio'
  if (e.startsWith('data:video')) return 'video'
  if (/\.(jpg|jpeg|png|gif|webp|bmp)(\?|$)/i.test(e)) return 'image'
  if (/\.(wav|mp3|ogg|m4a|aac)(\?|$)/i.test(e)) return 'audio'
  if (/\.(mp4|webm|mov)(\?|$)/i.test(e)) return 'video'

  if (et === 'audio') return 'audio'
  if (et === 'screenshot' || et === 'image') return 'image'
  if (et === 'video') return 'video'

  if (e.includes('/get_evidence_file') || e.includes('/files/') || e.includes('sharepoint')) {
    if (et === 'audio') return 'audio'
    if (et === 'screenshot' || et === 'image') return 'image'
    if (vt === 'AUDIO_VAD' || vt === 'NOISE') return 'audio'
    return 'image'
  }

  if (vt === 'AUDIO_VAD' || vt === 'NOISE') return 'audio'
  return 'unknown'
}

export function isPreviewableEvidence(evidence, evidenceType, eventType) {
  if (!evidence) return false
  const media = getEvidenceMediaType(evidence, evidenceType, eventType)
  return media === 'image' || media === 'audio' || media === 'video'
}
