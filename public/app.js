'use strict';

// ── State ──────────────────────────────────────────────────────────────────
const S = {
  user: null,
  matchDays: [],       // [{match_date, total, settled_count}]
  currentDate: null,
  dayData: null,       // {date, matches, players, predictions}
  adminMatchId: null,
};

// ── API ────────────────────────────────────────────────────────────────────
async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || '请求失败');
  return data;
}

// ── Toast ──────────────────────────────────────────────────────────────────
let toastTimer;
function toast(msg, type = 'success') {
  clearTimeout(toastTimer);
  const old = document.querySelector('.toast');
  if (old) old.remove();
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  toastTimer = setTimeout(() => el.remove(), 2800);
}

// ── Login / Logout ─────────────────────────────────────────────────────────
document.getElementById('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  const errEl = document.getElementById('login-error');
  errEl.textContent = '';
  try {
    const { user } = await api('/api/login', {
      method: 'POST',
      body: JSON.stringify({ name: document.getElementById('inp-name').value.trim() }),
    });
    S.user = user;
    showApp();
  } catch (err) {
    errEl.textContent = err.message;
  }
});

async function logout() {
  await api('/api/logout', { method: 'POST' });
  S.user = null;
  S.currentDate = null;
  S.dayData = null;
  document.getElementById('app').classList.add('hidden');
  document.getElementById('login-overlay').classList.remove('hidden');
  document.getElementById('inp-name').value = '';
}

// ── Init ───────────────────────────────────────────────────────────────────
async function init() {
  try {
    const { user } = await api('/api/me');
    if (user) {
      S.user = user;
      showApp();
    }
  } catch (_) {}
}

async function showApp() {
  document.getElementById('login-overlay').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  document.getElementById('header-username').textContent = S.user.display_name;

  await Promise.all([loadStandings(), loadMatchDays()]);
  await loadCurrentDay();
}

// ── Standings ──────────────────────────────────────────────────────────────
async function loadStandings() {
  try {
    const { standings } = await api('/api/standings');
    const bar = document.getElementById('standings-bar');
    bar.innerHTML = standings.map((s, i) => `
      <div class="standing-chip rank${i + 1}">
        <span class="rank">#${i + 1}</span>
        <span class="name">${s.display_name}</span>
        <span class="pts">${s.total_points}分</span>
      </div>
    `).join('');
  } catch (_) {}
}

// ── Match Days ─────────────────────────────────────────────────────────────
async function loadMatchDays() {
  try {
    const { days } = await api('/api/match-days');
    S.matchDays = days;
  } catch (_) {}
}

function currentDayIndex() {
  return S.matchDays.findIndex(d => d.match_date === S.currentDate);
}

function updateNavButtons() {
  const idx = currentDayIndex();
  document.getElementById('btn-prev').disabled = idx <= 0;
  document.getElementById('btn-next').disabled = idx < 0 || idx >= S.matchDays.length - 1;
}

function formatDateLabel(dateStr) {
  const d = new Date(dateStr + 'T12:00:00');
  const month = d.getMonth() + 1;
  const day = d.getDate();
  const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
  const wd = weekdays[d.getDay()];
  const idx = S.matchDays.findIndex(x => x.match_date === dateStr);
  const dayNum = idx >= 0 ? `第${idx + 1}比赛日` : '';
  return `${month}月${day}日（周${wd}）${dayNum}`;
}

function prevDay() {
  const idx = currentDayIndex();
  if (idx > 0) loadDay(S.matchDays[idx - 1].match_date);
}

function nextDay() {
  const idx = currentDayIndex();
  if (idx < S.matchDays.length - 1) loadDay(S.matchDays[idx + 1].match_date);
}

async function goToCurrentDay() {
  try {
    const data = await api('/api/current-day');
    S.dayData = data;
    S.currentDate = data.date;
    updateNavButtons();
    document.getElementById('day-label').textContent = formatDateLabel(data.date);
    renderDay(data);
  } catch (_) {}
}

// ── Load Day Data ──────────────────────────────────────────────────────────
async function loadCurrentDay() {
  try {
    const data = await api('/api/current-day');
    S.dayData = data;
    S.currentDate = data.date;
    updateNavButtons();
    document.getElementById('day-label').textContent = formatDateLabel(data.date);
    renderDay(data);
  } catch (_) {}
}

async function loadDay(date) {
  try {
    S.currentDate = date;
    updateNavButtons();
    document.getElementById('day-label').textContent = formatDateLabel(date);
    document.getElementById('match-list').innerHTML = '<div class="loading">加载中...</div>';
    document.getElementById('pred-tbody').innerHTML = '<tr><td colspan="6"><div class="loading">加载中...</div></td></tr>';
    const data = await api(`/api/day/${date}`);
    S.dayData = data;
    renderDay(data);
  } catch (_) {}
}

// ── Render Day ─────────────────────────────────────────────────────────────
function renderDay(data) {
  renderMatchList(data);
  renderPredTable(data);
}

function renderMatchList(data) {
  const { matches } = data;
  const el = document.getElementById('match-list');

  if (!matches.length) {
    el.innerHTML = '<div class="empty-day">本日无比赛</div>';
    return;
  }

  el.innerHTML = matches.map(m => {
    const hasResult = m.home_score !== null;
    const resultHtml = hasResult
      ? `<span class="match-card-result">${m.home_score} - ${m.away_score}</span>`
      : '';
    const badge = m.settled
      ? '<span class="badge-settled">已结算</span>'
      : (hasResult ? '<span class="badge-settled" style="color:#f59e0b;border-color:#f59e0b">已出结果</span>' : '');
    const adminBtn = S.user
      ? `<button class="admin-btn" onclick="openAdminModal(${m.id}, event)">录入</button>`
      : '';

    return `
      <div class="match-card ${m.settled ? 'settled' : ''}" data-id="${m.id}" onclick="highlightMatch(${m.id})">
        ${adminBtn}
        <div class="match-card-group">${m.group_name}</div>
        <div class="match-card-teams">
          ${m.home_team}<br>${m.away_team}
        </div>
        <div class="match-card-time">
          <span class="match-card-clock">⏰ ${m.match_time}</span>
          ${resultHtml || badge}
        </div>
      </div>
    `;
  }).join('');
}

// ── Mobile Tab Switch ──────────────────────────────────────────────────────
function switchTab(tab) {
  const matchPanel = document.getElementById('match-panel');
  const predPanel  = document.querySelector('.pred-panel');
  const tabMatch   = document.getElementById('tab-match');
  const tabPred    = document.getElementById('tab-pred');
  if (tab === 'match') {
    matchPanel.classList.remove('mobile-hidden');
    predPanel.classList.add('mobile-hidden');
    tabMatch.classList.add('active');
    tabPred.classList.remove('active');
  } else {
    matchPanel.classList.add('mobile-hidden');
    predPanel.classList.remove('mobile-hidden');
    tabPred.classList.add('active');
    tabMatch.classList.remove('active');
  }
}

function isMobile() { return window.innerWidth <= 768; }

function highlightMatch(matchId) {
  document.querySelectorAll('.match-card').forEach(c => c.classList.remove('active'));
  const card = document.querySelector(`.match-card[data-id="${matchId}"]`);
  if (card) card.classList.add('active');
  // on mobile: switch to pred tab first, then scroll to row
  if (isMobile()) {
    switchTab('pred');
    setTimeout(() => {
      const row = document.querySelector(`tr[data-match-id="${matchId}"]`);
      if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 50);
  } else {
    const row = document.querySelector(`tr[data-match-id="${matchId}"]`);
    if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

function renderPredTable(data) {
  const { matches, players, predictions } = data;

  // Build prediction lookup: predMap[match_id][user_id] = prediction
  const predMap = {};
  for (const p of predictions) {
    if (!predMap[p.match_id]) predMap[p.match_id] = {};
    predMap[p.match_id][p.user_id] = p;
  }

  // thead
  const thead = document.getElementById('pred-thead');
  thead.innerHTML = `
    <tr>
      <th class="th-match">比赛</th>
      ${players.map(p => `
        <th style="${p.id === S.user?.id ? 'color: var(--gold)' : ''}">${p.display_name}${p.id === S.user?.id ? ' 👤' : ''}</th>
      `).join('')}
    </tr>
  `;

  if (!matches.length) {
    document.getElementById('pred-tbody').innerHTML =
      `<tr><td colspan="${players.length + 1}"><div class="empty-day">本日无比赛</div></td></tr>`;
    return;
  }

  // group matches by group_name
  const groups = {};
  for (const m of matches) {
    const g = m.group_name || '其他';
    if (!groups[g]) groups[g] = [];
    groups[g].push(m);
  }

  const rows = [];
  for (const [group, gMatches] of Object.entries(groups)) {
    // group header row
    rows.push(`
      <tr class="group-header-row">
        <td colspan="${players.length + 1}">${group}</td>
      </tr>
    `);

    for (const m of gMatches) {
      const hasResult = m.home_score !== null;
      const resultText = hasResult ? `${m.home_score} : ${m.away_score}` : '待定';

      const matchCell = `
        <td class="td-match">
          <div class="td-match-inner">
            <div class="td-match-teams">${m.home_team} vs ${m.away_team}</div>
            <div class="td-match-meta">${m.match_time} · ${m.group_name}</div>
            ${hasResult ? `<div class="td-match-result">${m.home_score} - ${m.away_score} ${m.settled ? '✓' : ''}</div>` : ''}
          </div>
        </td>
      `;

      const predCells = players.map(player => {
        const pred = predMap[m.id]?.[player.id];
        const isMe = player.id === S.user?.id;
        const canEdit = isMe && !m.settled;

        if (canEdit) {
          const curH = pred ? pred.pred_home : '';
          const curA = pred ? pred.pred_away : '';
          return `
            <td class="pred-cell">
              <div class="pred-editable">
                <input type="number" class="pred-inp" id="inp-h-${m.id}" value="${curH}" min="0" max="30" placeholder="0"
                  onkeydown="handlePredKey(event,${m.id})">
                <span class="pred-sep">:</span>
                <input type="number" class="pred-inp" id="inp-a-${m.id}" value="${curA}" min="0" max="30" placeholder="0"
                  onkeydown="handlePredKey(event,${m.id})">
              </div>
              <button class="pred-save-btn" onclick="savePred(${m.id})">保存</button>
            </td>
          `;
        }

        if (!pred) {
          return `<td class="pred-cell"><span class="pred-empty">—</span></td>`;
        }

        const scoreText = `${pred.pred_home}:${pred.pred_away}`;

        if (!hasResult) {
          return `<td class="pred-cell"><span class="pred-score">${scoreText}</span></td>`;
        }

        // settled / has result
        const pts = pred.points;
        let cls = '', badge = '', badgeCls = '';
        if (pts === 3)      { cls = 'pts-3'; badge = '+3 完美预测'; badgeCls = 'b3'; }
        else if (pts === 1) { cls = 'pts-1'; badge = '+1 结果正确'; badgeCls = 'b1'; }
        else if (pts === 0) { cls = 'pts-0'; badge = '+0'; badgeCls = 'b0'; }
        else                { cls = ''; badge = '待结算'; badgeCls = ''; }

        return `
          <td class="pred-cell">
            <span class="pred-score ${cls}">${scoreText}</span>
            ${badge ? `<span class="pts-badge ${badgeCls}">${badge}</span>` : ''}
          </td>
        `;
      }).join('');

      rows.push(`<tr data-match-id="${m.id}">${matchCell}${predCells}</tr>`);
    }
  }

  document.getElementById('pred-tbody').innerHTML = rows.join('');
}

// ── Predict ────────────────────────────────────────────────────────────────
function handlePredKey(e, matchId) {
  if (e.key === 'Enter') savePred(matchId);
}

async function savePred(matchId) {
  const hInp = document.getElementById(`inp-h-${matchId}`);
  const aInp = document.getElementById(`inp-a-${matchId}`);
  if (!hInp || !aInp) return;
  const h = hInp.value.trim();
  const a = aInp.value.trim();
  if (h === '' || a === '') {
    toast('请填写主客队比分', 'error');
    return;
  }
  try {
    await api('/api/predict', {
      method: 'POST',
      body: JSON.stringify({ match_id: matchId, pred_home: parseInt(h), pred_away: parseInt(a) }),
    });
    toast('预测已保存 ✓');
    // reload day data silently
    const data = await api(`/api/day/${S.currentDate}`);
    S.dayData = data;
    renderDay(data);
    await loadStandings();
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── Admin ──────────────────────────────────────────────────────────────────
function openAdminModal(matchId, e) {
  e.stopPropagation();
  if (!S.user) return;
  const match = S.dayData?.matches.find(m => m.id === matchId);
  if (!match) return;
  S.adminMatchId = matchId;

  document.getElementById('modal-match-name').textContent =
    `${match.home_team} vs ${match.away_team}`;
  document.getElementById('modal-home-name').textContent = match.home_team;
  document.getElementById('modal-away-name').textContent = match.away_team;
  document.getElementById('modal-home-score').value = match.home_score ?? '';
  document.getElementById('modal-away-score').value = match.away_score ?? '';
  document.getElementById('admin-modal').classList.remove('hidden');
  document.getElementById('modal-home-score').focus();
}

function closeAdminModal() {
  document.getElementById('admin-modal').classList.add('hidden');
  S.adminMatchId = null;
}

async function submitResult() {
  const h = document.getElementById('modal-home-score').value.trim();
  const a = document.getElementById('modal-away-score').value.trim();
  if (h === '' || a === '') {
    toast('请填写比分', 'error');
    return;
  }
  try {
    await api('/api/admin/result', {
      method: 'POST',
      body: JSON.stringify({ match_id: S.adminMatchId, home_score: parseInt(h), away_score: parseInt(a) }),
    });
    toast('比赛结果已录入，积分已结算 ✓');
    closeAdminModal();
    const data = await api(`/api/day/${S.currentDate}`);
    S.dayData = data;
    renderDay(data);
    await Promise.all([loadStandings(), loadMatchDays()]);
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function clearResult() {
  if (!confirm('确认清除此场比赛结果？若已结算，将回滚积分。')) return;
  try {
    await api('/api/admin/clear-result', {
      method: 'POST',
      body: JSON.stringify({ match_id: S.adminMatchId }),
    });
    toast('结果已清除');
    closeAdminModal();
    const data = await api(`/api/day/${S.currentDate}`);
    S.dayData = data;
    renderDay(data);
    await Promise.all([loadStandings(), loadMatchDays()]);
  } catch (err) {
    toast(err.message, 'error');
  }
}

// close modal on backdrop click
document.getElementById('admin-modal').addEventListener('click', function(e) {
  if (e.target === this) closeAdminModal();
});

// Auto-refresh standings every 30 seconds
setInterval(loadStandings, 30000);

// ── Boot ───────────────────────────────────────────────────────────────────
init();
