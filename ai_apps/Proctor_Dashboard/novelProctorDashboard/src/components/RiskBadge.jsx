import React from 'react';
import PropTypes from 'prop-types';
import './RiskBadge.css';

/**
 * RiskBadge component displays risk level with color‑coded badge.
 * Expected risk levels: 'low', 'medium', 'high', 'critical'.
 */
const RiskBadge = ({ risk }) => {
  const level = risk?.toLowerCase() || 'low';
  const className = `risk-badge risk-${level}`;
  // Ensure the displayed text is escaped by React automatically.
  return <span className={className}>{level.charAt(0).toUpperCase() + level.slice(1)}</span>;
};

RiskBadge.propTypes = {
  risk: PropTypes.string.isRequired,
};

export default RiskBadge;
