// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useStatus } from '../hooks/useStatus';

/**
 * What the RSTUF API says, and plainly that it said nothing.
 *
 * This is the one panel whose source is not checked, because it is not a
 * security claim: it reports whether the repository has been bootstrapped and
 * what is waiting to be signed. The trust picture comes from the signed
 * metadata alone.
 */
export function StatusPage() {
  const { data, isFetching, error } = useStatus();

  if (isFetching || (!data && !error))
    return <p className="muted">Asking…</p>;

  if (error || !data?.available) {
    return (
      <p className="muted">
        No RSTUF API is configured, or it did not answer. The repository is
        still read and verified without it, because none of the trust picture
        comes from here.
      </p>
    );
  }

  return (
    <>
      <h2 className="section-title">Repository status</h2>

      <dl className="facts">
        <dt>State</dt>
        <dd>{data.state}</dd>
        <dt>Bootstrap</dt>
        <dd>{data.bootstrap || 'not reported'}</dd>
      </dl>

      {data.message && <p className="muted">{data.message}</p>}

      {/* When nothing awaits signing the API returns a message and no data
          field at all, so an empty list here is a real answer and not a
          gap. */}
      <h3>Awaiting signatures</h3>
      {data.awaiting_signatures && data.awaiting_signatures.length > 0 ? (
        <ul className="paths">
          {data.awaiting_signatures.map((role) => (
            <li key={role}>{role}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">Nothing is waiting to be signed.</p>
      )}

      {data.keys && data.keys.length > 0 && (
        <>
          <h3>Keys</h3>
          <ul className="keys">
            {data.keys.map((key) => (
              <li key={key.keyid}>
                <span className="key" title={key.keyid}>
                  <span
                    className={`key__dot key__dot--${key.online ? 'online' : 'offline'}`}
                  />
                  {key.name}
                </span>
                <span className="muted">
                  {key.online ? ' · online' : ' · offline'}
                  {(key.signs ?? []).length > 0 &&
                    ` · signs ${(key.signs ?? []).join(', ')}`}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
