// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useQuery } from '@tanstack/react-query';

import { getRoots } from '../endpoints/roots';

/** Read when this screen is routed to; nobody lands here first. */
export function useRoots() {
  return useQuery({ queryKey: ['roots'], queryFn: getRoots });
}
