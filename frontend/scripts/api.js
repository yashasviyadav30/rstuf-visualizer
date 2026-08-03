/* SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
 * SPDX-License-Identifier: MIT
 *
 * Calls to our own backend. The browser talks to nothing else: not the
 * storage holding the metadata, and not the RSTUF API.
 */

(function () {
  'use strict';

  const BASE = `${window.location.origin}/api/v1`;

  // Long enough for a cold verification pass, short enough that an
  // unreachable server reports itself instead of leaving the page waiting.
  const TIMEOUT_MS = 15000;

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
    }
  }

  async function request(path) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

    try {
      const response = await fetch(`${BASE}${path}`, {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });

      let body = null;
      try {
        body = await response.json();
      } catch (err) {
        body = null;
      }

      if (!response.ok) {
        const detail = (body && body.detail) || response.statusText;
        throw new ApiError(detail, response.status);
      }
      return body;
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if (err.name === 'AbortError') {
        throw new ApiError('The server did not answer in time.', 0);
      }
      throw new ApiError('Could not reach the visualizer backend.', 0);
    } finally {
      clearTimeout(timer);
    }
  }

  window.Api = {
    ApiError,
    overview: (refresh) =>
      request(`/overview${refresh ? '?refresh=true' : ''}`),
    role: (name) => request(`/roles/${encodeURIComponent(name)}`),
    roots: () => request('/roots'),
    artifacts: (search) =>
      request(`/artifacts?search=${encodeURIComponent(search || '')}`),
    status: () => request('/status'),
  };
})();
