// SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
//
// SPDX-License-Identifier: MIT

import { NavLink } from 'react-router';

const TABS = [
  { to: '/', label: 'Roles' },
  { to: '/roots', label: 'Root history' },
  { to: '/artifacts', label: 'Artifacts' },
  { to: '/status', label: 'Status' },
] as const;

/**
 * The four screens, as links. Buttons would not survive a bookmark.
 *
 * A link can be copied, sent and reopened, which is the point of routing
 * them: "look at the root history of this repository" is a thing one person
 * says to another, and a button could not carry it.
 */
export function Tabs() {
  return (
    <nav className="tabs" aria-label="Screens">
      <div className="container tabs__inner">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.to === '/'}
            className={({ isActive }) => `tab${isActive ? ' is-active' : ''}`}
          >
            {tab.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
