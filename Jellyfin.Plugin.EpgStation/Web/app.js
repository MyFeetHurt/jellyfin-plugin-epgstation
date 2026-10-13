/* EPGStation for Jellyfin – user page. Talks only to the plugin API (../), with the user's
 * Jellyfin token from jellyfin-web's saved credentials (same origin). */
'use strict';

(function () {
  const API = '../';
  const TYPES = ['GR', 'BS', 'CS', 'SKY'];
  const HOUR = 3600 * 1000;
  const DAY = 24 * HOUR;

  // ---------- i18n ----------
  const STR = {
    en: {
      guide: 'Guide', search: 'Search', reserves: 'Scheduled', now: 'Now', keyword: 'Keyword',
      inDescription: 'Description too', filterActive: 'Scheduled', filterConflict: 'Conflicts', filterSkip: 'Skipped',
      reload: 'Reload', backToJellyfin: 'Back to Jellyfin', record: 'Record', cancel: 'Cancel recording',
      stop: 'Stop recording', unskip: 'Record again', close: 'Close', recording: 'Recording', scheduled: 'Scheduled',
      conflict: 'Conflict', skipped: 'Skipped', overlap: 'Duplicate', rule: 'Rule', by: 'by {0}',
      loading: 'Loading…', noResults: 'No programmes found.', noReserves: 'Nothing here.',
      scheduledOk: 'Scheduled: {0}', cancelledOk: 'Cancelled: {0}', stoppedOk: 'Stopped: {0}', unskippedOk: 'Will record: {0}',
      confirmCancel: 'Cancel the recording of “{0}”?', confirmStop: '“{0}” is recording now. Stop it? The part recorded so far is kept.',
      confirmSkip: '“{0}” was scheduled by a rule. Skip this airing? (The rule stays.)',
      notSignedIn: 'Sign in to Jellyfin first.', signIn: 'Sign in', notAllowed: 'Your Jellyfin account may not use EPGStation. Ask an administrator.',
      notConfigured: 'The EPGStation plugin is not set up yet. An administrator must enter the EPGStation URL in Dashboard → Plugins → EPGStation.',
      notConnected: 'EPGStation is not reachable: {0}', error: 'Error: {0}', ended: 'Ended', results: '{0} programmes',
      ruleHint: 'Scheduled by an EPGStation rule.', conflictHint: 'No free tuner: this will not record unless another recording is cancelled.',
      skipHint: 'Skipped: a rule matched this programme but it will not record.',
      overlapHint: 'Already recorded by another reservation.', recordingHint: 'Recording now.',
      today: 'Today', tomorrow: 'Tomorrow', min: '{0} min',
      'err.ReservationManageModelAddReserveConflict': 'No free tuner at that time: it conflicts with other recordings.',
      'err.ReservationManageModelCheckReservedProgramError': 'This programme is already scheduled.',
      'err.ReservationManageModelReservedError': 'This programme is already scheduled.',
      'err.ReservationIsNotFound': 'This reservation no longer exists.',
      'err.ProgramIsNotFound': 'This programme is no longer in the guide.',
      'err.IPCTimeout': 'EPGStation is busy. The change may still go through: reload in a moment.',
    },
    ja: {
      guide: '番組表', search: '検索', reserves: '予約', now: '現在', keyword: 'キーワード',
      inDescription: '概要も検索', filterActive: '予約', filterConflict: '競合', filterSkip: '除外',
      reload: '更新', backToJellyfin: 'Jellyfin に戻る', record: '録画予約', cancel: '予約を取り消す',
      stop: '録画を停止', unskip: '除外を解除', close: '閉じる', recording: '録画中', scheduled: '予約済み',
      conflict: '競合', skipped: '除外', overlap: '重複', rule: 'ルール', by: '{0} が予約',
      loading: '読み込み中…', noResults: '番組が見つかりません。', noReserves: 'ありません。',
      scheduledOk: '予約しました: {0}', cancelledOk: '取り消しました: {0}', stoppedOk: '停止しました: {0}', unskippedOk: '除外を解除しました: {0}',
      confirmCancel: '「{0}」の予約を取り消しますか？', confirmStop: '「{0}」は録画中です。停止しますか？ ここまでの録画は残ります。',
      confirmSkip: '「{0}」はルールによる予約です。この回を除外しますか？（ルールは残ります）',
      notSignedIn: '先に Jellyfin にサインインしてください。', signIn: 'サインイン', notAllowed: 'このアカウントでは EPGStation を使えません。管理者に連絡してください。',
      notConfigured: 'EPGStation プラグインが未設定です。管理者が ダッシュボード → プラグイン → EPGStation で URL を入力してください。',
      notConnected: 'EPGStation に接続できません: {0}', error: 'エラー: {0}', ended: '終了', results: '{0} 件',
      ruleHint: 'EPGStation のルールによる予約です。', conflictHint: 'チューナーが足りません。他の予約を取り消さないと録画されません。',
      skipHint: '除外: ルールに一致しましたが録画しません。',
      overlapHint: '他の予約で録画されるため重複しています。', recordingHint: '録画中です。',
      today: '今日', tomorrow: '明日', min: '{0}分',
      'err.ReservationManageModelAddReserveConflict': 'チューナーが足りません（他の予約と競合します）。',
      'err.ReservationManageModelCheckReservedProgramError': 'この番組はすでに予約されています。',
      'err.ReservationManageModelReservedError': 'この番組はすでに予約されています。',
      'err.ReservationIsNotFound': 'この予約はもうありません。',
      'err.ProgramIsNotFound': 'この番組は番組表にありません。',
      'err.IPCTimeout': 'EPGStation が混み合っています。少し待ってから更新してください（処理は完了しているかもしれません）。',
    },
  };
  const lang = (navigator.language || 'en').toLowerCase().startsWith('ja') ? 'ja' : 'en';
  document.documentElement.lang = lang;
  function t(key, ...args) {
    let s = (STR[lang][key] ?? STR.en[key] ?? key);
    args.forEach((a, i) => { s = s.replace('{' + i + '}', a); });
    return s;
  }
  document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  document.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });

  const GENRES = {
    en: ['News', 'Sports', 'Information', 'Drama', 'Music', 'Variety', 'Movie', 'Anime/Tokusatsu', 'Documentary', 'Theatre', 'Hobby/Education', 'Welfare'],
    ja: ['ニュース・報道', 'スポーツ', '情報・ワイドショー', 'ドラマ', '音楽', 'バラエティ', '映画', 'アニメ・特撮', 'ドキュメンタリー・教養', '劇場・公演', '趣味・教育', '福祉'],
  };
  const GENRE_COLORS = ['#5c8bd6', '#3fae6a', '#d0a23b', '#c9568f', '#9b6ad6', '#e08a3c', '#d14b4b', '#d6739e', '#4bb0b0', '#8f7b5c', '#7aa64a', '#6a7fa0'];
  const genreColor = p => (p.genre1 !== undefined && p.genre1 < GENRE_COLORS.length ? GENRE_COLORS[p.genre1] : '#555');
  const genreName = g => (g !== undefined && g < GENRES[lang].length ? GENRES[lang][g] : null);

  // ---------- helpers ----------
  const $ = id => document.getElementById(id);
  function el(tag, attrs, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'style') e.style.cssText = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : String(c));
    return e;
  }
  const pad = n => String(n).padStart(2, '0');
  const hm = ms => { const d = new Date(ms); return pad(d.getHours()) + ':' + pad(d.getMinutes()); };
  const WD = { en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'], ja: ['日', '月', '火', '水', '木', '金', '土'] };
  const md = ms => { const d = new Date(ms); return (d.getMonth() + 1) + '/' + d.getDate() + ' (' + WD[lang][d.getDay()] + ')'; };
  const startOfDay = ms => { const d = new Date(ms); d.setHours(0, 0, 0, 0); return d.getTime(); };

  let toastTimer;
  function toast(msg, isError) {
    document.querySelectorAll('.toast').forEach(e => e.remove());
    const e = el('div', { class: 'toast' + (isError ? ' error' : ''), role: 'status' }, msg);
    document.body.append(e);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => e.remove(), isError ? 6000 : 3000);
  }
  function notice(msg, isError, link) {
    const n = $('notice');
    n.replaceChildren(msg, link ? el('span', null, ' ', el('a', { href: link.href, style: 'color:inherit' }, link.text)) : '');
    n.className = 'notice' + (isError ? ' error' : '');
    n.hidden = false;
  }

  // ---------- auth + API ----------
  function token() {
    try {
      const creds = JSON.parse(localStorage.getItem('jellyfin_credentials') || '{}');
      const servers = (creds.Servers || []).filter(s => s.AccessToken);
      servers.sort((a, b) => (b.DateLastAccessed || 0) - (a.DateLastAccessed || 0));
      return servers.length ? servers[0].AccessToken : null;
    } catch (e) {
      return null;
    }
  }
  const TOKEN = token();

  async function api(path, opts = {}) {
    const headers = { Authorization: 'MediaBrowser Client="EPGStation plugin page", Token="' + TOKEN + '"' };
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
    const res = await fetch(API + path, {
      method: opts.method || 'GET', headers, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
    if (!res.ok) {
      const code = data && data.error ? data.error : 'HTTP ' + res.status;
      // EPGStation reports error codes (e.g. ReservationIsNotFound): show them in words when known.
      const known = STR[lang]['err.' + code] || STR.en['err.' + code];
      const err = new Error(known || code);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  // ---------- state ----------
  const state = {
    tab: 'guide', type: null, types: [], channels: new Map(), allChannels: new Map(), owners: {},
    reserveByProgram: new Map(), // programId -> {reserveId, kind: normal|conflict|skip|overlap, ruleId}
    filter: 'active',
  };

  async function loadReserveIndex() {
    // Index of every reservation by programme (for the guide and the search marks).
    const [res, owners] = await Promise.all([api('Reserves'), api('Owners')]);
    state.owners = owners || {};
    state.reserves = res.reserves || [];
    state.reserveByProgram = new Map();
    for (const r of state.reserves) {
      if (r.programId) state.reserveByProgram.set(r.programId, r);
    }
  }
  const reserveKind = r => (r.isSkip ? 'skip' : r.isConflict ? 'conflict' : r.isOverlap ? 'overlap' : 'normal');
  const isRecordingNow = r => reserveKind(r) === 'normal' && r.startAt <= Date.now() && Date.now() < r.endAt;

  function badgesFor(r) {
    if (!r) return [];
    const out = [];
    const kind = reserveKind(r);
    if (isRecordingNow(r)) out.push(el('span', { class: 'badge recording' }, '● ' + t('recording')));
    else if (kind === 'normal') out.push(el('span', { class: 'badge rec' }, '● ' + t('scheduled')));
    else if (kind === 'conflict') out.push(el('span', { class: 'badge conflict' }, t('conflict')));
    else if (kind === 'skip') out.push(el('span', { class: 'badge skip' }, t('skipped')));
    else out.push(el('span', { class: 'badge overlap' }, t('overlap')));
    if (r.ruleId) out.push(el('span', { class: 'badge rule' }, t('rule')));
    return out;
  }

  // ---------- tabs ----------
  function showTab(name) {
    state.tab = name;
    document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-selected', b.dataset.tab === name));
    document.querySelectorAll('.tab').forEach(s => { s.hidden = s.id !== 'tab-' + name; });
    try { localStorage.setItem('epgs-tab', name); } catch (e) { /* ignore */ }
    if (name === 'guide') renderGuide();
    if (name === 'reserves') renderReserves();
  }
  document.querySelectorAll('.tabs button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));

  // ---------- guide ----------
  const ppm = () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--ppm')) || 3;
  let guideSeq = 0;

  function fillGuideControls() {
    const types = $('types');
    types.replaceChildren(...state.types.map(ty => el('button', {
      class: ty === state.type ? 'on' : '', onclick: () => { state.type = ty; fillGuideControls(); renderGuide(); },
    }, ty === 'GR' && lang === 'ja' ? '地デジ' : ty)));
    const st = $('searchTypes');
    if (!st.children.length) {
      st.append(...state.types.map(ty => el('label', { class: 'check' }, el('input', { type: 'checkbox', value: ty, checked: true }), ' ', ty)));
    }
  }

  function fillDayHour() {
    const day = $('day');
    const today = startOfDay(Date.now());
    day.replaceChildren(...Array.from({ length: 8 }, (_, i) => {
      const ms = today + i * DAY;
      const label = (i === 0 ? t('today') + ' ' : i === 1 ? t('tomorrow') + ' ' : '') + md(ms);
      return el('option', { value: ms }, label);
    }));
    $('hour').replaceChildren(...Array.from({ length: 24 }, (_, h) => el('option', { value: h }, pad(h) + ':00')));
    setNow();
  }
  function setNow() {
    $('day').value = String(startOfDay(Date.now()));
    $('hour').value = String(new Date().getHours());
  }
  $('day').addEventListener('change', renderGuide);
  $('hour').addEventListener('change', renderGuide);
  $('now').addEventListener('click', () => { setNow(); renderGuide(); });

  async function renderGuide() {
    if (!state.type) return;
    const seq = ++guideSeq;
    const start = Number($('day').value) + Number($('hour').value) * HOUR;
    const end = start + DAY;
    const grid = $('grid');
    grid.replaceChildren(el('div', { class: 'empty' }, t('loading')));
    let schedules;
    try {
      [schedules] = await Promise.all([
        api(`Schedules?type=${state.type}&startAt=${start}&endAt=${end}`),
        loadReserveIndex(),
      ]);
    } catch (e) {
      if (seq === guideSeq) grid.replaceChildren(el('div', { class: 'empty' }, t('error', e.message)));
      return;
    }
    if (seq !== guideSeq) return;
    const k = ppm();
    const height = 24 * 60 * k;
    // Only TV and radio services (ARIB type 1, 2): one-seg and data services are not worth recording.
    const cols = schedules.filter(s => s.programs.length && state.channels.has(s.channel.id));
    const head = el('div', { class: 'g-head' }, el('div', { class: 'g-corner' }),
      cols.map(s => el('div', { class: 'g-ch', title: chName(s.channel) },
        s.channel.hasLogoData ? el('img', { src: API + 'Channels/' + s.channel.id + '/Logo', alt: '', loading: 'lazy' }) : null,
        el('span', null, chName(s.channel)))));
    const times = el('div', { class: 'g-times', style: `height:${height}px` },
      Array.from({ length: 24 }, (_, i) => el('div', { class: 'g-hour', style: `top:${i * 60 * k}px;height:${60 * k}px` }, new Date(start + i * HOUR).getHours())));
    const now = Date.now();
    const body = el('div', { class: 'g-body' }, times, cols.map(s => {
      const col = el('div', { class: 'g-col', style: `height:${height}px` });
      for (const p of s.programs) {
        const top = Math.max(0, (p.startAt - start) / 60000 * k);
        const bottom = Math.min(height, (p.endAt - start) / 60000 * k);
        if (bottom - top < 1) continue;
        const r = state.reserveByProgram.get(p.id);
        const cls = ['p'];
        if (p.endAt <= now) cls.push('past');
        if (r) {
          const kind = reserveKind(r);
          cls.push(kind === 'normal' ? (isRecordingNow(r) ? 'reserved recording' : 'reserved') : kind);
        }
        col.append(el('div', {
          class: cls.join(' '), style: `top:${top}px;height:${bottom - top}px;--genre:${genreColor(p)}`,
          title: hm(p.startAt) + ' ' + p.name, onclick: () => openDetail(p, s.channel),
        }, el('span', { class: 'tm' }, pad(new Date(p.startAt).getMinutes())), el('span', { class: 't' }, p.name),
        bottom - top > 40 && p.description ? el('div', { class: 'd' }, p.description) : null));
      }
      if (now >= start && now < end) col.append(el('div', { class: 'g-now', style: `top:${(now - start) / 60000 * k}px` }));
      return col;
    }));
    grid.replaceChildren(el('div', { style: `width:calc(var(--timew) + ${cols.length} * var(--colw))` }, head, body));
    if (!cols.length) grid.replaceChildren(el('div', { class: 'empty' }, t('noResults')));
    if (now >= start && now < end) $('gridWrap').scrollTop = Math.max(0, (now - start) / 60000 * k - 60 * k / 2);
    else $('gridWrap').scrollTop = 0;
  }

  // ---------- detail dialog + actions ----------
  const chName = c => c.halfWidthName || c.name;
  function channelName(id) { const c = state.allChannels.get(id); return c ? chName(c) : ''; }

  async function openDetail(p, channel) {
    const dlg = $('detail');
    const r = state.reserveByProgram.get(p.id) || null;
    dlg.querySelector('.dlg-head').style.setProperty('--genre', genreColor(p));
    $('dTime').textContent = md(p.startAt) + ' ' + hm(p.startAt) + '–' + hm(p.endAt) + ' (' + t('min', Math.round((p.endAt - p.startAt) / 60000)) + ')';
    $('dTitle').textContent = p.name;
    $('dChan').textContent = [channel ? chName(channel) : channelName(p.channelId), genreName(p.genre1)].filter(Boolean).join(' · ');
    $('dDesc').textContent = p.description || '';
    $('dExt').replaceChildren();
    $('dState').replaceChildren(...stateLines(r));
    $('dActions').replaceChildren(...actionButtons(p, r, () => dlg.close()));
    if (!dlg.open) dlg.showModal();
    // The guide entry has no extended text: fetch the full programme.
    if (p.extended === undefined && p.endAt > Date.now()) {
      try {
        const full = await api('Programs/' + p.id);
        if (dlg.open && $('dTitle').textContent === p.name && full.extended) $('dExt').replaceChildren(...extendedBlocks(full.extended));
      } catch (e) { /* programme may have ended; keep the short text */ }
    } else if (p.extended) {
      $('dExt').replaceChildren(...extendedBlocks(p.extended));
    }
  }
  function extendedBlocks(text) {
    // EPGStation joins ARIB extended items as "◇heading\nbody".
    return text.split(/\n(?=◇)/).map(part => {
      const m = part.match(/^◇(.*)\n([\s\S]*)$/);
      return m ? el('div', null, el('h3', null, m[1]), el('p', null, m[2].trim())) : el('p', null, part.trim());
    });
  }
  function stateLines(r) {
    if (!r) return [];
    const owner = state.owners[String(r.id)];
    const hint = isRecordingNow(r) ? t('recordingHint') : { normal: r.ruleId ? t('ruleHint') : '', conflict: t('conflictHint'), skip: t('skipHint'), overlap: t('overlapHint') }[reserveKind(r)];
    return [el('div', { style: 'margin:4px 0 8px' }, badgesFor(r), owner ? el('span', { class: 'sub', style: 'color:var(--dim);font-size:12px' }, t('by', owner.UserName)) : null),
      hint ? el('div', { style: 'color:var(--dim);font-size:13px;margin-bottom:6px' }, hint) : null].filter(Boolean);
  }

  function actionButtons(p, r, done) {
    const out = [];
    const ended = p.endAt <= Date.now();
    if (!r && !ended) {
      out.push(el('button', { type: 'button', class: 'btn rec', onclick: ev => act(ev, () => addReserve(p), done) }, '● ' + t('record')));
    } else if (r && reserveKind(r) === 'skip' && !ended) {
      out.push(el('button', { type: 'button', class: 'btn', onclick: ev => act(ev, () => unskip(r), done) }, t('unskip')));
    } else if (r && !ended) {
      out.push(el('button', { type: 'button', class: 'btn ghost', onclick: ev => act(ev, () => cancelReserve(r), done) },
        isRecordingNow(r) ? t('stop') : t('cancel')));
    }
    out.push(el('button', { type: 'button', class: 'btn ghost', onclick: () => $('detail').close() }, t('close')));
    return out;
  }

  async function act(ev, fn, done) {
    const btn = ev.currentTarget;
    btn.disabled = true;
    try {
      if (await fn() !== false) {
        if (done) done();
        await refreshCurrent();
      }
    } catch (e) {
      toast(t('error', e.message), true);
    } finally {
      btn.disabled = false;
    }
  }

  async function addReserve(p) {
    await api('Reserves', { method: 'POST', body: { programId: p.id } });
    toast(t('scheduledOk', p.name));
  }
  async function cancelReserve(r) {
    const recording = isRecordingNow(r);
    const msg = recording ? t('confirmStop', r.name) : r.ruleId ? t('confirmSkip', r.name) : t('confirmCancel', r.name);
    if (!confirm(msg)) return false;
    await api('Reserves/' + r.id, { method: 'DELETE' });
    toast(recording ? t('stoppedOk', r.name) : t('cancelledOk', r.name));
    return true;
  }
  async function unskip(r) {
    await api('Reserves/' + r.id + '/Skip', { method: 'DELETE' });
    toast(t('unskippedOk', r.name));
  }

  async function refreshCurrent() {
    if (state.tab === 'guide') await renderGuide();
    else if (state.tab === 'reserves') await renderReserves();
    else if (state.tab === 'search' && state.lastSearch) await runSearch();
  }

  // ---------- list rows (search + reservations) ----------
  function rowFor(p, r, opts = {}) {
    const ended = p.endAt <= Date.now();
    const owner = r ? state.owners[String(r.id)] : null;
    const sub = [channelName(p.channelId), genreName(p.genre1), owner ? t('by', owner.UserName) : null].filter(Boolean).join(' · ');
    const acts = [];
    if (!ended) {
      if (!r) acts.push(el('button', { class: 'btn rec small-rec', onclick: ev => { ev.stopPropagation(); act(ev, () => addReserve(p)); } }, '● ' + t('record')));
      else if (reserveKind(r) === 'skip') acts.push(el('button', { class: 'btn small', onclick: ev => { ev.stopPropagation(); act(ev, () => unskip(r)); } }, t('unskip')));
      else acts.push(el('button', { class: 'btn small', onclick: ev => { ev.stopPropagation(); act(ev, () => cancelReserve(r)); } }, isRecordingNow(r) ? t('stop') : t('cancel')));
    } else {
      acts.push(el('span', { class: 'sub' }, t('ended')));
    }
    return el('div', { class: 'row', style: `--genre:${genreColor(p)}`, onclick: () => openDetail(p, state.allChannels.get(p.channelId)) },
      el('div', { class: 'when' }, opts.withDate ? md(p.startAt) : null, el('b', null, hm(p.startAt) + '–' + hm(p.endAt))),
      el('div', { class: 'main' }, el('div', { class: 'title' }, badgesFor(r), p.name), el('div', { class: 'sub' }, sub)),
      el('div', { class: 'acts' }, acts));
  }
  function groupByDay(items, render) {
    const out = [];
    let day = null;
    for (const it of items) {
      const d = startOfDay(it.startAt);
      if (d !== day) { day = d; out.push(el('div', { class: 'day-h' }, md(d))); }
      out.push(render(it));
    }
    return out;
  }

  // ---------- search ----------
  $('searchForm').addEventListener('submit', ev => {
    ev.preventDefault();
    state.lastSearch = {
      keyword: $('keyword').value.trim(),
      description: $('searchDesc').checked,
      types: [...$('searchTypes').querySelectorAll('input:checked')].map(i => i.value),
    };
    runSearch();
  });
  async function runSearch() {
    const box = $('searchResults');
    box.replaceChildren(el('div', { class: 'empty' }, t('loading')));
    try {
      const [items] = await Promise.all([api('Search', { method: 'POST', body: state.lastSearch }), loadReserveIndex()]);
      const now = Date.now();
      const list = (items || []).filter(p => p.endAt > now && state.channels.has(p.channelId)).sort((a, b) => a.startAt - b.startAt);
      box.replaceChildren(list.length ? el('div', { class: 'day-h', style: 'position:static' }, t('results', list.length)) : el('div', { class: 'empty' }, t('noResults')),
        ...groupByDay(list, p => rowFor(p, state.reserveByProgram.get(p.id))));
    } catch (e) {
      box.replaceChildren(el('div', { class: 'empty' }, t('error', e.message)));
    }
  }

  // ---------- reservations ----------
  document.querySelectorAll('#reserveFilter button').forEach(b => b.addEventListener('click', () => { state.filter = b.dataset.filter; renderReserves(); }));
  $('reload').addEventListener('click', () => renderReserves());

  async function renderReserves() {
    document.querySelectorAll('#reserveFilter button').forEach(b => b.classList.toggle('on', b.dataset.filter === state.filter));
    const box = $('reserveList');
    if (!box.children.length) box.replaceChildren(el('div', { class: 'empty' }, t('loading')));
    try {
      await loadReserveIndex();
    } catch (e) {
      box.replaceChildren(el('div', { class: 'empty' }, t('error', e.message)));
      return;
    }
    const now = Date.now();
    const want = { active: k => k === 'normal' || k === 'overlap', conflict: k => k === 'conflict', skip: k => k === 'skip' }[state.filter];
    const list = state.reserves.filter(r => r.endAt > now && want(reserveKind(r))).sort((a, b) => a.startAt - b.startAt);
    // Reserve items carry the programme fields, so they render like programmes.
    box.replaceChildren(...(list.length ? groupByDay(list, r => rowFor(r.programId ? { ...r, id: r.programId } : r, r)) : [el('div', { class: 'empty' }, t('noReserves'))]));
  }

  // ---------- start ----------
  async function start() {
    if (!TOKEN) {
      notice(t('notSignedIn'), true, { href: '../../web/', text: t('signIn') });
      return;
    }
    let status;
    try {
      status = await api('Status');
    } catch (e) {
      if (e.status === 401) notice(t('notSignedIn'), true, { href: '../../web/', text: t('signIn') });
      else notice(t('error', e.message), true);
      return;
    }
    $('who').textContent = status.userName;
    if (!status.allowed) { notice(t('notAllowed'), true); return; }
    if (!status.configured) { notice(t('notConfigured'), true); return; }
    if (!status.connected) { notice(t('notConnected', status.error || ''), true); return; }
    const channels = await api('Channels');
    for (const c of channels) {
      state.allChannels.set(c.id, c);
      if (c.type === 1 || c.type === 2) state.channels.set(c.id, c);
    }
    state.types = TYPES.filter(ty => [...state.channels.values()].some(c => c.channelType === ty));
    state.type = state.types[0] || null;
    fillGuideControls();
    fillDayHour();
    let tab = 'guide';
    try { tab = localStorage.getItem('epgs-tab') || 'guide'; } catch (e) { /* ignore */ }
    showTab(['guide', 'search', 'reserves'].includes(tab) ? tab : 'guide');
  }
  start();
}());
