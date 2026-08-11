// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { request } from '../../../api/client';
import type { RootsResponse } from '../../../api/types';

/** How root reached the version in force today, rotation by rotation. */
export function getRoots(): Promise<RootsResponse> {
  return request<RootsResponse>('/roots');
}
