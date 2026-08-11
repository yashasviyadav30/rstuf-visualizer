// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';

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
  const [refreshing, setRefreshing] = useState(false);

  const query = useQuery({
    queryKey: ['overview'],
    queryFn: async () => {
      const result = await getOverview(refreshing);
      setRefreshing(false);
      return result;
    },
  });

  const refresh = useCallback(() => {
    setRefreshing(true);
    void client.invalidateQueries({ queryKey: ['overview'] });
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
