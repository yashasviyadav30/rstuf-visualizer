// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useQuery } from '@tanstack/react-query';

import { getRoots } from '../endpoints/roots';

/** Read only when the tab is opened; nobody lands here first. */
export function useRoots(enabled: boolean) {
  return useQuery({ queryKey: ['roots'], queryFn: getRoots, enabled });
}
