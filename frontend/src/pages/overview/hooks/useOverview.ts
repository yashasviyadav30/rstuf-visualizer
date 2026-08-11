import { useCallback, useState } from 'react';

import type { OverviewResponse, RoleDetailResponse } from '../../../api/types';
import { useAsync } from '../../../hooks/useAsync';
import { getOverview, getRole } from '../endpoints/overview';

export interface OverviewState {
  overview: OverviewResponse | null;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
}

export function useOverview(): OverviewState {
  // Held here rather than passed to getOverview through the dependency list,
  // so that pressing refresh twice is two requests rather than one ignored.
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const result = await getOverview(refreshing);
    setRefreshing(false);
    return result;
  }, [refreshing]);

  const { data, loading, error, reload } = useAsync(load, []);

  const refresh = useCallback(() => {
    setRefreshing(true);
    reload();
  }, [reload]);

  return { overview: data, loading, error, refresh };
}

/**
 * The role currently open, and how to open another.
 *
 * Roles already verified during the refresh are in the overview, but the
 * detail panel wants keys and signatures, so every role is asked for by name.
 */
export function useSelectedRole(): {
  selected: string | null;
  detail: RoleDetailResponse | null;
  loading: boolean;
  error: Error | null;
  select: (name: string | null) => void;
} {
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(
    () => (selected ? getRole(selected) : Promise.resolve(null)),
    [selected],
  );

  const { data, loading, error } = useAsync(load, [selected], {
    enabled: selected !== null,
  });

  return { selected, detail: data, loading, error, select: setSelected };
}
