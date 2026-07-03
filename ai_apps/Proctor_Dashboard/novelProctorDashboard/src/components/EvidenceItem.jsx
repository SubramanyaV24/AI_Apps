import PropTypes from 'prop-types';
import proctorApi from '../api/Proctor_Dashboard_Api';
import './EvidenceItem.css';

/**
 * EvidenceItem – renders a single evidence entry.
 * Supports screenshots (image thumbnails) and audio recordings.
 * Props:
 *   evidence: {
 *     evidence_type: string, // "screenshot", "audio", or others
 *     sharepoint_url: string, // URL to the file
 *     thumbnail_url: string, // For images – already a preview image URL
 *   }
 */
const EvidenceItem = ({ evidence }) => {
  const { evidence_type, sharepoint_url, thumbnail_url } = evidence;
  if (!sharepoint_url) {
    return null;
  }

  // Defensively resolve relative URLs using frappeBaseUrl from proctorApi
  const getAbsoluteUrl = (url) => {
    if (url && url.startsWith('/')) {
      return `${proctorApi.frappeBaseUrl}${url}`;
    }
    return url;
  };

  const resolvedSharepointUrl = getAbsoluteUrl(sharepoint_url);
  const resolvedThumbnailUrl = getAbsoluteUrl(thumbnail_url);

  if (evidence_type === 'screenshot' && resolvedThumbnailUrl) {
    return (
      <img src={resolvedThumbnailUrl} alt="Screenshot" className="evidence-thumbnail" />
    );
  }
  if (evidence_type === 'audio') {
    return (
      <audio controls src={resolvedSharepointUrl} className="evidence-audio">
        Your browser does not support the audio element.
      </audio>
    );
  }
  // Fallback: generic link
  return (
    <a href={resolvedSharepointUrl} target="_blank" rel="noopener noreferrer" className="evidence-link">
      View {evidence_type || 'evidence'}
    </a>
  );
};

EvidenceItem.propTypes = {
  evidence: PropTypes.shape({
    evidence_type: PropTypes.string,
    sharepoint_url: PropTypes.string.isRequired,
    thumbnail_url: PropTypes.string,
  }).isRequired,
};

export default EvidenceItem;
