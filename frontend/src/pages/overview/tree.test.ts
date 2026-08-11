// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { describe, expect, it } from 'vitest';

import type { OverviewResponse } from '../../api/types';
import { layout, treeModel } from './tree';
import { GROUP } from './types/tree';

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

const named = (names: string[]) =>
  names.map((name) => ({
    name,
    version: 1,
    expires: '2026-09-01T00:00:00+00:00',
    expires_in: 'in 20 days',
    band: 'valid' as const,
    threshold: 1,
    key_count: 1,
    key_names: [],
    status: 'valid' as const,
  }));

describe('the delegation tree', () => {
  it('takes its shape from the edges, naming no role itself', () => {
    const model = treeModel(
      overview({
        roles: named(['root', 'timestamp', 'snapshot', 'targets']),
        edges: [
          { parent: 'root', child: 'timestamp' },
          { parent: 'root', child: 'snapshot' },
          { parent: 'root', child: 'targets' },
        ],
      }),
    );

    expect(model.tops).toEqual(['root']);
    expect(model.children.get('root')).toEqual([
      'timestamp',
      'snapshot',
      'targets',
    ]);
  });

  it('stands every delegated role behind one node', () => {
    // A repository may hold two hundred and fifty-six bins. Drawing each as
    // its own branch would hide the structure it is meant to show.
    const model = treeModel(
      overview({
        roles: named(['root', 'targets']),
        delegated: Array.from({ length: 256 }, (_, i) => ({
          name: `bins-${i}`,
          version: 1,
          loaded: false,
        })),
        edges: [
          { parent: 'root', child: 'targets' },
          { parent: 'targets', child: 'bins-0' },
          { parent: 'targets', child: 'bins-1' },
        ],
      }),
    );

    expect(model.children.get('targets')).toEqual([GROUP]);
    expect(model.delegated).toHaveLength(256);
  });

  it('puts a parent halfway between its first and last child', () => {
    const model = treeModel(
      overview({
        roles: named(['root', 'a', 'b', 'c']),
        edges: [
          { parent: 'root', child: 'a' },
          { parent: 'root', child: 'b' },
          { parent: 'root', child: 'c' },
        ],
      }),
    );

    const placed = layout(model);
    const at = (name: string) =>
      placed.nodes.find((node) => node.name === name)?.column;

    expect(at('a')).toBe(0);
    expect(at('c')).toBe(2);
    expect(at('root')).toBe(1);
  });

  it('ignores an edge naming a role that was never verified', () => {
    // Verification can stop part way, and the roles that were read are still
    // worth drawing. An edge into a role we do not have must not place a node.
    const model = treeModel(
      overview({
        roles: named(['root']),
        edges: [{ parent: 'root', child: 'targets' }],
      }),
    );

    expect(model.children.size).toBe(0);
    expect(layout(model).nodes).toHaveLength(1);
  });
});
