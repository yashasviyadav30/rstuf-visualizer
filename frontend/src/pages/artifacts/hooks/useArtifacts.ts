import { useCallback, useEffect, useState } from 'react';

import { useAsync } from '../../../hooks/useAsync';
import { getArtifacts, getBins } from '../endpoints/artifacts';

export const PAGE_SIZE = 50;

/** The bin list, asked for once when the tab is first opened. */
export function useBins(enabled: boolean) {
  return useAsync(getBins, [], { enabled });
}

/**
 * The artifacts on screen: one bin, or a search across all of them.
 *
 * Nothing is asked for until a reader picks one or types, because the whole
 * point of the bin list is that opening this tab costs one small request.
 */
export function useArtifactPage(role: string | null, search: string) {
  const [page, setPage] = useState(1);

  // A narrower search has fewer pages, so page four of the old result is not
  // a place the new one has.
  useEffect(() => setPage(1), [role, search]);

  const load = useCallback(
    () =>
      getArtifacts({
        role: role ?? undefined,
        search,
        page,
        pageSize: PAGE_SIZE,
      }),
    [role, search, page],
  );

  const enabled = role !== null || search.length > 0;
  const result = useAsync(load, [role, search, page], { enabled });

  return { ...result, page, setPage, enabled };
}

/** Wait for typing to stop before asking, so each keystroke is not a request. */
export function useDebounced<T>(value: T, delay = 250): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return settled;
}
