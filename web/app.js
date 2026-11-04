'use strict';

const paths = {
  dashboard: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  network: '<circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="m11 7-5 9m7-9 5 9M8 18h8"/>',
  route: '<path d="M5 3v5l7 5v8M19 3v5l-7 5M3 3h4m10 0h4"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m7 9 3 3-3 3m6 0h4"/>',
  settings: '<path d="m9.5 3-.8 2.4-2 .9-2.3-.5L2 10l1.7 1.9v2.2L2 16l2.4 4.2 2.3-.5 2 .9.8 2.4h5l.8-2.4 2-.9 2.3.5L22 16l-1.7-1.9v-2.2L22 10l-2.4-4.2-2.3.5-2-.9L14.5 3Z" transform="translate(1 -1) scale(.92)"/><circle cx="12" cy="12" r="3"/>',
  shield: '<path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  activity: '<rect x="3" y="4" width="18" height="16" rx="4"/><path d="M5 12h3l2-4 4 8 2-4h3"/>',
  power: '<path d="M12 3v9M6.4 5.8a8 8 0 1 0 11.2 0"/>',
  down: '<path d="M12 3v17m-6-6 6 6 6-6"/>',
  up: '<path d="M12 21V4m-6 6 6-6 6 6"/>',
  arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  refresh: '<path d="M20 8a8.5 8.5 0 0 0-14-3L3 8m0-5v5h5m-4 8a8.5 8.5 0 0 0 14 3l3-3m0 5v-5h-5"/>',
  moon: '<path d="M20.5 13a8.8 8.8 0 1 1-9.5-9.5A7 7 0 0 0 20.5 13Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  list: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M8 4v16m4-11h5m-5 6h5"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>',
  plug: '<path d="M8 3v5m8-5v5M5 8h14v3a7 7 0 0 1-14 0Zm7 10v4"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8Zm-9 10 9 5 9-5M3 18l9 5 9-5"/>',
  search: '<circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6"/>',
  gauge: '<path d="M4 18a9 9 0 1 1 16 0M12 13l4-5M7 17h10"/><circle cx="12" cy="13" r="1.5"/>',
  plus: '<path d="M12 4v16M4 12h16"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  pause: '<path d="M8 5v14m8-14v14"/>',
  play: '<path d="m7 4 14 8-14 8Z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.2"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  signal: '<path d="M4 20v-4m5 4v-8m6 8V8m5 12V4"/>',
};
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.globe}</svg>`;
const $ = id => document.getElementById(id);
const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const text = (id, value) => { $(id).textContent = value; };
const fillIcons = () => document.querySelectorAll('[data-icon]').forEach(node => { node.innerHTML = icon(node.dataset.icon); });
fillIcons();

let token = '', state = null, page = 'dashboard', selectedGroup = '', loading = false;
let pending = false, testing = false, pausedLogs = false, logLines = [], rules = [];
let toastTimer, modalCallback, profileSignature = '', groupSignature = '', nodeSignature = '';
const leafDelays = new Map();
const pageNames = {dashboard:['仪表盘','OVERVIEW'],proxies:['代理节点','PROXIES'],profiles:['订阅配置','PROFILES'],connections:['实时连接','CONNECTIONS'],rules:['路由规则','RULES'],logs:['运行日志','LOGS'],settings:['设置','SETTINGS']};

function bytes(value) {
  const n = Math.max(0, Number(value) || 0);
  const units = ['B','KB','MB','GB','TB'];
  const index = Math.min(4, n > 0 ? Math.floor(Math.log(n) / Math.log(1024)) : 0);
  const scaled = n / Math.pow(1024, index);
  return [scaled >= 100 || index === 0 ? scaled.toFixed(0) : scaled.toFixed(1), units[index]];
}
const formatBytes = value => bytes(value).join(' ');
function toast(message, error = false) {
  clearTimeout(toastTimer);
  text('toast', message);
  $('toast').className = 'toast' + (error ? ' error' : '');
  toastTimer = setTimeout(() => $('toast').classList.add('hidden'), error ? 8000 : 4500);
}

async function api(path, body) {
  const options = {credentials:'same-origin',cache:'no-store'};
  if (body) {
    options.method = 'POST';
    options.headers = {'Content-Type':'application/json','X-UI-Token':token};
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`);
  return data;
}

async function action(body, message) {
  if (pending) return;
  pending = true;
  renderDisabled();
  try {
    const result = await api('/api/action', body);
    toast(result.message || message || '操作已完成');
    if (!result.terminal) await refresh(true);
    return result;
  } catch (error) {
    toast(error.message, true);
  } finally {
    pending = false;
    renderDisabled();
  }
}

function setSwitch(id, enabled) { $(id).setAttribute('aria-checked', enabled ? 'true' : 'false'); }
function renderDisabled() {
  const online = state && state.online;
  ['system-proxy','tun','allow-lan','ipv6','log-level','flush-dns','test-group'].forEach(id => { $(id).disabled = pending || !online; });
  $('system-proxy').disabled = pending || !online || !(state && state.systemProxy.available);
  $('power').disabled = pending || !state;
  document.querySelectorAll('[data-mode]').forEach(button => { button.disabled = pending || !online; });
  $('test-group').disabled = pending || !online || testing || !selectedGroup;
}

function getGroups() {
  if (!state) return [];
  return Object.entries(state.proxies).filter(([name, proxy]) => Array.isArray(proxy.all) && !proxy.hidden && (name !== 'GLOBAL' || state.config.mode === 'global'));
}

function getPrimary() {
  const groups = getGroups();
  return groups.find(([, proxy]) => proxy.type === 'Selector') || groups[0];
}

function chart(id, key) {
  const points = (state.samples || []).slice(-60).map(sample => Number(sample[key]) || 0);
  const height = 59, maximum = Math.max(1024, ...points) * 1.15;
  if (points.length === 1) points.unshift(points[0]);
  const coords = points.map((value, index) => [index * 300 / Math.max(points.length - 1, 1), height - value / maximum * 48]);
  const path = coords.length ? 'M' + coords.map(point => point.map(v => v.toFixed(1)).join(',')).join(' L') : '';
  $(id).querySelector('.chart-line').setAttribute('d', path);
  $(id).querySelector('.chart-fill').setAttribute('d', path ? path + ' L300,65 L0,65 Z' : '');
}

function renderState() {
  const {online, config, subscriptions, proxies, connections} = state;
  $('setup-banner').classList.toggle('hidden', subscriptions.profiles.length > 0);
  $('sidebar-status').classList.toggle('online', online);
  text('sidebar-version', online ? state.version : '内核未连接');
  text('core-version', state.version || '—');
  text('current-profile', subscriptions.current || '未选择');
  text('profile-name', subscriptions.current || '暂无订阅');
  text('status-heading', online ? '代理内核运行中' : '代理内核未连接');
  text('run-badge', online ? '运行中' : '未连接');
  $('run-badge').className = 'pill ' + (online ? 'success' : 'neutral');
  text('power-hint', online ? '点击停止' : '点击启动');
  $('power').innerHTML = icon(online ? 'pause' : 'power');
  $('power').setAttribute('aria-label', online ? '停止代理内核' : '启动代理内核');
  const primary = getPrimary();
  text('active-node', online ? (primary ? `${primary[0]} → ${primary[1].now || '自动调度'}` : '内核已连接，暂无代理组') : '请检查 clashctl 状态或启动内核');
  const leafCount = Object.values(proxies).filter(proxy => !proxy.all && !['Direct','Reject','Compatible','Pass','DIRECT','REJECT'].includes(proxy.type)).length;
  text('node-count', leafCount);
  text('leaf-count', leafCount);
  text('groups-count', getGroups().length + ' 个策略组');
  text('connections-count', connections.length);
  text('preview-count', connections.length);
  text('connection-description', `当前 ${connections.length} 个活跃连接 · 每 2 秒更新`);
  const down = bytes(state.traffic.down), up = bytes(state.traffic.up);
  text('download-speed', down[0]); text('download-unit', down[1] + '/s');
  text('upload-speed', up[0]); text('upload-unit', up[1] + '/s');
  text('download-total', formatBytes(state.downloadTotal));
  text('upload-total', formatBytes(state.uploadTotal));
  text('proxy-port', ':' + (config['mixed-port'] || config.port || '—'));
  text('memory-info', state.memory > 0 ? formatBytes(state.memory) : '');
  text('install-directory', state.directory);
  setSwitch('system-proxy', state.systemProxy.enabled);
  text('system-proxy-desc', state.systemProxy.available ? 'GNOME 桌面代理' : '当前桌面暂不支持');
  setSwitch('tun', config.tun.enable);
  setSwitch('allow-lan', config['allow-lan']);
  setSwitch('ipv6', config.ipv6);
  if (document.activeElement !== $('log-level') && config['log-level']) $('log-level').value = config['log-level'];
  document.querySelectorAll('[data-mode]').forEach(button => {
    button.classList.toggle('active', config.mode === button.dataset.mode);
    button.setAttribute('aria-pressed', String(config.mode === button.dataset.mode));
  });
  const active = subscriptions.profiles.find(profile => profile.active);
  const usage = active ? active.usage : {};
  const used = (usage.upload || 0) + (usage.download || 0);
  text('profile-usage', usage.total ? `${formatBytes(used)} / ${formatBytes(usage.total)} · 已用 ${Math.min(100, Math.round(used / usage.total * 100))}%` : '订阅未提供流量信息');
  $('profile-progress').style.width = (usage.total ? Math.min(100, used / usage.total * 100) : 0) + '%';
  text('updated-at', '更新于 ' + new Date().toLocaleTimeString('zh-CN', {hour12:false}));
  $('error-banner').classList.toggle('hidden', !state.error);
  text('error-banner', state.error || '');
  chart('down-chart', 'down'); chart('up-chart', 'up');
  renderPreview();
  if (page === 'proxies') renderProxies();
  if (page === 'connections') renderConnections();
  if (page === 'profiles') renderProfiles();
  renderDisabled();
}

function connectionTarget(connection) {
  const m = connection.metadata || {};
  return m.host || m.destinationIP || '未知目标';
}

function renderPreview() {
  const connections = [...state.connections].sort((a,b) => (b.download || 0) - (a.download || 0));
  $('preview-connections').innerHTML = connections.slice(0,5).map(connection => {
    const host = connectionTarget(connection), chain = connection.chains || [];
    return `<tr><td title="${esc(host)}"><div class="target-cell"><span class="site-avatar">${esc(host[0].toUpperCase())}</span><span>${esc(host)}</span></div></td><td title="${esc(chain.join(' → '))}">${esc(chain[0] || 'DIRECT')}</td><td class="numeric">${esc(formatBytes(connection.download))}</td><td class="numeric">${esc(formatBytes(connection.upload))}</td></tr>`;
  }).join('') || '<tr><td colspan="4" class="empty">暂无活跃连接<br>应用访问网络后，连接会显示在这里</td></tr>';
  const groups = getGroups().slice(0,3);
  $('preview-groups').innerHTML = groups.map(([name, proxy], index) => `<button class="group-item" data-open-group="${esc(name)}"><span class="group-avatar">${icon(index === 0 ? 'globe' : index === 1 ? 'gauge' : 'layers')}</span><span class="group-text"><strong>${esc(name)}</strong><small>${esc(proxy.now || '自动调度')}</small></span><span>${icon('chevron')}</span></button>`).join('') || '<div class="empty">暂无代理组</div>';
}

function proxyDelay(name) {
  if (leafDelays.has(name)) return leafDelays.get(name);
  const history = (state.proxies[name] || {}).history || [];
  return history.length ? history[history.length - 1].delay || -1 : null;
}

function renderProxies(force = false) {
  const groups = getGroups();
  if (!groups.some(([name]) => name === selectedGroup)) selectedGroup = groups.length ? groups[0][0] : '';
  const tabsSignature = JSON.stringify(groups.map(([name, proxy]) => [name, proxy.all.length])) + selectedGroup;
  if (groupSignature !== tabsSignature || force) {
    groupSignature = tabsSignature;
    $('group-tabs').innerHTML = groups.map(([name, proxy]) => `<button class="group-tab ${name === selectedGroup ? 'active' : ''}" data-group="${esc(name)}">${esc(name)}<small>${proxy.all.length}</small></button>`).join('');
  }
  const group = state.proxies[selectedGroup];
  if (!group) {
    $('node-grid').innerHTML = '<div class="empty">暂无节点，请先启动内核并添加订阅</div>';
    text('group-description', '');
    return;
  }
  const manual = group.type === 'Selector';
  text('group-description', `${manual ? '手动选择' : group.type === 'URLTest' ? '自动选择 · 由内核调度' : '故障转移 · 由内核调度'} · ${group.all.length} 个节点`);
  const query = $('node-search').value.toLowerCase();
  let members = group.all.filter(name => name.toLowerCase().includes(query));
  if ($('node-sort').value === 'delay') members.sort((a,b) => (proxyDelay(a) > 0 ? proxyDelay(a) : Infinity) - (proxyDelay(b) > 0 ? proxyDelay(b) : Infinity));
  if ($('node-sort').value === 'name') members.sort((a,b) => a.localeCompare(b, 'zh-CN'));
  const signature = JSON.stringify(members.map(name => [name, proxyDelay(name)])) + group.now + selectedGroup + manual;
  if (nodeSignature === signature && !force) return;
  nodeSignature = signature;
  $('node-grid').innerHTML = members.map(name => {
    const proxy = state.proxies[name] || {}, selected = group.now === name, delay = proxyDelay(name);
    const latency = delay === null ? '未测速' : delay < 1 ? '超时' : `${delay} ms`;
    return `<article class="node-card ${selected ? 'selected' : ''} ${manual ? '' : 'disabled'}" ${manual ? 'tabindex="0" role="button"' : ''} data-select-node="${esc(name)}" aria-label="${esc(name)}${selected ? '，已选择' : ''}" ${manual ? `aria-pressed="${selected}"` : ''}><div class="node-heading"><span class="node-symbol">${icon(proxy.all ? 'layers' : 'globe')}</span><span class="node-name" title="${esc(name)}">${esc(name)}</span>${selected ? `<span class="node-check">${icon('check')}</span>` : ''}</div><div class="node-footer"><span class="node-type">${esc(proxy.type || 'PROXY')}${proxy.udp ? ' · UDP' : ''}</span><button class="latency ${delay == null || delay < 1 ? 'unavailable' : delay > 300 ? 'slow' : ''}" data-test-node="${esc(name)}" title="测试此节点延迟" aria-label="测试 ${esc(name)} 延迟">${icon('signal')}<span>${esc(latency)}</span></button></div></article>`;
  }).join('') || '<div class="empty">没有找到匹配的节点</div>';
}

function renderProfiles() {
  const signature = JSON.stringify(state.subscriptions);
  if (profileSignature === signature) return;
  profileSignature = signature;
  $('profile-list').innerHTML = state.subscriptions.profiles.map(profile => {
    const u = profile.usage, used = (u.upload || 0) + (u.download || 0);
    let expiry = u.expire ? new Date(u.expire * 1000).toLocaleDateString('zh-CN') : '未提供';
    return `<article class="card profile-card"><div class="profile-card-top"><span class="profile-file">${icon('file')}</span><span class="pill ${profile.active ? 'success' : 'neutral'}">${profile.active ? '使用中' : '未启用'}</span></div><h3>${esc(profile.name)}</h3><div class="host">${esc(profile.host)}</div><div class="details"><div class="detail-row"><span>最近更新</span><span>${esc(profile.updated || '—')}</span></div><div class="detail-row"><span>订阅流量</span><span>${u.total ? esc(formatBytes(used) + ' / ' + formatBytes(u.total)) : '未提供'}</span></div><div class="detail-row"><span>到期时间</span><span>${esc(expiry)}</span></div></div><div class="profile-actions"><button class="secondary-button" data-update-profile="${esc(profile.name)}">${icon('refresh')}更新订阅</button>${!profile.active ? `<button class="primary-button" data-use-profile="${esc(profile.name)}">启用</button>` : ''}</div></article>`;
  }).join('') || '<article class="card empty">还没有订阅配置，点击右上角添加订阅。</article>';
}

function renderConnections() {
  const query = $('connection-search').value.toLowerCase();
  const rows = state.connections.filter(connection => JSON.stringify([connection.metadata, connection.chains, connection.rule]).toLowerCase().includes(query));
  $('connection-list').innerHTML = rows.slice(0,300).map(connection => {
    const m = connection.metadata || {}, target = connectionTarget(connection), chain = (connection.chains || []).join(' → ');
    return `<tr><td title="${esc(target)}">${esc(target)}<small>${esc(m.process || m.sourceIP || '—')} · ${esc(m.network || 'TCP')}:${esc(m.destinationPort || '')}</small></td><td title="${esc(connection.rulePayload || '')}">${esc(connection.rule || '—')}<small>${esc(connection.rulePayload || '')}</small></td><td title="${esc(chain)}">${esc((connection.chains || [])[0] || 'DIRECT')}</td><td class="numeric">${esc(formatBytes(connection.download))}<small>${esc(formatBytes(connection.upload))}</small></td><td><button class="icon-button" data-close-connection="${esc(connection.id)}" title="关闭此连接" aria-label="关闭 ${esc(target)} 的连接">${icon('close')}</button></td></tr>`;
  }).join('') || '<tr><td colspan="5" class="empty">暂无匹配的活跃连接</td></tr>';
}

async function loadRules() {
  try { const data = await api('/api/rules'); rules = data.rules || []; renderRules(); }
  catch (error) { $('rule-list').innerHTML = `<tr><td colspan="4" class="empty">${esc(error.message)}</td></tr>`; }
}
function renderRules() {
  const query = $('rule-search').value.toLowerCase();
  const filtered = rules.map((rule, index) => ({...rule, index:index + 1})).filter(rule => JSON.stringify(rule).toLowerCase().includes(query));
  text('rule-description', `${rules.length} 条路由规则 · 从上到下依次匹配`);
  $('rule-list').innerHTML = filtered.slice(0,500).map(rule => `<tr><td>${rule.index}</td><td><span class="pill neutral">${esc(rule.type)}</span></td><td title="${esc(rule.payload || '')}">${esc(rule.payload || '所有流量')}</td><td>${esc(rule.proxy)}</td></tr>`).join('') || '<tr><td colspan="4" class="empty">暂无匹配的规则</td></tr>';
  text('rule-more', filtered.length > 500 ? `显示前 500 条，共 ${filtered.length} 条匹配结果。输入关键词可缩小范围。` : `共 ${filtered.length} 条匹配结果`);
}

async function loadLogs() {
  if (pausedLogs) return;
  try { const data = await api('/api/logs'); logLines = data.lines || []; renderLogs(); }
  catch (error) { toast(error.message, true); }
}
function renderLogs() {
  const query = $('log-search').value.toLowerCase();
  const box = $('log-lines');
  box.innerHTML = logLines.filter(line => line.toLowerCase().includes(query)).map(line => {
    const level = /level=(error|warning|debug)/.exec(line);
    return `<div class="log-line ${level ? level[1] : ''}">${esc(line)}</div>`;
  }).join('') || '<div class="empty">暂无匹配的日志</div>';
  if (!pausedLogs) box.scrollTop = box.scrollHeight;
}

function navigate(next) {
  if (!pageNames[next]) next = 'dashboard';
  page = next;
  document.querySelectorAll('.page').forEach(section => section.classList.toggle('hidden', section.id !== page));
  document.querySelectorAll('.nav-item').forEach(button => button.classList.toggle('active', button.dataset.page === page));
  text('page-title', pageNames[page][0]); text('breadcrumb', pageNames[page][1]);
  if (location.hash !== '#' + page) history.replaceState(null,'','#' + page);
  window.scrollTo(0,0);
  if (state) {
    if (page === 'proxies') renderProxies(true);
    if (page === 'profiles') renderProfiles();
    if (page === 'connections') renderConnections();
    renderDisabled();
  }
  if (page === 'rules') loadRules();
  if (page === 'logs') loadLogs();
}

function openModal(title, body, submit, callback) {
  text('modal-title', title); $('modal-body').innerHTML = body;
  text('modal-submit', submit); $('modal-submit').disabled = false;
  modalCallback = callback; $('modal').showModal();
  const firstInput = $('modal').querySelector('input');
  if (firstInput) firstInput.focus();
}

async function testNode(name) {
  try {
    const result = await api('/api/action', {action:'delay', name});
    leafDelays.set(name, result.delay > 0 ? result.delay : -1);
    return result.delay > 0;
  } catch (error) {
    leafDelays.set(name, -1);
    return false;
  } finally { if (page === 'proxies') renderProxies(); }
}

document.addEventListener('click', async event => {
  const button = event.target.closest('button, [data-select-node]');
  if (!button || button.disabled) return;
  if (button.dataset.page) { navigate(button.dataset.page); return; }
  if (button.dataset.openGroup) { selectedGroup = button.dataset.openGroup; navigate('proxies'); return; }
  if (button.dataset.group) { selectedGroup = button.dataset.group; renderProxies(true); return; }
  if (button.dataset.mode) { await action({action:'settings',patch:{mode:button.dataset.mode}}); return; }
  if (button.dataset.testNode) {
    button.disabled = true;
    const name = button.dataset.testNode;
    await testNode(name);
    if (proxyDelay(name) > 0) toast(`${name} · ${proxyDelay(name)} ms`);
    else toast(`${name} · 测速超时或不可用`, true);
    return;
  }
  if (button.dataset.selectNode) {
    const group = state.proxies[selectedGroup];
    if (group && group.type === 'Selector' && button.dataset.selectNode !== group.now)
      await action({action:'select',name:selectedGroup,member:button.dataset.selectNode}, '节点已切换');
    return;
  }
  if (button.dataset.closeConnection) {
    await action({action:'close-connection',id:button.dataset.closeConnection}); return;
  }
  if (button.dataset.updateProfile) {
    const name = button.dataset.updateProfile;
    openModal('更新订阅', `重新下载并更新 <strong>${esc(name)}</strong>。如果是当前订阅，clashctl 会重新加载内核配置。`, '更新', () => action({action:'profile-update',name})); return;
  }
  if (button.dataset.useProfile) {
    const name = button.dataset.useProfile;
    openModal('切换订阅', `启用 <strong>${esc(name)}</strong> 并重新加载内核配置。`, '启用', () => action({action:'profile-use',name})); return;
  }
});

document.addEventListener('keydown', event => {
  if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('[data-select-node]')) { event.preventDefault(); event.target.click(); }
});

$('power').onclick = () => {
  if (!state) return;
  if (!state.online) { action({action:'start'}); return; }
  openModal('停止代理内核', '停止后，使用该内核的应用会断开代理连接。系统代理和已有终端的代理设置需要按需关闭。', '停止内核', () => action({action:'stop'}));
};
$('system-proxy').onclick = () => action({action:'system-proxy',enabled:!state.systemProxy.enabled});
$('tun').onclick = () => {
  const enabled = !state.config.tun.enable;
  openModal(enabled ? '开启 TUN 模式' : '关闭 TUN 模式', '将打开 clashctl 授权终端。请在终端中完成管理员授权；切换时内核会重启，可能短暂中断连接。', '打开授权终端', () => action({action:'tun',enabled}));
};
$('allow-lan').onclick = () => action({action:'settings',patch:{'allow-lan':!state.config['allow-lan']}});
$('ipv6').onclick = () => action({action:'settings',patch:{ipv6:!state.config.ipv6}});
$('log-level').onchange = () => action({action:'settings',patch:{'log-level':$('log-level').value}});
$('flush-dns').onclick = () => action({action:'flush-dns'},'DNS 缓存已清除');
$('node-search').oninput = () => state && renderProxies(true);
$('node-sort').onchange = () => state && renderProxies(true);
$('connection-search').oninput = () => state && renderConnections();
$('rule-search').oninput = renderRules;
$('log-search').oninput = renderLogs;
$('pause-logs').onclick = () => {
  pausedLogs = !pausedLogs;
  $('pause-logs').innerHTML = icon(pausedLogs ? 'play' : 'pause') + (pausedLogs ? '继续更新' : '暂停滚动');
  if (!pausedLogs) loadLogs();
};
$('test-group').onclick = async () => {
  const group = state.proxies[selectedGroup];
  if (!group || testing) return;
  testing = true; renderDisabled();
  const names = group.all.slice();
  let done = 0, success = 0;
  const worker = async () => {
    while (names.length) {
      const name = names.shift();
      if (await testNode(name)) success++;
      done++;
      $('test-group').innerHTML = icon('gauge') + `${done} / ${group.all.length}`;
    }
  };
  await Promise.all([worker(),worker(),worker()]);
  testing = false;
  $('test-group').innerHTML = icon('gauge') + '组内测速';
  renderDisabled();
  toast(`测速完成 · ${success} / ${group.all.length} 个节点可用`);
};
$('add-profile').onclick = () => openModal('添加订阅', '<label>订阅名称<input name="profileName" maxlength="150" placeholder="例如：我的订阅" required autocomplete="off"></label><label>Clash / Mihomo 订阅链接<input name="profileUrl" type="url" placeholder="https://…" required autocomplete="off" spellcheck="false"></label><p>首次添加会自动启用；后续订阅可手动切换。链接只提交到本机 clashctl。</p>', '添加订阅', async form => {
  const result = await api('/api/action', {action:'profile-add',name:form.elements.profileName.value.trim(),url:form.elements.profileUrl.value.trim()});
  toast(result.message || '订阅已添加');
  await refresh(true);
  return result;
});
$('setup-add-profile').onclick = () => $('add-profile').click();
$('modal-close').onclick = $('modal-cancel').onclick = () => $('modal').close();
$('modal-form').onsubmit = async event => {
  event.preventDefault();
  if ($('modal-submit').disabled) return;
  $('modal-submit').disabled = true;
  try {
    const result = await modalCallback(event.target);
    if (result) $('modal').close();
  } catch (error) {
    let message = $('modal-body').querySelector('.form-error');
    if (!message) { message = document.createElement('p'); message.className = 'form-error'; $('modal-body').appendChild(message); }
    message.textContent = error.message;
  } finally { $('modal-submit').disabled = false; }
};

function theme(value) {
  document.body.classList.toggle('dark', value === 'dark');
  $('theme').innerHTML = icon(value === 'dark' ? 'sun' : 'moon');
  try { localStorage.setItem('clashctl-theme', value); } catch (_) {}
}
let initialTheme = 'light';
try { initialTheme = localStorage.getItem('clashctl-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); } catch (_) {}
theme(initialTheme);
$('theme').onclick = () => theme(document.body.classList.contains('dark') ? 'light' : 'dark');
$('refresh').onclick = async () => {
  $('refresh').classList.add('spinning');
  try { await refresh(true); if (page === 'rules') await loadRules(); if (page === 'logs') await loadLogs(); }
  finally { $('refresh').classList.remove('spinning'); }
};
window.addEventListener('hashchange', () => navigate(location.hash.slice(1)));

async function refresh(force = false) {
  if (loading) return;
  loading = true;
  try {
    state = await api('/api/state');
    renderState();
    if (page === 'logs') await loadLogs();
  } catch (error) {
    $('error-banner').classList.remove('hidden');
    text('error-banner', error.message + '。控制台会自动重试。');
    if (force) toast(error.message, true);
  } finally { loading = false; }
}

async function start() {
  try { token = (await api('/api/bootstrap')).token; }
  catch (error) { text('error-banner', error.message); $('error-banner').classList.remove('hidden'); return; }
  navigate(location.hash.slice(1) || 'dashboard');
  await refresh();
  const poll = async () => { await refresh(); setTimeout(poll, 2000); };
  setTimeout(poll, 2000);
}
start();
