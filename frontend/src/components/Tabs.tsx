// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

export const TABS = [
  { id: 'roles', label: 'Roles' },
  { id: 'roots', label: 'Root history' },
  { id: 'artifacts', label: 'Artifacts' },
  { id: 'status', label: 'Status' },
] as const;

export type TabId = (typeof TABS)[number]['id'];

interface Props {
  active: TabId;
  onSelect: (id: TabId) => void;
}

export function Tabs({ active, onSelect }: Props) {
  return (
    <nav className="tabs">
      <div className="container tabs__inner">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`tab${tab.id === active ? ' is-active' : ''}`}
            type="button"
            onClick={() => onSelect(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </nav>
  );
}
