import React from 'react';
import PropTypes from 'prop-types';
import './TrustScoreCircle.css';

/**
 * TrustScoreCircle displays a circular progress indicator for trust score.
 * The score is a number between 0 and 100.
 */
const TrustScoreCircle = ({ score }) => {
  const radius = 36;
  const stroke = 4;
  const normalizedScore = Math.min(Math.max(score, 0), 100);
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (circumference * normalizedScore) / 100;
  const getColor = () => {
    if (normalizedScore >= 80) return '#10b981'; // green
    if (normalizedScore >= 50) return '#f59e0b'; // orange
    return '#ef4444'; // red
  };

  return (
    <svg width="84" height="84" style={{ display: 'block' }}>
      <g transform="rotate(-90 42 42)">
        <circle
          cx="42"
          cy="42"
          r={radius}
          stroke="#1e293b"
          strokeWidth={stroke}
          fill="none"
          className="trust-score-bg"
        />
        <circle
          cx="42"
          cy="42"
          r={radius}
          stroke={getColor()}
          strokeWidth={stroke}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="trust-score-fg"
        />
      </g>
      <text
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        fontSize="16"
        fill={getColor()}
        fontWeight="700"
        dy=".1em"
      >
        {normalizedScore}%
      </text>
    </svg>
  );
};

TrustScoreCircle.propTypes = {
  score: PropTypes.number.isRequired,
};

export default TrustScoreCircle;
