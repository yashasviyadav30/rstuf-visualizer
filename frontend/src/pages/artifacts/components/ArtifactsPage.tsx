// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { useState } from 'react';

import { Banner, ErrorBanner } from '../../../components/Banner';
import {
  PAGE_SIZE,
  useArtifactPage,
  useBins,
  useDebounced,
} from '../hooks/useArtifacts';
import { BinList } from './BinList';
import { ArtifactTable } from './ArtifactTable';

/**
 * Artifacts, a bin at a time.
 *
 * Dumping every artifact on one screen is wrong twice over: with two hundred
 * and fifty-six bins the first load reads the whole repository, and the table
 * it produces is not something a person can use. So the tab opens as a list
 * of bins with counts, and reads nothing else until a bin is opened or a
 * search is typed.
 */
export function ArtifactsPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [typed, setTyped] = useState('');
  const search = useDebounced(typed);

  const bins = useBins();
  const page = useArtifactPage(search ? null : selected, search);

  if (bins.error) return <ErrorBanner error={bins.error} />;

  const shown = page.data?.artifacts?.length ?? 0;
  const total = page.data?.total ?? 0;
  const first = total === 0 ? 0 : (page.page - 1) * PAGE_SIZE + 1;

  return (
    <>
      <div className="toolbar">
        {/* A placeholder is a hint, not a name: it disappears the moment
            someone types, and a screen reader announcing an unnamed field
            has nothing to say about it. */}
        <label className="visually-hidden" htmlFor="artifact-search">
          Search artifacts by path, across every bin
        </label>
        <input
          id="artifact-search"
          type="search"
          placeholder="Search by path, across every bin…"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
        {page.enabled && (
          <span className="muted">
            {total === 0
              ? 'nothing matches'
              : `${first}–${first + shown - 1} of ${total}`}
          </span>
        )}
        {page.enabled && total > PAGE_SIZE && (
          <div className="pager">
            <button
              className="btn"
              type="button"
              disabled={page.page === 1}
              onClick={() => page.setPage(page.page - 1)}
            >
              Previous
            </button>
            <button
              className="btn"
              type="button"
              disabled={first + shown - 1 >= total}
              onClick={() => page.setPage(page.page + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* A bin that could not be read is named. The difference between "this
          bin is empty" and "this bin did not verify" is the whole point. */}
      {page.data?.unavailable && page.data.unavailable.length > 0 && (
        <Banner kind="warn">
          <strong>Some roles could not be read:</strong>{' '}
          {page.data.unavailable.join(', ')}. Artifacts they hold are missing
          from this list.
        </Banner>
      )}

      <div className="split">
        <div className="col col--narrow">
          <h2 className="section-title">Bins</h2>
          <BinList
            bins={bins.data?.bins ?? []}
            total={bins.data?.total ?? 0}
            loading={bins.isFetching}
            selected={search ? null : selected}
            onSelect={(name) => {
              setTyped('');
              setSelected(name);
            }}
          />
        </div>

        <div className="col">
          <h2 className="section-title">
            {search
              ? `Matching “${search}”`
              : selected
                ? selected
                : 'Artifacts'}
          </h2>
          <ArtifactTable
            artifacts={page.data?.artifacts ?? []}
            loading={page.loading}
            error={page.error}
            prompted={!page.enabled}
            showRole={Boolean(search)}
          />
          <p className="note">
            Paths, sizes and hashes only. This service never serves artifact
            files, and never says one is safe to install.
          </p>
        </div>
      </div>
    </>
  );
}
