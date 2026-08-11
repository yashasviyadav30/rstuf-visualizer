import { useState } from 'react';

import { HealthBadge } from './components/HealthBadge';
import { Tabs, type TabId } from './components/Tabs';
import { ArtifactsPage } from './pages/artifacts/components/ArtifactsPage';
import { OverviewPage } from './pages/overview/components/OverviewPage';
import { useOverview } from './pages/overview/hooks/useOverview';
import { RootHistoryPage } from './pages/roots/components/RootHistoryPage';
import { StatusPage } from './pages/status/components/StatusPage';

export function App() {
  const [tab, setTab] = useState<TabId>('roles');
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

      <Tabs active={tab} onSelect={setTab} />

      <main className="container">
        {/* Each panel is mounted only once its tab has been opened, and stays
            mounted afterwards. That is what keeps landing on this page from
            reading every bin in the repository, while switching back to a tab
            does not ask again. */}
        {tab === 'roles' && (
          <section className="panel is-active">
            <OverviewPage
              overview={overview}
              loading={loading}
              error={error}
            />
          </section>
        )}
        {tab === 'roots' && (
          <section className="panel is-active">
            <RootHistoryPage active />
          </section>
        )}
        {tab === 'artifacts' && (
          <section className="panel is-active">
            <ArtifactsPage active />
          </section>
        )}
        {tab === 'status' && (
          <section className="panel is-active">
            <StatusPage active />
          </section>
        )}
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
