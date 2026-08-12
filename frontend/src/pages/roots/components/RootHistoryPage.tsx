// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import type {
  RootVersionSummary,
  SignatureCheckSummary,
} from '../../../api/types';
import { ErrorBanner } from '../../../components/Banner';
import { useRoots } from '../hooks/useRoots';

/**
 * How root reached the version in force today.
 *
 * This is how a signer confirms a rotation went as intended, and it looks
 * where an ordinary refresh never does: a client moves forward from the root
 * it holds, so once it settles on the newest it stops reading the older ones.
 * An archived root corrupted or swapped after the fact therefore goes
 * unnoticed by every normal client. Reading the history is what finds it.
 */
export function RootHistoryPage() {
  const { data, isFetching, error } = useRoots();

  if (error) return <ErrorBanner error={error} />;
  if (isFetching || !data)
    return <p className="muted">Reading the history…</p>;

  return (
    <>
      <h2 className="section-title">How root reached version {data.current}</h2>
      {data.message && <p className="muted">{data.message}</p>}

      <ol className="roots">
        {(data.versions ?? []).map((version) => (
          <RootVersion key={version.version} version={version} />
        ))}
      </ol>

      <p className="note">
        Each version must be signed by the keys of the version before it and by
        its own. A step that fails that rule is marked, not hidden. Superseded
        versions are not graded for expiry: old roots lapse as a matter of
        course, and a client checks expiry on the newest alone.
      </p>
    </>
  );
}

/**
 * One threshold check, reported with the numbers behind it.
 *
 * The check is an object, not a flag, and reading it as one would say "signed"
 * for a check that failed. On the screen that exists to audit rotations, that
 * is the difference between clearing a broken root and accusing a sound one,
 * so the count is shown, not a verdict on its own.
 */
function SignatureCheck({
  check,
  by,
}: {
  check: SignatureCheckSummary;
  by: string;
}) {
  return (
    <span className={check.verified ? undefined : 'state state--invalid'}>
      {check.verified ? 'signed by' : 'NOT signed by'} {by} ({check.present} of{' '}
      {check.threshold})
    </span>
  );
}

function RootVersion({ version }: { version: RootVersionSummary }) {
  return (
    <li className={version.verified ? 'root' : 'root root--unverified'}>
      <h3>
        Version {version.version}
        {version.superseded ? (
          <span className="muted"> · superseded</span>
        ) : (
          <span className={`state state--${version.band}`}>
            {' '}
            · {version.expires_in}
          </span>
        )}
      </h3>

      <p className="muted">
        {version.key_count} key{version.key_count === 1 ? '' : 's'}
        {' · '}
        <SignatureCheck check={version.by_own_keys} by="its own keys" />
        {' · '}
        {version.by_previous_keys ? (
          <SignatureCheck
            check={version.by_previous_keys}
            by="the keys before it"
          />
        ) : (
          // The oldest version reached has nothing above it to be checked
          // against, which is not the same as failing that check.
          <span>no earlier version was read</span>
        )}
      </p>

      {version.note && <p className="state state--invalid">{version.note}</p>}

      {version.keys_changed && version.keys_changed.length > 0 && (
        <ul className="changes">
          {version.keys_changed.map((change) => (
            <li key={`${change.keyid}-${change.action}`}>
              <span className={`change change--${change.action}`}>
                {change.action}
              </span>{' '}
              {change.name || change.keyid_short}
            </li>
          ))}
        </ul>
      )}

      {version.roles_changed && version.roles_changed.length > 0 && (
        <ul className="changes">
          {version.roles_changed.map((change) => (
            <li key={change.role}>
              <strong>{change.role}</strong>: threshold{' '}
              {change.threshold_before} → {change.threshold_after}
              {(change.signers_added ?? []).length > 0 && (
                <> · added {(change.signers_added ?? []).join(', ')}</>
              )}
              {(change.signers_removed ?? []).length > 0 && (
                <> · removed {(change.signers_removed ?? []).join(', ')}</>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
