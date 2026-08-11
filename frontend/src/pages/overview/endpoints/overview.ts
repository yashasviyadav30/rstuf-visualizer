// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { request } from '../../../api/client';
import type { OverviewResponse, RoleDetailResponse } from '../../../api/types';

/** The whole repository in one request: roles, their state, and the tree. */
export function getOverview(refresh = false): Promise<OverviewResponse> {
  return request<OverviewResponse>('/overview', { refresh });
}

/**
 * One role, fetched when it is opened.
 *
 * A delegated role costs a request here rather than at page load, which is
 * what keeps a repository of two hundred and fifty-six bins cheap to draw.
 */
export function getRole(name: string): Promise<RoleDetailResponse> {
  return request<RoleDetailResponse>(`/roles/${encodeURIComponent(name)}`);
}

/** Where the bytes a role was verified from can be downloaded. */
export function rawUrl(name: string): string {
  return `/api/v1/roles/${encodeURIComponent(name)}/raw`;
}
