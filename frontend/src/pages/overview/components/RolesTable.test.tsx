// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { RoleSummary } from '../../../api/types';
import { RolesTable } from './RolesTable';

const role = (over: Partial<RoleSummary>): RoleSummary =>
  ({
    name: 'root',
    version: 3,
    expires: '2027-08-12T00:00:00+00:00',
    expires_in: 'expires 2027-08-12',
    band: 'valid',
    threshold: 2,
    key_count: 2,
    key_names: ['root_key_1', 'root_key_2'],
    status: 'valid',
    ...over,
  }) as RoleSummary;

describe('the roles table', () => {
  it('shows the threshold beside the signers, not on its own', () => {
    // "2" says almost nothing. "2 of 2" says the arrangement: two keys
    // exist and both are required.
    render(
      <RolesTable roles={[role({})]} selected={null} onSelect={vi.fn()} />,
    );

    expect(screen.getByText('(2 of 2)')).toBeTruthy();
    expect(screen.getByText('root_key_1')).toBeTruthy();
  });

  it('says when a threshold or key count is missing', () => {
    // A delegated role reaches this table without root's entry for it, and
    // an empty cell beside a real one reads as zero.
    render(
      <RolesTable
        roles={[role({ threshold: null, key_count: null })]}
        selected={null}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText('(? of ?)')).toBeTruthy();
  });

  it('carries the expiry band into the class, not only the words', () => {
    render(
      <RolesTable
        roles={[role({ band: 'critical', expires_in: 'expires in 20h' })]}
        selected={null}
        onSelect={vi.fn()}
      />,
    );

    const cell = screen.getByText('expires in 20h');
    expect(cell.className).toContain('state--critical');
  });

  it('opens the role that was clicked', async () => {
    const onSelect = vi.fn();
    render(
      <RolesTable
        roles={[role({ name: 'targets' })]}
        selected={null}
        onSelect={onSelect}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'targets' }));

    expect(onSelect).toHaveBeenCalledWith('targets');
  });

  it('says so when nothing verified', () => {
    render(<RolesTable roles={[]} selected={null} onSelect={vi.fn()} />);

    expect(screen.getByText('No roles were verified.')).toBeTruthy();
  });
});
