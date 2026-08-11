import type { DelegatedSummary, RoleSummary } from '../../../api/types';

/**
 * A name no TUF role can hold, so the collapsed group of delegated roles can
 * live in the same structure as real roles instead of being a special case
 * everywhere the layout touches it.
 */
export const GROUP = 'group:delegated' as const;

export interface TreeModel {
  roles: Map<string, RoleSummary>;
  children: Map<string, string[]>;
  tops: string[];
  delegated: DelegatedSummary[];
}

export interface PlacedNode {
  name: string;
  depth: number;
  column: number;
  x: number;
  y: number;
}

export interface TreeLayout {
  nodes: PlacedNode[];
  width: number;
  height: number;
}
