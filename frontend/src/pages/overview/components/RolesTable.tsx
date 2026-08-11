// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import type { RoleSummary } from '../../../api/types';

interface Props {
  roles: RoleSummary[];
  selected: string | null;
  onSelect: (name: string) => void;
}

/**
 * The landing view, because it is dense and scannable.
 *
 * The threshold is shown beside the signers rather than on its own: "2 of 2"
 * says the arrangement, where a bare "2" says almost nothing.
 */
export function RolesTable({ roles, selected, onSelect }: Props) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Role</th>
          <th>Signers</th>
          <th>Ver.</th>
          <th>Expiry</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {roles.length === 0 && (
          <tr>
            <td colSpan={5} className="muted">
              No roles were verified.
            </td>
          </tr>
        )}
        {roles.map((role) => (
          <tr
            key={role.name}
            className={role.name === selected ? 'is-selected' : undefined}
            onClick={() => onSelect(role.name)}
          >
            <td>
              <button className="linklike" type="button">
                {role.name}
              </button>
            </td>
            <td>
              {(role.key_names ?? []).map((name) => (
                <span className="key" key={name}>
                  {name}
                </span>
              ))}{' '}
              <span className="muted">
                ({role.threshold ?? '?'} of {role.key_count ?? '?'})
              </span>
            </td>
            <td>{role.version}</td>
            <td className={`state state--${role.band}`}>{role.expires_in}</td>
            <td className={`state state--${role.status}`}>{role.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
