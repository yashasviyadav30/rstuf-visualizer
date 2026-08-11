import type { KeySummary, RoleDetailResponse } from '../../../api/types';
import { rawUrl } from '../endpoints/overview';

interface Props {
  detail: RoleDetailResponse | null;
  loading: boolean;
  error: Error | null;
  selected: string | null;
}

export function RoleDetail({ detail, loading, error, selected }: Props) {
  if (!selected) {
    return (
      <p className="muted">
        Select a role to see its keys, signatures and artifacts.
      </p>
    );
  }

  if (loading) return <p className="muted">Reading {selected}…</p>;

  if (error) {
    return (
      <p className="state state--invalid">
        {selected} could not be read. {error.message}
      </p>
    );
  }

  if (!detail) return null;

  return (
    <div className="detail__body">
      <h3>{detail.name}</h3>

      <dl className="facts">
        <dt>Version</dt>
        <dd>{detail.version}</dd>
        <dt>Expires</dt>
        <dd className={`state state--${detail.band}`}>{detail.expires_in}</dd>
        <dt>Status</dt>
        <dd className={`state state--${detail.status}`}>{detail.status}</dd>
        <dt>Signatures</dt>
        {/* Both halves can be absent, and an empty number beside a real one
            reads as zero rather than as unknown. */}
        <dd>
          {detail.signatures_present ?? '?'} of {detail.threshold ?? '?'}{' '}
          required
        </dd>
      </dl>

      {/* A role edited after signing is named with its shortfall rather than
          folded into a generic failure, because which role fell short is the
          thing an operator has to act on. */}
      {detail.signature_note && (
        <p className="state state--invalid">{detail.signature_note}</p>
      )}

      <h4>Keys</h4>
      <ul className="keys">
        {(detail.signed_by ?? []).map((key: KeySummary) => (
          <li key={key.keyid}>
            <span className="key" title={key.keyid}>
              <span
                className={`key__dot key__dot--${key.online ? 'online' : 'offline'}`}
              />
              {key.name}
            </span>
            <span className="muted"> {key.scheme}</span>
            {/* Which keys are held offline is the security model, and raw
                metadata hides it. */}
            <span className="muted">
              {key.online ? ' · online' : ' · offline'}
            </span>
          </li>
        ))}
      </ul>

      {detail.delegates_to && detail.delegates_to.length > 0 && (
        <>
          <h4>Delegates to</h4>
          <p className="muted">{detail.delegates_to.join(', ')}</p>
        </>
      )}

      {detail.artifacts && detail.artifacts.length > 0 && (
        <>
          <h4>Artifacts</h4>
          <ul className="paths">
            {detail.artifacts.map((artifact) => (
              <li key={artifact.path}>{artifact.path}</li>
            ))}
          </ul>
        </>
      )}

      {/* The link points at this service, not at the storage the file came
          from: the reader may have no route to that storage, and a fresh
          fetch would return whatever is there now, which nobody has checked. */}
      <p>
        <a className="btn" href={rawUrl(detail.name)}>
          Download the signed file
        </a>
      </p>
    </div>
  );
}
