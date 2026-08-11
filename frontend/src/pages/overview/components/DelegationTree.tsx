// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useMemo } from 'react';

import type { OverviewResponse } from '../../../api/types';
import {
  CHIP_H,
  CHIP_W,
  NODE_H,
  NODE_W,
  chipPositions,
  edgePath,
  layout,
  treeModel,
} from '../tree';
import { GROUP } from '../types/tree';

interface Props {
  overview: OverviewResponse;
  selected: string | null;
  binsOpen: boolean;
  onSelect: (name: string) => void;
  onToggleBins: () => void;
}

/**
 * The delegation tree, drawn from the metadata rather than from a picture.
 *
 * It answers "who delegates to whom" at a glance, which the table cannot.
 */
export function DelegationTree({
  overview,
  selected,
  binsOpen,
  onSelect,
  onToggleBins,
}: Props) {
  const { model, placed, byName } = useMemo(() => {
    const model = treeModel(overview);
    const placed = layout(model);
    const byName = new Map(placed.nodes.map((node) => [node.name, node]));
    return { model, placed, byName };
  }, [overview]);

  if (model.roles.size === 0) {
    return <p className="muted">Nothing verified to draw.</p>;
  }

  const group = byName.get(GROUP);
  const band =
    binsOpen && group
      ? chipPositions(
          model.delegated.length,
          group.y + NODE_H + 26,
          placed.width,
        )
      : null;

  const height = band ? placed.height + band.height + 26 : placed.height;

  return (
    <div className="tree">
      <svg
        viewBox={`0 0 ${placed.width} ${height}`}
        width={placed.width}
        height={height}
        role="img"
        aria-label="Delegation tree"
      >
        {[...model.children.entries()].flatMap(([parent, kids]) =>
          kids.map((kid) => {
            const from = byName.get(parent);
            const to = byName.get(kid);
            if (!from || !to) return null;
            return (
              <path
                key={`${parent}->${kid}`}
                className="gedge"
                d={edgePath(from, to)}
              />
            );
          }),
        )}

        {placed.nodes.map((node) => {
          const isGroup = node.name === GROUP;
          const role = model.roles.get(node.name);
          const count = model.delegated.length;

          const label = isGroup
            ? `${count} delegated ${count === 1 ? 'role' : 'roles'}`
            : node.name;
          const meta = isGroup
            ? binsOpen
              ? 'shown below'
              : 'click to expand'
            : `v${role?.version ?? '?'} · ${role?.expires_in ?? ''}`;

          const classes = ['gnode'];
          if (isGroup) classes.push('gnode--group');
          if (node.name === selected) classes.push('is-selected');

          return (
            <g
              key={node.name}
              className={classes.join(' ')}
              transform={`translate(${node.x},${node.y})`}
              onClick={() => (isGroup ? onToggleBins() : onSelect(node.name))}
            >
              <rect width={NODE_W} height={NODE_H} rx={5} />
              <circle
                className={`gnode__dot gnode__dot--${isGroup ? 'unknown' : (role?.band ?? 'unknown')}`}
                cx={14}
                cy={17}
                r={4}
              />
              <text className="gnode__name" x={26} y={21}>
                {label}
              </text>
              <text className="gnode__meta" x={14} y={36}>
                {meta}
              </text>
            </g>
          );
        })}

        {band?.positions.map((at, index) => {
          const bin = model.delegated[index];
          if (!bin) return null;
          return (
            <g
              key={bin.name}
              className={`gchip${bin.name === selected ? ' is-selected' : ''}`}
              transform={`translate(${at.x},${at.y})`}
              onClick={() => onSelect(bin.name)}
            >
              <rect width={CHIP_W} height={CHIP_H} rx={4} />
              <circle
                className="gnode__dot gnode__dot--unknown"
                cx={12}
                cy={15}
                r={3.5}
              />
              <text className="gchip__name" x={24} y={19}>
                {bin.name}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
