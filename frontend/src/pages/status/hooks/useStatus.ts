// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useQuery } from '@tanstack/react-query';

import { getStatus } from '../endpoints/status';

/** Read when this screen is routed to. Status is helpful, not load-bearing. */
export function useStatus() {
  return useQuery({ queryKey: ['status'], queryFn: getStatus });
}
