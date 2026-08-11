// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { ApiError } from '../api/client';

/**
 * Something the reader has to be told before they read anything else.
 *
 * Kept apart from the panels because the three cases it covers are not
 * failures of a screen: a repository that is not set up yet, one whose
 * metadata did not verify, and a service with no trust anchor. The first two
 * are the subject of this interface rather than an error in it.
 */
export function Banner({
  kind,
  children,
}: {
  kind: 'info' | 'warn';
  children: React.ReactNode;
}) {
  return <div className={`banner banner--${kind}`}>{children}</div>;
}

export function ErrorBanner({ error }: { error: Error }) {
  if (error instanceof ApiError && error.isUnverifiable) {
    return (
      <Banner kind="warn">
        <strong>Nothing can be checked.</strong> {error.message}
      </Banner>
    );
  }

  return (
    <Banner kind="warn">
      <strong>The repository could not be read.</strong> {error.message}
    </Banner>
  );
}
