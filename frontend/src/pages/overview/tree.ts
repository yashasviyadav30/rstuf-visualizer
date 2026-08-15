// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

/**
 * Where each node in the delegation tree goes.
 *
 * Positions are computed, never written down, so the shape follows the
 * metadata: a repository that delegates differently draws differently, and no
 * role name appears anywhere in here.
 */
import type { OverviewResponse } from '../../api/types';
import type { PlacedNode, TreeLayout, TreeModel } from './types/tree';
import { GROUP } from './types/tree';

export const NODE_W = 148;
export const NODE_H = 46;
export const CHIP_W = 96;
export const CHIP_H = 30;
export const CHIP_GAP = 10;

const SIBLING_GAP = 22;
const LEVEL_GAP = 58;
const MARGIN = 14;

/**
 * Turn the overview into a parent-to-children map.
 *
 * The edges come from the response, so nothing here decides that timestamp
 * hangs off root or that bins hang off targets. Delegated roles are left out
 * and stand behind one group node, because a repository may hold 256 of
 * them and drawing each would hide the structure.
 */
export function treeModel(overview: OverviewResponse): TreeModel {
  const roles = new Map((overview.roles ?? []).map((role) => [role.name, role]));
  const delegated = overview.delegated ?? [];
  const delegatedNames = new Set(delegated.map((one) => one.name));

  const children = new Map<string, string[]>();
  const hasParent = new Set<string>();
  let groupParent: string | null = null;

  for (const { parent, child } of overview.edges ?? []) {
    if (delegatedNames.has(child)) {
      if (roles.has(parent)) groupParent = parent;
      continue;
    }
    if (!roles.has(parent) || !roles.has(child)) continue;
    children.set(parent, [...(children.get(parent) ?? []), child]);
    hasParent.add(child);
  }

  if (groupParent && delegated.length > 0) {
    children.set(groupParent, [...(children.get(groupParent) ?? []), GROUP]);
  }

  const tops = [...roles.keys()].filter((name) => !hasParent.has(name));
  return { roles, children, tops, delegated };
}

/**
 * Give every node a column and a row.
 *
 * A leaf takes the next free column, left to right, and a parent sits halfway
 * between its first and last child. That keeps subtrees from overlapping
 * without a layout library, and the shape a TUF repository makes is too
 * shallow to need one.
 */
export function layout(model: TreeModel): TreeLayout {
  const placed: Omit<PlacedNode, 'x' | 'y'>[] = [];
  let column = 0;

  const walk = (name: string, depth: number): number => {
    const kids = model.children.get(name) ?? [];
    let position: number;

    if (kids.length === 0) {
      position = column++;
    } else {
      const spread = kids.map((kid) => walk(kid, depth + 1));
      position = ((spread[0] ?? 0) + (spread[spread.length - 1] ?? 0)) / 2;
    }

    placed.push({ name, depth, column: position });
    return position;
  };

  for (const name of model.tops) walk(name, 0);

  const deepest = placed.reduce((max, node) => Math.max(max, node.depth), 0);
  const nodes: PlacedNode[] = placed.map((node) => ({
    ...node,
    x: MARGIN + node.column * (NODE_W + SIBLING_GAP),
    y: MARGIN + node.depth * (NODE_H + LEVEL_GAP),
  }));

  return {
    nodes,
    width: MARGIN * 2 + Math.max(1, column) * (NODE_W + SIBLING_GAP),
    height: MARGIN * 2 + (deepest + 1) * NODE_H + deepest * LEVEL_GAP,
  };
}

/** A curve from the bottom of one node to the top of another. */
export function edgePath(from: PlacedNode, to: PlacedNode): string {
  const x1 = from.x + NODE_W / 2;
  const y1 = from.y + NODE_H;
  const x2 = to.x + NODE_W / 2;
  const y2 = to.y;
  const bend = (y2 - y1) / 2;
  return `M${x1},${y1} C${x1},${y1 + bend} ${x2},${y2 - bend} ${x2},${y2}`;
}

/**
 * Where each delegated role sits once the group is opened.
 *
 * They are laid out as a block of chips under a single connector instead of
 * as branches. One edge per bin would be 256 lines
 * crossing the same gap, which hides the structure it is meant to show.
 */
export function chipPositions(
  count: number,
  top: number,
  width: number,
): { positions: { x: number; y: number }[]; height: number } {
  const perRow = Math.max(
    1,
    Math.floor((width - MARGIN * 2 + CHIP_GAP) / (CHIP_W + CHIP_GAP)),
  );

  const positions = Array.from({ length: count }, (_, index) => ({
    x: MARGIN + (index % perRow) * (CHIP_W + CHIP_GAP),
    y: top + Math.floor(index / perRow) * (CHIP_H + CHIP_GAP),
  }));

  return {
    positions,
    height: Math.ceil(count / perRow) * (CHIP_H + CHIP_GAP),
  };
}
