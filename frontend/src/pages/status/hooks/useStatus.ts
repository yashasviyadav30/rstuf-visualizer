// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useQuery } from '@tanstack/react-query';

import { getStatus } from '../endpoints/status';

/** Read only when the tab is opened. Status is helpful, not load-bearing. */
export function useStatus(enabled: boolean) {
  return useQuery({ queryKey: ['status'], queryFn: getStatus, enabled });
}
