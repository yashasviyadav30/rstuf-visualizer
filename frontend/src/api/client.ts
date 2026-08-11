/**
 * The one place this interface talks to the backend.
 *
 * Every path is relative, with no host in front of it, because the backend
 * serves these files itself in every deployment. During development the Vite
 * proxy forwards them; nothing here has to know which of the two it is.
 */

/** A reply the backend refused to give, carrying the reason it gave. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /**
   * Whether this is the backend saying it cannot check anything.
   *
   * Worth separating: a repository that fails verification is the subject of
   * this interface and draws normally, while a missing trust anchor means
   * there is nothing to draw at all.
   */
  get isUnverifiable(): boolean {
    return this.status === 503;
  }
}

const BASE = '/api/v1';

export async function request<T>(
  path: string,
  params: Record<string, string | number | boolean | undefined> = {},
): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') {
      query.set(key, String(value));
    }
  }

  const suffix = query.size > 0 ? `?${query}` : '';
  const response = await fetch(`${BASE}${path}${suffix}`, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response));
  }

  return (await response.json()) as T;
}

/**
 * The message the backend sent, where it sent one.
 *
 * Every failure from this API carries a `detail` written for a person, and
 * losing it in favour of "502 Bad Gateway" would throw away the only part of
 * the answer worth reading.
 */
async function detailOf(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === 'object' &&
      body !== null &&
      'detail' in body &&
      typeof body.detail === 'string'
    ) {
      return body.detail;
    }
  } catch {
    // A reply that is not JSON tells us nothing beyond its status.
  }
  return response.statusText || `Request failed with ${response.status}`;
}
