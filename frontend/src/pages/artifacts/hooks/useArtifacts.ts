// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { getArtifacts, getBins } from '../endpoints/artifacts';
import type { ArtifactPageState } from '../types/artifacts';

export const PAGE_SIZE = 50;

/** The bin list, asked for once when this screen is first opened. */
export function useBins() {
  return useQuery({ queryKey: ['artifact-bins'], queryFn: getBins });
}

/**
 * The artifacts on screen: one bin, or a search across all of them.
 *
 * Nothing is asked for until a reader picks a bin or types, because the whole
 * point of the bin list is that opening this tab costs one small request.
 *
 * The page number is held against what is being paged through, rather than
 * reset when that changes. A narrower search has fewer pages, and page four
 * of the old result is not a place the new one has; keeping them apart says
 * that without an effect that writes state during a render.
 */
export function useArtifactPage(
  role: string | null,
  search: string,
): ArtifactPageState {
  const [pages, setPages] = useState<Record<string, number>>({});
  const key = `${role ?? ''}:${search}`;
  const page = pages[key] ?? 1;

  const enabled = role !== null || search.length > 0;

  const query = useQuery({
    queryKey: ['artifacts', role, search, page],
    queryFn: () =>
      getArtifacts({
        role: role ?? undefined,
        search,
        page,
        pageSize: PAGE_SIZE,
      }),
    enabled,
  });

  return {
    data: query.data,
    loading: query.isFetching,
    error: query.error,
    page,
    setPage: (next: number) => setPages((held) => ({ ...held, [key]: next })),
    enabled,
  };
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
