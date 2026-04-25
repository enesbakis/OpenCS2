/* ── Dashboard auto-refresh (every 15 seconds) ─────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  if (document.getElementById('playerTbody') || document.getElementById('livePlayerCount')) {
    refreshStatus();
    setInterval(refreshStatus, 15000);
  }
});

/* ── Live status refresh ─────────────────────────────────────────────────── */
function refreshStatus() {
  fetch('/api/status')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      // Topbar pill
      const topbarDot = document.getElementById('topbarDot');
      const topbarMap = document.getElementById('topbarMap');
      if (data.online) {
        if (topbarDot) { topbarDot.className = 'dot-online'; }
        if (topbarMap) topbarMap.textContent = data.map || 'Online';

        const host = document.getElementById('liveHostname');
        if (host) host.textContent = data.hostname;

        const mapEl = document.getElementById('liveMap');
        if (mapEl) mapEl.textContent = data.map;

        const nextEl = document.getElementById('liveNextMap');
        if (nextEl) nextEl.textContent = data.next_map;

        const cntEl = document.getElementById('livePlayerCount');
        if (cntEl) cntEl.textContent = data.player_count;

        const maxEl = document.getElementById('liveMaxPlayers');
        if (maxEl && data.max_players) maxEl.textContent = data.max_players;

        const badgeEl = document.getElementById('liveBadge');
        if (badgeEl) badgeEl.textContent = data.player_count + ' oyuncu';

        renderPlayers(data.players);
      } else {
        if (topbarDot) { topbarDot.className = 'dot-offline'; }
        if (topbarMap) topbarMap.textContent = 'Offline';
      }
    })
    .catch(function () { /* silently ignore */ });
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderPlayers(players) {
  const tbody = document.getElementById('playerTbody');
  if (!tbody) return;

  if (!players || players.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:2rem; color:#94a3b8;">Şu an sunucuda oyuncu yok</td></tr>';
    return;
  }

  let html = '';
  players.forEach(function (p) {
    const ping = parseInt(p.ping, 10);
    const pingBadge = ping < 80
      ? '<span class="badge-ping-good">' + escHtml(p.ping) + 'ms</span>'
      : ping < 150
        ? '<span class="badge-ping-med">' + escHtml(p.ping) + 'ms</span>'
        : '<span class="badge-ping-bad">' + escHtml(p.ping) + 'ms</span>';

    html += '<tr>' +
      '<td><span class="badge-neutral">' + escHtml(p.userid) + '</span></td>' +
      '<td><strong>' + escHtml(p.name) + '</strong></td>' +
      '<td style="font-size:0.75rem;color:#94a3b8;">' + escHtml(p.steamid) + '</td>' +
      '<td>' + pingBadge + '</td>' +
      '<td>' +
        '<form method="POST" action="/player_action" class="d-inline">' +
          '<input type="hidden" name="userid" value="' + escHtml(p.userid) + '">' +
          '<input type="hidden" name="playername" value="' + escHtml(p.name) + '">' +
          '<button type="submit" name="action" value="kick" class="btn-action kick"><i class="fa-solid fa-shoe-prints"></i> Kick</button>' +
          '<button type="button" class="btn-action ban" data-bs-toggle="modal" data-bs-target="#banModal"' +
            ' data-userid="' + escHtml(p.userid) + '" data-name="' + escHtml(p.name) + '">' +
            '<i class="fa-solid fa-ban"></i> Ban</button>' +
          '<button type="submit" name="action" value="slay" class="btn-action slay"><i class="fa-solid fa-skull"></i> Slay</button>' +
        '</form>' +
      '</td></tr>';
  });
  tbody.innerHTML = html;
}
