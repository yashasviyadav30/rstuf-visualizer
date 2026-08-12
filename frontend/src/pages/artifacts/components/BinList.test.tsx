// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { BinSummary } from '../../../api/types';
import { BinList } from './BinList';

const bin = (over: Partial<BinSummary>): BinSummary => ({
  name: 'bins-0',
  count: 32,
  available: true,
  ...over,
});

function show(bins: BinSummary[]) {
  render(
    <BinList
      bins={bins}
      total={bins.reduce((sum, one) => sum + one.count, 0)}
      loading={false}
      selected={null}
      onSelect={vi.fn()}
    />,
  );
}

describe('the bin list', () => {
  it('keeps a bin that holds nothing, showing zero', () => {
    // Its absence would say the bin does not exist, which is a different
    // fact and one nobody checked.
    show([bin({ name: 'bins-0', count: 0 })]);

    expect(screen.getByText('bins-0')).toBeTruthy();
    expect(screen.getByText('0')).toBeTruthy();
  });

  it('says a bin could not be read instead of showing zero', () => {
    // Zero would be a claim about its contents. Nothing was read, so
    // nothing about its contents is known.
    show([bin({ name: 'bins-9', count: 0, available: false })]);

    expect(screen.getByText('unreadable')).toBeTruthy();
    expect(screen.queryByText('0')).toBeNull();
  });

  it('will not open a bin it could not read', () => {
    show([bin({ available: false })]);

    const button = screen.getByRole('button', { name: /bins-0/ });
    expect(button.hasAttribute('disabled')).toBe(true);
  });

  it('counts the artifacts and the roles holding them', () => {
    show([bin({ name: 'bins-0' }), bin({ name: 'bins-1' })]);

    expect(screen.getByText('64 artifacts across 2 roles')).toBeTruthy();
  });

  it('says so when a repository delegates to nothing', () => {
    show([]);

    expect(
      screen.getByText('This repository delegates to no roles.'),
    ).toBeTruthy();
  });
});
