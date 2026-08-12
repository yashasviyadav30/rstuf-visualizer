// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { request } from '../../../api/client';
import type {
  ArtifactBinsResponse,
  ArtifactsResponse,
} from '../../../api/types';

/**
 * Every role holding artifacts, with a count each.
 *
 * Asked for before the artifacts themselves, so a repository split across two
 * 256 bins opens as a list of counts and not as a table
 * of every package it has ever carried.
 */
export function getBins(): Promise<ArtifactBinsResponse> {
  return request<ArtifactBinsResponse>('/artifacts/bins');
}

/**
 * One page of artifacts, from one bin or from all of them.
 *
 * A bin is asked for by name when a reader opens it. A search leaves the role
 * empty and spans every bin, because a path gives no clue which one holds it.
 */
export function getArtifacts(options: {
  role?: string;
  search?: string;
  page: number;
  pageSize: number;
}): Promise<ArtifactsResponse> {
  return request<ArtifactsResponse>('/artifacts', {
    role: options.role,
    search: options.search,
    page: options.page,
    page_size: options.pageSize,
  });
}
