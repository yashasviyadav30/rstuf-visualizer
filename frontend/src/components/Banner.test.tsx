// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../api/client';
import { ErrorBanner } from './Banner';

describe('reporting a failure', () => {
  it('separates having nothing to check from failing to read', () => {
    // A repository that cannot be reached is a broken deployment. A service
    // with no trust anchor cannot check anything at all, which is a
    // different problem with a different fix.
    render(
      <ErrorBanner
        error={new ApiError(503, 'No trust anchor is available.')}
      />,
    );

    expect(screen.getByText('Nothing can be checked.')).toBeTruthy();
  });

  it('reports an unreachable repository as unreachable', () => {
    render(
      <ErrorBanner error={new ApiError(502, 'could not fetch timestamp')} />,
    );

    expect(screen.getByText('The repository could not be read.')).toBeTruthy();
  });

  it('keeps the message the backend sent', () => {
    // Every failure from this API carries a sentence written for a person,
    // and it is the only part of the answer worth reading.
    render(<ErrorBanner error={new ApiError(502, 'storage timed out')} />);

    expect(screen.getByText(/storage timed out/)).toBeTruthy();
  });

  it('handles a failure that never reached the API at all', () => {
    render(<ErrorBanner error={new Error('Failed to fetch')} />);

    expect(screen.getByText(/Failed to fetch/)).toBeTruthy();
  });
});
