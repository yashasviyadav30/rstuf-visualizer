import { useEffect, useState } from 'react';

import type { OverviewResponse } from '../api/types';
import { ago, verdictFor } from './health';

interface Props {
  overview: OverviewResponse | null;
  loading: boolean;
  onRefresh: () => void;
}

export function HealthBadge({ overview, loading, onRefresh }: Props) {
  // The age of the reading is only honest if it keeps counting. Nothing is
  // fetched here; the label is redrawn from the reading already in hand.
  const [, tick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => tick((n) => n + 1), 10_000);
    return () => clearInterval(timer);
  }, []);

  const verdict = overview
    ? verdictFor(overview)
    : { band: 'loading' as const, label: 'Checking…' };

  return (
    <>
      <span className={`badge badge--${verdict.band}`}>
        <span className="badge__dot" />
        <span>{verdict.label}</span>
      </span>
      <div className="topbar__right">
        <span className="checked">
          {overview?.checked_at
            ? `checked ${ago(overview.checked_at)} ago`
            : ''}
        </span>
        <button
          className={`btn${loading ? ' is-busy' : ''}`}
          type="button"
          title="Check the repository now"
          disabled={loading}
          onClick={onRefresh}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
          </svg>
          Refresh
        </button>
      </div>
    </>
  );
}
