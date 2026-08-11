/* SPDX-FileCopyrightText: 2026 Repository Service for TUF Contributors
 * SPDX-License-Identifier: MIT
 *
 * Rendering and page state.
 *
 * Delegated roles are drawn from their names alone and fetched only when
 * one is opened, which is why a repository with two hundred bins costs the
 * same to display as one with two.
 */

(function () {
  'use strict';

  const state = {
    overview: null,
    selected: null,
    binsOpen: false,
    loadedBins: new Map(),
    artifactsLoaded: false,
    artifactSearch: '',
    artifactPage: 1,
    statusLoaded: false,
    rootsLoaded: false,
    checkedAt: null,
  };

  const $ = (id) => document.getElementById(id);
  const esc = (value) =>
    String(value == null ? '' : value).replace(
      /[&<>"']/g,
      (c) =>
        ({
          '&': '&amp;',
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#39;',
        })[c]
    );

  function size(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(2)} MB`;
  }

  function keyChip(key) {
    const kind = key.online ? 'online' : 'offline';
    const title = key.online
      ? 'Held online, used for automatic signing'
      : 'Held offline by a person';
    return (
      `<span class="key" title="${title}">` +
      `<span class="key__dot key__dot--${kind}"></span>` +
      `${esc(key.name)}</span>`
    );
  }

  /* ---------------- header ---------------- */

  function plural(count, word) {
    return `${count} ${word}${count === 1 ? '' : 's'}`;
  }

  /* How old the answer on screen is, in words.
   *
   * A clock time answers a question nobody asked. What sends someone to the
   * refresh button is not knowing whether they are looking at something
   * current, and "checked 4 seconds ago" settles that without a click.
   */
  function ago(iso) {
    const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (seconds < 45) return plural(Math.round(seconds), 'second');
    const minutes = seconds / 60;
    if (minutes < 45) return plural(Math.round(minutes), 'minute');
    return plural(Math.round(minutes / 60), 'hour');
  }

  function renderCheckedAt() {
    const element = $('checked-at');
    element.textContent = state.checkedAt
      ? `checked ${ago(state.checkedAt)}`
      : '';
  }

  /* The header carries one verdict, so it has to mean something.
   *
   * It used to show the worst expiry band found on any role, which left it
   * amber for ever: RSTUF gives timestamp a one-day life and renews it on a
   * schedule, so a perfectly healthy repository always holds a role inside a
   * day of expiring. A warning that is always on is not a warning.
   *
   * The narrower question it answers now is whether anything is actually
   * wrong. Something expired, or a signature that did not check out, is
   * wrong. Root running down is the one countdown that earns a place beside
   * them, because root is the role no worker can renew: it is signed
   * offline, by people, and nothing will rescue it automatically.
   *
   * Every other band stays in the table, where a one-day expiry reads as the
   * ordinary information it is rather than as an alarm.
   */
  function renderHealth(overview) {
    const badge = $('health-badge');
    const label = $('health-label');
    const roles = overview.roles || [];
    const root = roles.find((role) => role.name === 'root');

    let band = 'valid';
    let text = 'All healthy';

    if (overview.status === 'invalid') {
      band = 'invalid';
      text = 'Verification failed';
    } else if (
      overview.status === 'expired' ||
      roles.some((role) => role.band === 'expired')
    ) {
      band = 'expired';
      text = 'Expired';
    } else if (
      root &&
      (root.band === 'critical' || root.band === 'expiring')
    ) {
      band = 'critical';
      text = `Root ${root.expires_in}`;
    }

    badge.className = `badge badge--${band}`;
    label.textContent = text;

    state.checkedAt = overview.checked_at || null;
    renderCheckedAt();
  }

  function renderBanner(overview) {
    const banner = $('banner');

    if (overview.message) {
      banner.className = 'banner banner--info';
      banner.innerHTML = `<strong>Not ready.</strong> ${esc(
        overview.message
      )}`;
      banner.hidden = false;
      return;
    }

    if (overview.verification_error) {
      banner.className = 'banner';
      banner.innerHTML =
        '<strong>Verification stopped.</strong> ' +
        `${esc(overview.verification_error)}. ` +
        'Roles verified before this point are shown; the rest could not be ' +
        'checked, so they are not displayed.';
      banner.hidden = false;
      return;
    }

    banner.hidden = true;
  }

  /* ---------------- roles ---------------- */

  function renderRoles(overview) {
    const body = $('roles-body');
    const roles = overview.roles || [];

    if (!roles.length) {
      body.innerHTML =
        '<tr><td colspan="5" class="muted">No verified roles.</td></tr>';
      return;
    }

    body.innerHTML = roles
      .map(
        (role) => `
        <tr class="is-clickable" data-role="${esc(role.name)}">
          <td>${esc(role.name)}</td>
          <td>${(role.key_names || []).map((n) => esc(n)).join(', ')}
              <span class="muted">(${role.threshold ?? '?'} of
              ${role.key_count ?? '?'})</span></td>
          <td>${role.version}</td>
          <td class="state state--${esc(role.band)}">${esc(
            role.expires_in
          )}</td>
          <td class="state state--${esc(role.status)}">${esc(
            role.status
          )}</td>
        </tr>`
      )
      .join('');

    body.querySelectorAll('tr[data-role]').forEach((row) => {
      row.addEventListener('click', () => select(row.dataset.role));
    });
  }

  /* ---------------- tree ----------------
   *
   * Drawn as a graph, positioned by the code below rather than by hand. The
   * shape therefore follows the metadata: a repository that delegates
   * differently draws differently, and no role name appears in the layout.
   */

  const NODE_W = 148;
  const NODE_H = 46;
  const SIBLING_GAP = 22;
  const LEVEL_GAP = 58;
  const MARGIN = 14;

  const CHIP_W = 96;
  const CHIP_H = 30;
  const CHIP_GAP = 10;

  // A name no TUF role can hold, so the collapsed group can live in the same
  // structure as real roles instead of being a special case in the layout.
  const GROUP = 'group:delegated';

  /* Turn the overview into a parent-to-children map.
   *
   * Edges come from the response, so nothing here decides that timestamp
   * hangs off root or that bins hang off targets. Delegated roles are left
   * out and stand behind one group node, because a repository may hold two
   * hundred and fifty-six of them.
   */
  function treeModel(overview) {
    const roles = new Map((overview.roles || []).map((r) => [r.name, r]));
    const delegated = overview.delegated || [];
    const delegatedNames = new Set(delegated.map((d) => d.name));

    const children = new Map();
    const hasParent = new Set();
    let groupParent = null;

    (overview.edges || []).forEach(({ parent, child }) => {
      if (delegatedNames.has(child)) {
        if (roles.has(parent)) groupParent = parent;
        return;
      }
      if (!roles.has(parent) || !roles.has(child)) return;
      if (!children.has(parent)) children.set(parent, []);
      children.get(parent).push(child);
      hasParent.add(child);
    });

    if (groupParent && delegated.length) {
      if (!children.has(groupParent)) children.set(groupParent, []);
      children.get(groupParent).push(GROUP);
    }

    const tops = [...roles.keys()].filter((name) => !hasParent.has(name));
    return { roles, children, tops, delegated };
  }

  /* Give every node a column and a row.
   *
   * Leaves take the next free column, left to right, and a parent sits
   * halfway between its first and last child. That keeps subtrees from
   * overlapping without needing a layout library, which would mean a build
   * step this project deliberately does not have.
   */
  function layout(model) {
    const placed = [];
    let column = 0;

    const walk = (name, depth) => {
      const kids = model.children.get(name) || [];
      let x;
      if (!kids.length) {
        x = column++;
      } else {
        const spread = kids.map((kid) => walk(kid, depth + 1));
        x = (spread[0] + spread[spread.length - 1]) / 2;
      }
      placed.push({ name, depth, column: x });
      return x;
    };

    model.tops.forEach((name) => walk(name, 0));

    const depth = placed.reduce((max, n) => Math.max(max, n.depth), 0);
    const nodes = placed.map((n) => ({
      ...n,
      x: MARGIN + n.column * (NODE_W + SIBLING_GAP),
      y: MARGIN + n.depth * (NODE_H + LEVEL_GAP),
    }));

    return {
      nodes,
      width: MARGIN * 2 + Math.max(1, column) * (NODE_W + SIBLING_GAP),
      height: MARGIN * 2 + (depth + 1) * NODE_H + depth * LEVEL_GAP,
    };
  }

  function edgePath(from, to) {
    const x1 = from.x + NODE_W / 2;
    const y1 = from.y + NODE_H;
    const x2 = to.x + NODE_W / 2;
    const y2 = to.y;
    const bend = (y2 - y1) / 2;
    return `M${x1},${y1} C${x1},${y1 + bend} ${x2},${y2 - bend} ${x2},${y2}`;
  }

  function nodeSvg(node, model) {
    const isGroup = node.name === GROUP;
    const role = model.roles.get(node.name);
    const count = model.delegated.length;

    const label = isGroup
      ? `${count} delegated ${count === 1 ? 'role' : 'roles'}`
      : node.name;
    const meta = isGroup
      ? state.binsOpen
        ? 'shown below'
        : 'click to expand'
      : `v${role.version} · ${role.expires_in}`;
    const band = isGroup ? 'unknown' : role.band;

    const classes = ['gnode'];
    if (isGroup) classes.push('gnode--group');
    if (node.name === state.selected) classes.push('is-selected');

    return `
      <g class="${classes.join(' ')}" data-node="${esc(node.name)}"
         transform="translate(${node.x},${node.y})">
        <rect width="${NODE_W}" height="${NODE_H}" rx="5"></rect>
        <circle class="gnode__dot gnode__dot--${esc(band)}"
                cx="14" cy="17" r="4"></circle>
        <text class="gnode__name" x="26" y="21">${esc(label)}</text>
        <text class="gnode__meta" x="14" y="36">${esc(meta)}</text>
      </g>`;
  }

  /* The expanded delegated roles, drawn as a band rather than as branches.
   *
   * One edge per bin would be two hundred and fifty-six lines crossing the
   * same gap, which hides the structure it is meant to show. A single
   * connector into a block of chips says the same thing and stays readable.
   */
  function binBand(model, top, width) {
    const perRow = Math.max(
      1,
      Math.floor((width - MARGIN * 2 + CHIP_GAP) / (CHIP_W + CHIP_GAP))
    );

    const chips = model.delegated
      .map((bin, index) => {
        const loaded = state.loadedBins.get(bin.name);
        const band = loaded ? loaded.band : 'unknown';
        const x = MARGIN + (index % perRow) * (CHIP_W + CHIP_GAP);
        const y = top + Math.floor(index / perRow) * (CHIP_H + CHIP_GAP);
        const selected = bin.name === state.selected ? ' is-selected' : '';
        return `
        <g class="gchip${selected}" data-node="${esc(bin.name)}"
           transform="translate(${x},${y})">
          <rect width="${CHIP_W}" height="${CHIP_H}" rx="4"></rect>
          <circle class="gnode__dot gnode__dot--${esc(band)}"
                  cx="12" cy="15" r="3.5"></circle>
          <text class="gchip__name" x="24" y="19">${esc(bin.name)}</text>
        </g>`;
      })
      .join('');

    const rows = Math.ceil(model.delegated.length / perRow);
    return { chips, height: rows * (CHIP_H + CHIP_GAP) };
  }

  function renderTree(overview) {
    const tree = $('tree');
    const model = treeModel(overview);

    if (!model.roles.size) {
      tree.innerHTML = '<p class="muted">Nothing verified to draw.</p>';
      return;
    }

    const { nodes, width, height } = layout(model);
    const byName = new Map(nodes.map((n) => [n.name, n]));

    let edges = '';
    model.children.forEach((kids, parent) => {
      const from = byName.get(parent);
      kids.forEach((kid) => {
        const to = byName.get(kid);
        if (from && to) edges += `<path d="${edgePath(from, to)}"/>`;
      });
    });

    let total = height;
    let chips = '';
    const group = byName.get(GROUP);

    if (state.binsOpen && group) {
      const bandTop = height + 8;
      const drawn = binBand(model, bandTop, width);
      edges += `<path d="${edgePath(group, {
        x: group.x,
        y: bandTop,
      })}"/>`;
      chips = drawn.chips;
      total = bandTop + drawn.height;
    }

    tree.innerHTML = `
      <svg class="graph" viewBox="0 0 ${width} ${total}"
           width="${width}" height="${total}"
           role="img" aria-label="Delegation tree">
        <g class="graph__edges">${edges}</g>
        <g class="graph__nodes">
          ${nodes.map((n) => nodeSvg(n, model)).join('')}
          ${chips}
        </g>
      </svg>`;

    tree.querySelectorAll('[data-node]').forEach((el) => {
      el.addEventListener('click', () => {
        if (el.dataset.node === GROUP) {
          state.binsOpen = !state.binsOpen;
          renderTree(state.overview);
          return;
        }
        select(el.dataset.node);
      });
    });
  }

  /* ---------------- detail ---------------- */

  // The same role can be drawn in the table and in the graph, so selecting
  // it marks every element that stands for it.
  function markSelected(name) {
    document
      .querySelectorAll('.is-selected')
      .forEach((el) => el.classList.remove('is-selected'));
    const chosen = CSS.escape(name);
    document
      .querySelectorAll(`[data-role="${chosen}"], [data-node="${chosen}"]`)
      .forEach((el) => el.classList.add('is-selected'));
  }

  async function select(name) {
    state.selected = name;
    markSelected(name);

    $('detail').innerHTML = `<p class="muted">Loading ${esc(name)}…</p>`;

    try {
      const detail = await window.Api.role(name);
      // A slow answer for a role the reader has already moved on from must
      // not overwrite what they are looking at now.
      if (state.selected !== name) return;
      state.loadedBins.set(name, detail);
      renderDetail(detail);
      // Redrawing the graph replaced its elements, so mark the choice again.
      renderTree(state.overview);
      markSelected(name);
    } catch (err) {
      if (state.selected !== name) return;
      $('detail').innerHTML =
        `<h3>${esc(name)}</h3>` +
        `<p class="state state--invalid">${esc(err.message)}</p>`;
    }
  }

  function renderDetail(d) {
    const field = (label, value) =>
      `<div class="field"><span class="field__label">${label}</span>` +
      `<span class="field__value">${value}</span></div>`;

    let html = `<h3>${esc(d.name)}</h3>`;
    html += `<div class="detail__sub">version ${d.version}</div>`;

    html += field(
      'Status',
      `<span class="state state--${esc(d.status)}">${esc(d.status)}</span>`
    );
    html += field(
      'Expiry',
      `<span class="state state--${esc(d.band)}">${esc(d.expires_in)}</span>`
    );
    if (d.threshold != null) {
      const present =
        d.signatures_present != null ? `${d.signatures_present} of ` : '';
      html += field('Signatures', `${present}${d.threshold} required`);
    }
    if (d.signed_by && d.signed_by.length) {
      html += field('Signed by', d.signed_by.map(keyChip).join(''));
    }
    if (d.signature_note) {
      html += `<p class="state state--invalid" style="margin-top:.6rem">${esc(
        d.signature_note
      )}</p>`;
    }
    if (d.delegates_to && d.delegates_to.length) {
      html += field('Delegates to', `${d.delegates_to.length} roles`);
    }
    if (d.raw_url) {
      // Served by this service, not by the storage, so what opens is the
      // document that was checked rather than a fresh unverified fetch.
      html += field(
        'Signed file',
        `<a href="${esc(d.raw_url)}" download="${esc(d.name)}.json">${esc(
          d.name
        )}.json</a>`
      );
    }

    if (d.artifacts && d.artifacts.length) {
      html += '<h2 class="section-title">Artifacts</h2>';
      html +=
        '<table class="table"><tbody>' +
        d.artifacts
          .map(
            (a) =>
              `<tr><td>${esc(a.path)}</td>` +
              `<td class="muted">${size(a.length)}</td></tr>`
          )
          .join('') +
        '</tbody></table>';
    }

    $('detail').innerHTML = html;
  }

  /* ---------------- artifacts ---------------- */

  function renderPager(data) {
    const pager = $('artifact-pager');
    const shown = data.artifacts.length;

    if (!data.total) {
      $('artifact-count').textContent = 'none';
      pager.hidden = true;
      return;
    }

    // Say which slice this is. A bare total beside fifty rows reads as if
    // fifty were all there was.
    const first = (data.page - 1) * data.page_size + 1;
    $('artifact-count').textContent =
      `showing ${first}–${first + shown - 1} of ${data.total}`;

    const pages = Math.ceil(data.total / data.page_size);
    pager.hidden = pages < 2;
    $('artifact-prev').disabled = data.page <= 1;
    $('artifact-next').disabled = data.page >= pages;
  }

  // Delegated roles are siblings, so one that cannot be read costs only its
  // own artifacts. Saying which ones is the difference between a short list
  // and a short list nobody can account for.
  function renderShortfall(missing) {
    const note = $('artifact-shortfall');

    if (!missing.length) {
      note.hidden = true;
      return;
    }

    note.innerHTML =
      `<strong>Incomplete.</strong> ${missing.length} delegated ` +
      `${missing.length === 1 ? 'role' : 'roles'} could not be read, so ` +
      'whatever they list is missing from this page and from the count: ' +
      missing.map((name) => esc(name)).join(', ');
    note.hidden = false;
  }

  async function loadArtifacts() {
    const body = $('artifacts-body');
    const requested = state.artifactPage;
    body.innerHTML = '<tr><td colspan="4" class="muted">Loading…</td></tr>';

    try {
      const data = await window.Api.artifacts(
        state.artifactSearch,
        requested
      );
      // A slower answer for a page the reader has already left must not
      // overwrite the one in front of them.
      if (state.artifactPage !== requested) return;

      renderPager(data);
      renderShortfall(data.unavailable || []);

      if (!data.artifacts.length) {
        body.innerHTML =
          '<tr><td colspan="4" class="muted">Nothing matched.</td></tr>';
        return;
      }

      body.innerHTML = data.artifacts
        .map((a) => {
          const digest = a.hashes.sha256 || Object.values(a.hashes)[0] || '';
          return `
          <tr>
            <td>${esc(a.path)}</td>
            <td class="muted">${esc(a.role)}</td>
            <td class="muted">${size(a.length)}</td>
            <td class="mono muted">${esc(digest.slice(0, 16))}…</td>
          </tr>`;
        })
        .join('');
    } catch (err) {
      $('artifact-pager').hidden = true;
      $('artifact-shortfall').hidden = true;
      body.innerHTML = `<tr><td colspan="4" class="state state--invalid">${esc(
        err.message
      )}</td></tr>`;
    }
  }

  function goToPage(page) {
    state.artifactPage = Math.max(1, page);
    loadArtifacts();
  }

  /* ---------------- root history ---------------- */

  function checkLine(label, check) {
    if (!check) return '';
    const cls = check.verified ? 'valid' : 'invalid';
    return (
      `<div class="rootcheck state state--${cls}">${label}: ` +
      `${check.present} of ${check.threshold} required</div>`
    );
  }

  function keyDiff(changes) {
    if (!changes.length) return '';
    return (
      '<div class="rootdiff">' +
      changes
        .map((c) => {
          const added = c.action === 'added';
          return (
            `<span class="chg chg--${esc(c.action)}">` +
            `${added ? '+' : '−'} ${esc(c.name)}` +
            `<span class="mono muted"> ${esc(c.keyid_short)}</span></span>`
          );
        })
        .join('') +
      '</div>'
    );
  }

  function roleDiff(changes) {
    if (!changes.length) return '';

    const moved = (before, after) =>
      before === after
        ? `${after ?? '—'}`
        : `${before ?? '—'} &rarr; <strong>${after ?? '—'}</strong>`;

    return (
      '<table class="table rootroles"><thead><tr>' +
      '<th>Role</th><th>Signatures required</th><th>Signers</th>' +
      '</tr></thead><tbody>' +
      changes
        .map((c) => {
          const signers = []
            .concat(
              c.signers_added.map(
                (n) => `<span class="chg chg--added">+ ${esc(n)}</span>`
              )
            )
            .concat(
              c.signers_removed.map(
                (n) => `<span class="chg chg--removed">− ${esc(n)}</span>`
              )
            );
          return (
            `<tr><td>${esc(c.role)}</td>` +
            `<td class="muted">${moved(
              c.threshold_before,
              c.threshold_after
            )}</td>` +
            `<td>${signers.join(' ') || '<span class="muted">—</span>'}</td>` +
            '</tr>'
          );
        })
        .join('') +
      '</tbody></table>'
    );
  }

  function rootCard(version, isOldest) {
    const failed = !version.verified;
    const tag = version.superseded
      ? '<span class="muted">superseded</span>'
      : '<span class="chip chip--current">in force</span>';

    let html = `<article class="rootcard ${failed ? 'is-broken' : ''}">`;
    html +=
      '<header class="rootcard__head">' +
      `<span class="rootcard__ver">Version ${version.version}</span>${tag}` +
      `<span class="rootcard__when ${
        version.band ? `state state--${esc(version.band)}` : 'muted'
      }">${esc(version.expires_in)}</span>` +
      '</header>';

    html += checkLine('Signed by its own keys', version.by_own_keys);
    html += checkLine(
      `Authorised by version ${version.version - 1}`,
      version.by_previous_keys
    );
    if (!version.by_previous_keys) {
      html +=
        '<div class="rootcheck muted">' +
        (version.version === 1
          ? 'The first version. Nothing precedes it to vouch for it.'
          : 'The version before this one was not read.') +
        '</div>';
    }
    if (version.note) {
      html += `<p class="state state--invalid rootnote">${esc(
        version.note
      )}</p>`;
    }

    const changed =
      version.keys_changed.length || version.roles_changed.length;
    if (changed) {
      html += '<div class="rootcard__body">';
      html += keyDiff(version.keys_changed);
      html += roleDiff(version.roles_changed);
      html += '</div>';
    } else if (!isOldest) {
      // The oldest card has nothing behind it to be compared against, so
      // saying "nothing changed" there would claim more than was checked.
      html +=
        '<p class="muted rootnote">Nothing changed against the version ' +
        'before it.</p>';
    }

    return `${html}</article>`;
  }

  async function loadRoots() {
    const body = $('roots-body');
    body.innerHTML = '<p class="muted">Loading…</p>';

    try {
      const data = await window.Api.roots();

      let html = '';
      if (data.message) {
        html += `<div class="banner banner--info">${esc(data.message)}</div>`;
      }
      const last = data.versions.length - 1;
      html +=
        '<div class="rootlist">' +
        data.versions.map((v, i) => rootCard(v, i === last)).join('') +
        '</div>';
      body.innerHTML = html;
    } catch (err) {
      body.innerHTML = `<p class="state state--invalid">${esc(
        err.message
      )}</p>`;
    }
  }

  /* ---------------- status ---------------- */

  async function loadStatus() {
    const body = $('status-body');
    body.innerHTML = '<p class="muted">Loading…</p>';

    try {
      const s = await window.Api.status();

      if (!s.available) {
        body.innerHTML =
          '<div class="banner banner--info"><strong>Status unavailable.</strong> ' +
          `${esc(s.message || 'The RSTUF API could not be reached.')} ` +
          'The metadata above is unaffected: it comes from the signed files, ' +
          'not from the API.</div>';
        return;
      }

      let html = `<div class="banner banner--info"><strong>${esc(
        s.state.replace(/_/g, ' ')
      )}</strong>`;
      if (s.awaiting_signatures && s.awaiting_signatures.length) {
        html += ` · awaiting signatures: ${s.awaiting_signatures
          .map((r) => esc(r))
          .join(', ')}`;
      }
      html += '</div>';

      if (s.keys && s.keys.length) {
        html += '<h2 class="section-title">Signing keys</h2>';
        html +=
          '<table class="table"><thead><tr><th>Key</th><th>Signs</th>' +
          '<th>Held</th></tr></thead><tbody>' +
          s.keys
            .map(
              (k) =>
                `<tr><td>${keyChip(k)}</td>` +
                `<td class="muted">${(k.signs || []).join(', ') || '—'}</td>` +
                `<td class="muted">${k.online ? 'online' : 'offline'}</td>` +
                '</tr>'
            )
            .join('') +
          '</tbody></table>';
        html +=
          '<p class="note">Root is protected by keys held offline; the ' +
          'online key signs everything renewed automatically. That split is ' +
          'the security model, and raw metadata hides it.</p>';
      }

      body.innerHTML = html;
    } catch (err) {
      body.innerHTML = `<p class="state state--invalid">${esc(
        err.message
      )}</p>`;
    }
  }

  /* ---------------- page ---------------- */

  async function loadOverview(refresh) {
    try {
      const overview = await window.Api.overview(refresh);
      state.overview = overview;
      state.loadedBins.clear();
      renderHealth(overview);
      renderBanner(overview);
      renderRoles(overview);
      renderTree(overview);
    } catch (err) {
      $('health-badge').className = 'badge badge--invalid';
      $('health-label').textContent = 'Unreachable';
      const banner = $('banner');
      banner.className = 'banner';
      banner.innerHTML = `<strong>Cannot load.</strong> ${esc(err.message)}`;
      banner.hidden = false;
      $('roles-body').innerHTML =
        '<tr><td colspan="5" class="muted">—</td></tr>';
    }
  }

  function wireTabs() {
    document.querySelectorAll('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document
          .querySelectorAll('.tab')
          .forEach((t) => t.classList.remove('is-active'));
        document
          .querySelectorAll('.panel')
          .forEach((p) => p.classList.remove('is-active'));
        tab.classList.add('is-active');
        $(`tab-${tab.dataset.tab}`).classList.add('is-active');

        // Each tab pays for its own data, and only once it is opened.
        if (tab.dataset.tab === 'artifacts' && !state.artifactsLoaded) {
          state.artifactsLoaded = true;
          loadArtifacts();
        }
        if (tab.dataset.tab === 'status' && !state.statusLoaded) {
          state.statusLoaded = true;
          loadStatus();
        }
        if (tab.dataset.tab === 'roots' && !state.rootsLoaded) {
          state.rootsLoaded = true;
          loadRoots();
        }
      });
    });
  }

  function wireRefresh() {
    const btn = $('refresh-btn');
    btn.addEventListener('click', async () => {
      btn.classList.add('is-busy');
      btn.disabled = true;
      state.artifactsLoaded = false;
      // The repository was read again, so a page number from the old result
      // may no longer exist. The search term is the reader's, so it stays.
      state.artifactPage = 1;
      state.statusLoaded = false;
      state.rootsLoaded = false;
      await loadOverview(true);
      btn.classList.remove('is-busy');
      btn.disabled = false;
    });
  }

  function wireArtifacts() {
    let timer = null;
    $('artifact-search').addEventListener('input', (event) => {
      clearTimeout(timer);
      const term = event.target.value;
      timer = setTimeout(() => {
        state.artifactSearch = term;
        // A narrower search has fewer pages, so page four of the old result
        // is not a place the new one has.
        goToPage(1);
      }, 250);
    });

    $('artifact-prev').addEventListener('click', () =>
      goToPage(state.artifactPage - 1)
    );
    $('artifact-next').addEventListener('click', () =>
      goToPage(state.artifactPage + 1)
    );
  }

  document.addEventListener('DOMContentLoaded', () => {
    wireTabs();
    wireRefresh();
    wireArtifacts();
    loadOverview(false);

    // The age of the answer is only honest if it keeps counting. Nothing is
    // fetched here; the label is redrawn from the reading already in hand.
    setInterval(renderCheckedAt, 10000);
  });
})();
