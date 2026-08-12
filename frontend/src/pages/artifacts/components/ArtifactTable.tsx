// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import type { ArtifactSummary } from '../../../api/types';

interface Props {
  artifacts: ArtifactSummary[];
  loading: boolean;
  error: Error | null;
  prompted: boolean;
  showRole: boolean;
}

export function ArtifactTable({
  artifacts,
  loading,
  error,
  prompted,
  showRole,
}: Props) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th scope="col">Path</th>
          {showRole && <th scope="col">Role</th>}
          <th scope="col">Size</th>
          <th scope="col">SHA-256</th>
        </tr>
      </thead>
      <tbody>
        {prompted && (
          <tr>
            <td colSpan={showRole ? 4 : 3} className="muted">
              Open a bin, or search across all of them.
            </td>
          </tr>
        )}
        {!prompted && loading && (
          <tr>
            <td colSpan={showRole ? 4 : 3} className="muted">
              Reading…
            </td>
          </tr>
        )}
        {error && (
          <tr>
            <td colSpan={showRole ? 4 : 3} className="state state--invalid">
              {error.message}
            </td>
          </tr>
        )}
        {!prompted && !loading && !error && artifacts.length === 0 && (
          <tr>
            <td colSpan={showRole ? 4 : 3} className="muted">
              Nothing here.
            </td>
          </tr>
        )}
        {artifacts.map((artifact) => (
          <tr key={`${artifact.role}/${artifact.path}`}>
            <td className="path">{artifact.path}</td>
            {showRole && <td>{artifact.role}</td>}
            <td>{size(artifact.length)}</td>
            <td className="hash" title={artifact.hashes?.['sha256'] ?? ''}>
              {(artifact.hashes?.['sha256'] ?? '').slice(0, 16) || '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1_048_576).toFixed(2)} MB`;
}
