// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import type { ArtifactsResponse } from '../../../api/types';

/**
 * What this screen is looking at, and what came back.
 *
 * Two things can be on screen: one bin, opened from the list, or a search
 * running across every bin. They are exclusive, and `enabled` is how the
 * table knows the difference between "nothing matched" and "you have not
 * asked for anything yet" — which look the same and mean opposite things.
 */
export interface ArtifactPageState {
  data: ArtifactsResponse | undefined;
  loading: boolean;
  error: Error | null;
  page: number;
  setPage: (next: number) => void;
  /** False until a bin is opened or a search is typed. */
  enabled: boolean;
}
