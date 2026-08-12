// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';

import type { OverviewResponse, RoleDetailResponse } from '../../../api/types';
import { getOverview, getRole } from '../endpoints/overview';

export interface OverviewState {
  overview: OverviewResponse | undefined;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
}

/**
 * The whole repository, and a way to ask for it again.
 *
 * Refreshing is not the same as refetching. Asking with `refresh=true` tells
 * the backend to discard its own cached reading and check the repository,
 * which it declines when the answer in hand is only seconds old. Refetching
 * without it would return that same reading and look like nothing happened.
 */
export function useOverview(): OverviewState {
  const client = useQueryClient();

  // A ref, not state, and the distinction is the whole of this hook.
  // Refetching starts synchronously, inside the same handler, before React
  // has re-rendered. A flag set through state is not visible to the function
  // that reads it until the render after that, so the request went out
  // without the one thing the button exists to send.
  const askedForCheck = useRef(false);

  const query = useQuery({
    queryKey: ['overview'],
    queryFn: () => {
      // Read and cleared before anything can fail, so the flag belongs to
      // this request. Left set by a rejected one, it would attach itself to
      // whichever fetch happened next.
      const refresh = askedForCheck.current;
      askedForCheck.current = false;
      return getOverview(refresh);
    },
  });

  const refresh = useCallback(() => {
    askedForCheck.current = true;
    void client.refetchQueries({ queryKey: ['overview'] });
  }, [client]);

  return {
    overview: query.data,
    loading: query.isFetching,
    error: query.error,
    refresh,
  };
}

/**
 * The role currently open, and how to open another.
 *
 * A delegated role is fetched when it is opened rather than at page load,
 * which is what keeps a repository of two hundred and fifty-six bins cheap to
 * draw. Opening one a second time costs nothing, because the answer is held
 * against the role's name.
 */
export function useSelectedRole(): {
  selected: string | null;
  detail: RoleDetailResponse | undefined;
  loading: boolean;
  error: Error | null;
  select: (name: string | null) => void;
} {
  const [selected, setSelected] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['role', selected],
    queryFn: () => getRole(selected as string),
    enabled: selected !== null,
  });

  return {
    selected,
    detail: query.data,
    loading: query.isFetching,
    error: query.error,
    select: setSelected,
  };
}
