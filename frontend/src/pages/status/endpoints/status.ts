// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { request } from '../../../api/client';
import type { StatusResponse } from '../../../api/types';

/**
 * What the RSTUF API reports about the repository.
 *
 * This never fails the request. Status is helpful, not load-bearing,
 * so an unreachable API hides one panel and leaves the rest standing.
 */
export function getStatus(): Promise<StatusResponse> {
  return request<StatusResponse>('/status');
}
