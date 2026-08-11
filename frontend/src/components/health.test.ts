// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from 'vitest';

import type { OverviewResponse, RoleSummary } from '../api/types';
import { ago, verdictFor } from './health';

function role(over: Partial<RoleSummary>): RoleSummary {
  return {
    name: 'timestamp',
    version: 1,
    expires: '2026-09-01T00:00:00+00:00',
    expires_in: 'expires in 20 hours',
    band: 'critical',
    threshold: 1,
    key_count: 1,
    key_names: ['online_key'],
    status: 'valid',
    ...over,
  } as RoleSummary;
}

function overview(over: Partial<OverviewResponse>): OverviewResponse {
  return {
    state: 'ready',
    status: 'valid',
    checked_at: '2026-08-12T10:00:00+00:00',
    roles: [],
    delegated: [],
    edges: [],
    verification_error: null,
    message: null,
    ...over,
  } as OverviewResponse;
}

describe('the header verdict', () => {
  it('stays green while timestamp is inside a day of expiring', () => {
    // This is the normal state of a working repository. RSTUF renews
    // timestamp daily, so an amber header here would be permanent.
    const verdict = verdictFor(
      overview({ roles: [role({ name: 'timestamp', band: 'critical' })] }),
    );

    expect(verdict.band).toBe('valid');
    expect(verdict.label).toBe('All healthy');
  });

  it('turns red when a role has actually expired', () => {
    const verdict = verdictFor(
      overview({ roles: [role({ name: 'snapshot', band: 'expired' })] }),
    );

    expect(verdict.band).toBe('expired');
  });

  it('turns red when verification failed', () => {
    expect(verdictFor(overview({ status: 'invalid' })).band).toBe('invalid');
  });

  it('warns when root is running down, because no worker renews it', () => {
    const verdict = verdictFor(
      overview({
        roles: [
          role({ name: 'root', band: 'expiring', expires_in: 'in 3 days' }),
          role({ name: 'timestamp', band: 'critical' }),
        ],
      }),
    );

    expect(verdict.band).toBe('critical');
    expect(verdict.label).toContain('Root');
  });
});

describe('the age of the reading', () => {
  const at = (iso: string) => new Date(iso).getTime();

  it('counts seconds without pluralising one', () => {
    expect(ago('2026-08-12T10:00:00Z', at('2026-08-12T10:00:01Z'))).toBe(
      '1 second',
    );
  });

  it('moves to minutes, then to hours', () => {
    expect(ago('2026-08-12T10:00:00Z', at('2026-08-12T10:05:00Z'))).toBe(
      '5 minutes',
    );
    expect(ago('2026-08-12T10:00:00Z', at('2026-08-12T13:00:00Z'))).toBe(
      '3 hours',
    );
  });

  it('never reports a reading from the future as negative', () => {
    expect(ago('2026-08-12T10:00:05Z', at('2026-08-12T10:00:00Z'))).toBe(
      '0 seconds',
    );
  });
});
