// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { Route, Routes } from 'react-router';

import { HealthBadge } from './components/HealthBadge';
import { Tabs } from './components/Tabs';
import { ArtifactsPage } from './pages/artifacts/components/ArtifactsPage';
import { OverviewPage } from './pages/overview/components/OverviewPage';
import { useOverview } from './pages/overview/hooks/useOverview';
import { RootHistoryPage } from './pages/roots/components/RootHistoryPage';
import { StatusPage } from './pages/status/components/StatusPage';

export function App() {
  // Read once, above the routes, because the header carries the repository's
  // verdict on every screen and the refresh button belongs to all of them.
  const { overview, loading, error, refresh } = useOverview();

  return (
    <>
      <header className="topbar">
        <div className="container topbar__inner">
          <h1 className="topbar__title">RSTUF Metadata Visualizer</h1>
          <HealthBadge
            overview={overview}
            loading={loading}
            onRefresh={refresh}
          />
        </div>
      </header>

      <Tabs />

      <main className="container">
        {/* A screen is mounted when it is routed to and unmounted when it is
            left, so landing on this page never reads every bin in the
            repository. Switching back does not ask again either: the answers
            are held by the query cache, keyed on what was asked for. */}
        <section className="panel is-active">
          <Routes>
            <Route
              index
              element={
                <OverviewPage
                  overview={overview}
                  loading={loading}
                  error={error}
                />
              }
            />
            <Route path="/roots" element={<RootHistoryPage />} />
            <Route path="/artifacts" element={<ArtifactsPage />} />
            <Route path="/status" element={<StatusPage />} />
            {/* An address nobody published still has to answer. */}
            <Route
              path="*"
              element={
                <p className="muted">
                  No such screen. Try one of the tabs above.
                </p>
              }
            />
          </Routes>
        </section>
      </main>

      <footer className="footer">
        <div className="container">
          Read-only · every file shown was verified with{' '}
          <a href="https://github.com/theupdateframework/python-tuf">
            python-tuf
          </a>{' '}
          before it reached this page.
        </div>
      </footer>
    </>
  );
}
