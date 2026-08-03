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
    statusLoaded: false,
    rootsLoaded: false,
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

  const BAND_RANK = { expired: 0, critical: 1, expiring: 2, valid: 3 };
  const BAND_LABEL = {
    expired: 'Expired',
    critical: 'Expires within a day',
    expiring: 'Expiring soon',
    valid: 'All healthy',
  };

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

  function renderHealth(overview) {
    const badge = $('health-badge');
    const label = $('health-label');

    if (overview.status === 'invalid') {
      badge.className = 'badge badge--invalid';
      label.textContent = 'Verification failed';
    } else {
      const worst = (overview.roles || []).reduce(
        (acc, role) =>
          BAND_RANK[role.band] < BAND_RANK[acc] ? role.band : acc,
        'valid'
      );
      badge.className = `badge badge--${worst}`;
      label.textContent = BAND_LABEL[worst] || 'Unknown';
    }

    if (overview.checked_at) {
      const when = new Date(overview.checked_at);
      $('checked-at').textContent = `checked ${when.toLocaleTimeString()}`;
    }
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

  /* ---------------- tree ---------------- */

  function renderTree(overview) {
    const tree = $('tree');
    const roles = new Map((overview.roles || []).map((r) => [r.name, r]));
    const delegated = overview.delegated || [];

    if (!roles.size) {
      tree.innerHTML = '<p class="muted">Nothing verified to draw.</p>';
      return;
    }

    const node = (role, cls) => `
      <div class="tnode ${cls}" data-role="${esc(role.name)}">
        <span class="state state--${esc(role.band)}"></span>
        <span class="tnode__name">${esc(role.name)}</span>
        <span class="tnode__meta">v${role.version} · ${esc(
          role.expires_in
        )}</span>
      </div>`;

    let html = '';
    if (roles.has('root')) html += node(roles.get('root'), '');
    ['timestamp', 'snapshot', 'targets'].forEach((name) => {
      if (roles.has(name)) html += node(roles.get(name), 'tnode--child');
    });

    if (delegated.length) {
      const caret = state.binsOpen ? 'is-open' : '';
      html += `
        <div class="tnode tnode--child" id="bins-toggle">
          <span class="tnode__caret ${caret}">&#9654;</span>
          <span class="tnode__name">${delegated.length} delegated
            ${delegated.length === 1 ? 'role' : 'roles'}</span>
          <span class="tnode__meta">${
            state.binsOpen ? 'click a role to load it' : 'collapsed'
          }</span>
        </div>`;

      if (state.binsOpen) {
        html += delegated
          .map((bin) => {
            const loaded = state.loadedBins.get(bin.name);
            const meta = loaded
              ? `v${loaded.version} · ${esc(loaded.expires_in)}`
              : 'not loaded';
            const band = loaded ? loaded.band : 'unknown';
            return `
            <div class="tnode tnode--bin" data-role="${esc(bin.name)}">
              <span class="state state--${esc(band)}"></span>
              <span class="tnode__name">${esc(bin.name)}</span>
              <span class="tnode__meta">${meta}</span>
            </div>`;
          })
          .join('');
      }
    }

    tree.innerHTML = html;

    const toggle = $('bins-toggle');
    if (toggle) {
      toggle.addEventListener('click', () => {
        state.binsOpen = !state.binsOpen;
        renderTree(state.overview);
      });
    }

    tree.querySelectorAll('.tnode[data-role]').forEach((el) => {
      el.addEventListener('click', () => select(el.dataset.role));
      if (el.dataset.role === state.selected) {
        el.classList.add('is-selected');
      }
    });
  }

  /* ---------------- detail ---------------- */

  async function select(name) {
    state.selected = name;
    document
      .querySelectorAll('.tnode.is-selected, tr.is-selected')
      .forEach((el) => el.classList.remove('is-selected'));
    document
      .querySelectorAll(`[data-role="${CSS.escape(name)}"]`)
      .forEach((el) => el.classList.add('is-selected'));

    $('detail').innerHTML = `<p class="muted">Loading ${esc(name)}…</p>`;

    try {
      const detail = await window.Api.role(name);
      // A slow answer for a role the reader has already moved on from must
      // not overwrite what they are looking at now.
      if (state.selected !== name) return;
      state.loadedBins.set(name, detail);
      renderDetail(detail);
      renderTree(state.overview);
      document
        .querySelectorAll(`[data-role="${CSS.escape(name)}"]`)
        .forEach((el) => el.classList.add('is-selected'));
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

  async function loadArtifacts(search) {
    const body = $('artifacts-body');
    body.innerHTML = '<tr><td colspan="4" class="muted">Loading…</td></tr>';

    try {
      const data = await window.Api.artifacts(search);
      $('artifact-count').textContent = `${data.total} total`;

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
      body.innerHTML = `<tr><td colspan="4" class="state state--invalid">${esc(
        err.message
      )}</td></tr>`;
    }
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
          loadArtifacts('');
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
      state.statusLoaded = false;
      state.rootsLoaded = false;
      await loadOverview(true);
      btn.classList.remove('is-busy');
      btn.disabled = false;
    });
  }

  function wireSearch() {
    let timer = null;
    $('artifact-search').addEventListener('input', (event) => {
      clearTimeout(timer);
      const term = event.target.value;
      timer = setTimeout(() => loadArtifacts(term), 250);
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    wireTabs();
    wireRefresh();
    wireSearch();
    loadOverview(false);
  });
})();
