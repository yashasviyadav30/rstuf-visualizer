// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useState } from 'react';

import type { OverviewResponse } from '../../../api/types';
import { Banner, ErrorBanner } from '../../../components/Banner';
import { useSelectedRole } from '../hooks/useOverview';
import { DelegationTree } from './DelegationTree';
import { RoleDetail } from './RoleDetail';
import { RolesTable } from './RolesTable';

interface Props {
  overview: OverviewResponse | undefined;
  loading: boolean;
  error: Error | null;
}

export function OverviewPage({ overview, loading, error }: Props) {
  const { selected, detail, loading: roleLoading, error: roleError, select } =
    useSelectedRole();
  const [binsOpen, setBinsOpen] = useState(false);

  if (error) return <ErrorBanner error={error} />;
  if (!overview) return <p className="muted">Loading…</p>;

  // A repository that has not been set up is a real state rather than a
  // failure, so one short card replaces the table instead of an error.
  if (overview.message) {
    return (
      <Banner kind="info">
        <strong>Not ready.</strong> {overview.message}
      </Banner>
    );
  }

  return (
    <>
      {/* Broken trust is the subject of this service, so it is reported in
          place, with the roles that could still be read left on screen. */}
      {overview.verification_error && (
        <Banner kind="warn">
          <strong>Verification stopped.</strong> {overview.verification_error}
        </Banner>
      )}

      <div className="split">
        <div className="col">
          <h2 className="section-title">Roles</h2>
          <RolesTable
            roles={overview.roles ?? []}
            selected={selected}
            onSelect={select}
          />

          <h2 className="section-title">Delegation tree</h2>
          <DelegationTree
            overview={overview}
            selected={selected}
            binsOpen={binsOpen}
            onSelect={select}
            onToggleBins={() => setBinsOpen((open) => !open)}
          />
        </div>

        <aside className="col">
          <h2 className="section-title">Detail</h2>
          <div className="detail">
            <RoleDetail
              detail={detail}
              loading={roleLoading || (loading && !overview)}
              error={roleError}
              selected={selected}
            />
          </div>
        </aside>
      </div>
    </>
  );
}
