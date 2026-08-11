import type { RootVersionSummary } from '../../../api/types';
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
export function RootHistoryPage({ active }: { active: boolean }) {
  const { data, loading, error } = useRoots(active);

  if (error) return <ErrorBanner error={error} />;
  if (loading || !data) return <p className="muted">Reading the history…</p>;

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
        {version.key_count} key{version.key_count === 1 ? '' : 's'} ·{' '}
        {version.by_previous_keys
          ? 'signed by the keys before it'
          : 'NOT signed by the keys before it'}{' '}
        ·{' '}
        {version.by_own_keys ? 'signed by its own' : 'NOT signed by its own'}
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
