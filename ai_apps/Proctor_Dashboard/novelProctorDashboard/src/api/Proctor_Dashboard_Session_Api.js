// src/api/sessionApi.js
// Frontend API wrapper for Proctor session list/details endpoints

import proctorApi from './Proctor_Dashboard_Api';

/**
 * Fetch a paginated list of past sessions.
 * @param {Object} filters - Optional filter dict (e.g., { status: 'ENDED' })
 * @param {number} page - 1-based page number
 * @param {number} limit - Items per page
 * @returns {Promise<Object>} { sessions, page, limit, total, total_pages }
 */
export async function listSessions(filters = {}, page = 1, limit = 20) {
  const filterStr = JSON.stringify(filters);
  return proctorApi._frappePost(
    '/api/method/ai_apps.api.proctor_api.proctor_session.list_sessions',
    { filters: filterStr, page, limit }
  );
}

/**
 * Retrieve detailed analytics for a single session.
 * @param {string} sessionId - Proctor Session name/id
 * @returns {Promise<Object>} session detail with events and evidence
 */
export async function getSessionDetails(sessionId) {
  return proctorApi._frappePost(
    '/api/method/ai_apps.api.proctor_api.proctor_session.get_session_details',
    { session_id: sessionId }
  );
}

/**
 * Mark a session as reviewed by a human reviewer.
 * @param {string} sessionId
 * @returns {Promise<Object>} success flag
 */
export async function markSessionReviewed(sessionId) {
  return proctorApi._frappePost(
    '/api/method/ai_apps.api.proctor_api.session_analytics.mark_reviewed',
    { session_id: sessionId }
  );
}

/**
 * Fetch the total number of analyzed candidates (all Proctor Sessions).
 * @returns {Promise<Object>} { success, total_candidates }
 */
export async function getTotalCandidates() {
  return proctorApi._frappePost(
    '/api/method/ai_apps.api.proctor_api.services.candidate_filter.get_total_candidates',
    {}
  );
}

/**
 * Filter and paginate Proctor Sessions using the candidate_filter service.
 *
 * @param {Object} opts
 * @param {string}   [opts.query]       - Free-text search (name / email)
 * @param {string[]} [opts.riskLevels]  - e.g. ["HIGH","MEDIUM"]
 * @param {number}   [opts.trustMin]    - Minimum trust score (0-100)
 * @param {number}   [opts.trustMax]    - Maximum trust score (0-100)
 * @param {string[]} [opts.status]      - e.g. ["ENDED"]
 * @param {number}   [opts.page]        - 1-based page number
 * @param {number}   [opts.limit]       - Items per page (max 100)
 * @returns {Promise<Object>} { sessions, page, limit, total, total_pages }
 */
export async function filterSessions({
  query = '',
  riskLevels = [],
  trustMin = 0,
  trustMax = 100,
  status = [],
  page = 1,
  limit = 25,
} = {}) {
  return proctorApi._frappePost(
    '/api/method/ai_apps.api.proctor_api.services.candidate_filter.filter_sessions',
    {
      query,
      risk_levels: JSON.stringify(riskLevels),
      trust_min: trustMin,
      trust_max: trustMax,
      status: JSON.stringify(status),
      page,
      limit,
    }
  );
}
