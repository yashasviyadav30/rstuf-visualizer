import { request } from '../../../api/client';
import type { StatusResponse } from '../../../api/types';

/**
 * What the RSTUF API reports about the repository.
 *
 * This never fails the request. Status is helpful rather than load-bearing,
 * so an unreachable API hides one panel and leaves the rest standing.
 */
export function getStatus(): Promise<StatusResponse> {
  return request<StatusResponse>('/status');
}
