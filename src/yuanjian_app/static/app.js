const token = new URLSearchParams(location.search).get('token') || '';
const content = document.querySelector('#content');
const title = document.querySelector('#page-title');

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {'Content-Type': 'application/json', 'X-YuanJian-Token': token, ...(options.headers || {})}
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error?.message || '本地请求失败');
  return payload;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

function forecastCard(item) {
  return `<article class="card level-${escapeHtml(item.alert_level)}">
    <div class="card-top"><span class="badge">${escapeHtml(item.alert_level)}</span><span>${Math.round(item.probability * 100)}%</span></div>
    <h3>${escapeHtml(item.title)}</h3>
    <p>截止：${escapeHtml(item.window_end)} · 可信度：${escapeHtml(item.confidence)}</p>
    <button class="detail" data-id="${escapeHtml(item.forecast_id)}">查看详情</button>
  </article>`;
}

function signalCard(item) {
  return `<article class="card signal level-${escapeHtml(item.alert_level)}">
    <div class="card-top"><span class="badge">${escapeHtml(item.alert_level)}</span><span>${escapeHtml(item.reliability)}</span></div>
    <h3>${escapeHtml(item.summary)}</h3>
    <p><b>影响：</b>${escapeHtml(item.why_it_matters)}</p>
    <p class="action"><b>建议：</b>${escapeHtml(item.recommended_action)}</p>
  </article>`;
}

function externalCard(item) {
  const rule = item.matched_rules?.[0];
  const why = rule?.reasons?.join('；') || '命中关注规则';
  return `<article class="card signal level-${escapeHtml(item.alert_level)}">
    <div class="card-top"><span class="badge">${escapeHtml(item.alert_level)}</span><span>${escapeHtml(item.source_count)}个独立来源</span></div>
    <h3>${escapeHtml(item.title)}</h3>
    <p>${escapeHtml(item.summary || '暂无摘要')}</p>
    <p><b>与你有关：</b>${escapeHtml(why)}</p>
    <p><b>发布：</b>${escapeHtml(item.published_at || '来源未提供')} · <b>抓取：</b>${escapeHtml(item.fetched_at)}</p>
    <a class="source-link" href="${escapeHtml(item.canonical_url)}" target="_blank" rel="noopener noreferrer">打开原始来源</a>
  </article>`;
}

function clusterCard(item) {
  return `<article class="card cluster evidence-${escapeHtml(item.evidence_level)}">
    <div class="card-top"><span class="badge">${escapeHtml(item.evidence_level)}</span><span>${escapeHtml(item.independent_domains)}个独立域名 · ${escapeHtml(item.item_count)}条证据</span></div>
    <h3>${escapeHtml(item.title)}</h3>
    <p>${escapeHtml(item.summary || '等待更多公开摘要')}</p>
    <p><b>状态：</b>${item.needs_judgment ? '等待研判' : '研判完成'} · <b>首次发现：</b>${escapeHtml(item.first_seen_at)}</p>
    <button class="cluster-detail" data-id="${escapeHtml(item.cluster_id)}">查看判断与证据</button>
  </article>`;
}

async function showCognition(runNotice = null) {
  title.textContent = '事件判断雷达';
  const [clusterData, status, trendData, notificationData] = await Promise.all([
    api('/api/cognition/clusters'), api('/api/cognition/status'), api('/api/cognition/trends'), api('/api/notifications')
  ]);
  const trends = trendData.trends.filter(item => item.window_hours === 24).map(item =>
    `<span class="trend ${escapeHtml(item.status)}">${escapeHtml(item.category)}：${escapeHtml(item.event_count)}条 · ${escapeHtml(item.status)}</span>`
  ).join('');
  content.innerHTML = `<div class="metrics cognition-metrics"><div><strong>${status.clusters}</strong><span>事件簇</span></div><div><strong>${status.needs_judgment}</strong><span>待研判</span></div><div><strong>${status.unread_notifications}</strong><span>未读提醒</span></div></div>
    <div class="panel cognition-toolbar"><div><h2>经过聚合与互证的外部事件</h2><p class="form-note">同题报道先合并，再按独立域名和官方来源分为E1—E4；私人利益只在本机映射。</p><p id="cognition-run-status" class="run-status ${escapeHtml(runNotice?.kind || '')}" aria-live="polite">${escapeHtml(runNotice?.text || '点击后会显示运行进度和本次结果。')}</p></div><button id="run-cognition">立即运行认知</button></div>
    <div class="trend-strip">${trends || '<span class="trend accumulating">趋势数据积累中</span>'}</div>
    <div class="grid">${clusterData.clusters.length ? clusterData.clusters.map(clusterCard).join('') : '<div class="empty">尚未形成事件簇。后台会继续读取公开来源。</div>'}</div>
    <div class="panel"><h3>本地通知中心</h3>${notificationData.notifications.length ? notificationData.notifications.slice(0,5).map(item => `<p><span class="badge">${escapeHtml(item.alert_level)}</span> ${escapeHtml(item.reason)}</p>`).join('') : '<p>目前没有提醒。</p>'}</div>`;
  document.querySelector('#run-cognition').addEventListener('click', async event => {
    await CognitionUI.runCognitionWithFeedback({
      apiCall: () => api('/api/cognition/run', {method:'POST', body:'{}'}),
      button: event.currentTarget,
      status: document.querySelector('#cognition-run-status'),
      onComplete: notice => showCognition(notice)
    });
  });
}

async function showClusterDetail(id) {
  const item = await api(`/api/cognition/clusters/${encodeURIComponent(id)}`);
  title.textContent = item.title;
  const judgment = item.judgment;
  const evidence = item.items.map(source => `<li><a href="${escapeHtml(source.canonical_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a> · ${escapeHtml(source.source_domain)}</li>`).join('');
  const impacts = item.impacts.map(impact => `<article class="impact level-${escapeHtml(impact.alert_level)}"><div class="card-top"><span class="badge">${escapeHtml(impact.alert_level)}</span><span>${Math.round(impact.impact_score*100)}分</span></div><h3>${escapeHtml(impact.interest_name || impact.interest_id)}</h3><p>${escapeHtml(impact.reason)}</p>${impact.candidate ? `<p><b>候选预测：</b>${escapeHtml(impact.candidate.title)}</p><label>人工概率<select class="candidate-probability">${probabilityOptions(0.50)}</select></label><button class="confirm-candidate" data-id="${escapeHtml(impact.impact_id)}">确认进入预测账本</button>` : ''}</article>`).join('');
  content.innerHTML = `<div class="panel"><div class="card-top"><span class="badge">证据等级 ${escapeHtml(item.evidence_level)}</span><span>${escapeHtml(item.independent_domains)}个独立域名</span></div>
    <h2>事实判断</h2><p>${escapeHtml(judgment?.fact_summary || '等待研判')}</p>
    <h3>因果链</h3><ol>${(judgment?.causal_chain || []).map(value => `<li>${escapeHtml(value)}</li>`).join('') || '<li>等待研判</li>'}</ol>
    <h3>反对证据与不确定性</h3><ul>${(judgment?.uncertainties || []).map(value => `<li>${escapeHtml(value)}</li>`).join('') || '<li>尚未形成</li>'}</ul>
    <h3>时间窗口</h3><p>${(judgment?.horizons || []).map(escapeHtml).join(' · ') || '等待研判'}</p>
    <h3>公开证据</h3><ul>${evidence}</ul></div>
    <div class="panel"><h2>对你的本地影响</h2><div class="grid">${impacts || '<p>没有命中已登记利益。</p>'}</div></div>
    <div class="panel feedback"><h3>纠正本地判断</h3><button data-action="mute">静音7天</button> <button data-action="lower_importance">降低重要度</button> <button data-action="false_positive">标记误报</button></div>`;
  document.querySelectorAll('.confirm-candidate').forEach(button => button.addEventListener('click', async () => {
    const probability = Number(button.closest('.impact').querySelector('.candidate-probability').value);
    await api(`/api/cognition/candidates/${encodeURIComponent(button.dataset.id)}/confirm`, {method:'POST', body:JSON.stringify({probability})});
    alert('已写入不可变预测账本');
    await showClusterDetail(id);
  }));
  document.querySelectorAll('.feedback button').forEach(button => button.addEventListener('click', async () => {
    await api(`/api/cognition/clusters/${encodeURIComponent(id)}/feedback`, {method:'POST', body:JSON.stringify({action:button.dataset.action})});
    alert('本地反馈已保存，不会发送给外部AI');
    await showClusterDetail(id);
  }));
}

async function showSettings() {
  title.textContent = '后台与AI设置';
  const [ai, startup, status] = await Promise.all([
    api('/api/settings/ai'), api('/api/settings/startup'), api('/api/cognition/status')
  ]);
  content.innerHTML = `<div class="panel"><h2>后台监控</h2><p>事件簇：${status.clusters} · 待研判：${status.needs_judgment} · 未读提醒：${status.unread_notifications}</p>
    <p>登录启动：${startup.installed ? '已开启' : '未开启'}${startup.available === false ? '（源码运行时不可设置，独立程序中可用）' : ''}</p>
    ${startup.available === false ? '' : `<button id="startup-toggle">${startup.installed ? '关闭登录启动' : '开启登录启动'}</button>`}</div>
    <form id="ai-settings" class="panel structured-form"><h2>可选外部AI研判</h2><p class="form-note">默认关闭。只发送公开标题、摘要、网址、时间和通用类别；私人利益、Obsidian原文、地址、医疗、债务和账户不会发送。API费用与ChatGPT/Codex订阅分开。</p>
      <label><input name="enabled" type="checkbox" ${ai.enabled ? 'checked' : ''}> 启用外部AI</label>
      <label>Responses API地址<input name="endpoint" type="url" required value="${escapeHtml(ai.endpoint)}"></label>
      <label>明确的模型编号<input name="model" value="${escapeHtml(ai.model)}" placeholder="不自动猜测模型"></label>
      <label>API密钥<input name="token" type="password" autocomplete="new-password" placeholder="${ai.configured ? '已安全保存；留空表示不更换' : '尚未配置'}"></label>
      <button type="submit">保存AI设置</button><p>密钥状态：${ai.configured ? '已加密保存' : '未配置'}</p></form>`;
  const startupButton = document.querySelector('#startup-toggle');
  if (startupButton) startupButton.addEventListener('click', async () => {
    await api('/api/settings/startup', {method:'POST', body:JSON.stringify({enabled:!startup.installed})});
    await showSettings();
  });
  document.querySelector('#ai-settings').addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.target);
    const values = {enabled:form.get('enabled') === 'on', endpoint:form.get('endpoint'), model:form.get('model')};
    if (form.get('token')) values.token = form.get('token');
    await api('/api/settings/ai', {method:'POST', body:JSON.stringify(values)});
    alert('AI设置已保存');
    await showSettings();
  });
}

async function showExternal() {
  title.textContent = '外部信息雷达';
  const [radar, sourceData, ruleData] = await Promise.all([
    api('/api/external/radar'), api('/api/external/sources'), api('/api/external/rules')
  ]);
  const sources = sourceData.sources.map(source => `<article class="card">
    <div class="card-top"><span>${escapeHtml(source.name)}</span><span>${source.stale ? '已陈旧' : escapeHtml(source.last_status)}</span></div>
    <p>${escapeHtml(source.kind)} · 每${escapeHtml(source.refresh_minutes)}分钟</p>
    ${source.last_error ? `<p class="error">${escapeHtml(source.last_error)}</p>` : ''}
    <button class="refresh-source" data-id="${escapeHtml(source.source_id)}" ${source.enabled ? '' : 'disabled'}>立即刷新</button>
    <button class="toggle-source" data-id="${escapeHtml(source.source_id)}" data-enabled="${source.enabled ? 'true' : 'false'}">${source.enabled ? '暂停' : '恢复'}</button>
  </article>`).join('');
  const rules = ruleData.rules.map(rule => `<span class="badge">${escapeHtml(rule.query)} · ${escapeHtml(rule.importance)}/5</span>`).join(' ');
  content.innerHTML = `<div class="panel"><h2>与你利益相关的新变化</h2><p class="form-note">系统先读取外界，再去重、核验来源并按你的关注规则过滤。单一来源只算线索，不算定论。</p>
    <div class="grid">${radar.items.length ? radar.items.map(externalCard).join('') : '<div class="empty">尚无命中关注规则的新情报。可先添加来源和关注词。</div>'}</div></div>
    <div class="panel"><h3>关注规则</h3><p>${rules || '还没有关注词。'}</p>
      <form id="rule-form" class="inline-form"><input name="query" required maxlength="80" placeholder="例如：行业、政策、资产"><select name="importance"><option value="5">最高</option><option value="4">高</option><option value="3" selected>中</option></select><button type="submit">添加关注词</button></form></div>
    <div class="panel"><h3>外部来源</h3><div class="grid">${sources || '<div class="empty">尚未添加外部来源。</div>'}</div>
      <form id="source-form" class="structured-form"><label>来源名称<input name="name" required maxlength="100"></label><label>公开地址<input name="endpoint" required type="url" placeholder="https://..."></label><label>类型<select name="kind"><option value="rss">RSS / Atom</option><option value="html_list">公开网页列表</option><option value="gdelt">GDELT JSON</option></select></label><button type="submit">添加来源</button></form></div>`;
  document.querySelector('#rule-form').addEventListener('submit', async event => {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.target)); values.importance = Number(values.importance);
    await api('/api/external/rules', {method:'POST', body:JSON.stringify(values)}); await showExternal();
  });
  document.querySelector('#source-form').addEventListener('submit', async event => {
    event.preventDefault(); const values = Object.fromEntries(new FormData(event.target));
    await api('/api/external/sources', {method:'POST', body:JSON.stringify(values)}); await showExternal();
  });
  document.querySelectorAll('.refresh-source').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true; await api('/api/external/refresh', {method:'POST', body:JSON.stringify({source_id:button.dataset.id})}); await showExternal();
  }));
  document.querySelectorAll('.toggle-source').forEach(button => button.addEventListener('click', async () => {
    await api(`/api/external/sources/${encodeURIComponent(button.dataset.id)}/enabled`, {method:'POST', body:JSON.stringify({enabled:button.dataset.enabled !== 'true'})}); await showExternal();
  }));
}

async function showDashboard() {
  title.textContent = '今日雷达';
  const data = await api('/api/dashboard');
  const forecasts = data.high_alerts.map(forecastCard).join('');
  const signals = data.high_signals.map(signalCard).join('');
  content.innerHTML = forecasts || signals
    ? `<h2>危险信号</h2><div class="grid">${signals || '<div class="empty">没有高等级新信号。</div>'}</div><h2>高等级预测</h2><div class="grid">${forecasts || '<div class="empty">没有L3或L4预测。</div>'}</div>`
    : '<div class="empty">目前没有L3或L4预警。</div>';
}

async function showSignals() {
  title.textContent = '信号收件箱';
  const data = await api('/api/signals');
  content.innerHTML = data.signals.length
    ? `<div class="grid">${data.signals.map(signalCard).join('')}</div>`
    : '<div class="empty">还没有保存的信号。请先录入新事件。</div>';
}

async function showInterests() {
  title.textContent = '利益地图';
  const data = await api('/api/interests');
  const labels = {health:'健康',cashflow:'现金流',work:'工作',policy:'政策',family:'家庭',assets:'资产负债',opportunity:'机会'};
  content.innerHTML = `<div class="grid">${data.objects.map(item => `<article class="card interest"><div class="card-top"><span>${escapeHtml(labels[item.category] || item.category)}</span><span>重要度 ${item.importance}/5</span></div><h3>${escapeHtml(item.name)}</h3><p>隐私：${escapeHtml(item.privacy_level)} · 状态：${escapeHtml(item.status)}</p></article>`).join('')}</div>
    <div class="panel relationship"><h3>依赖关系</h3>${data.links.length ? data.links.map(link => `<p>${escapeHtml(link.source_id)} → ${escapeHtml(link.target_id)} · ${escapeHtml(link.relationship)} · 强度${link.strength}</p>`).join('') : '<p>暂未登记对象之间的依赖关系。</p>'}</div>`;
}

async function showKnowledge(query = '') {
  title.textContent = '知识库';
  const [vaultData, documentData] = await Promise.all([
    api('/api/knowledge/vaults'),
    api(`/api/knowledge/documents?q=${encodeURIComponent(query)}`)
  ]);
  const options = vaultData.vaults.map(vault => `<option value="${escapeHtml(vault.path)}">${escapeHtml(vault.name)}</option>`).join('');
  content.innerHTML = `<div class="panel"><h3>Obsidian只读索引</h3><p class="form-note">只读取Markdown并保存相对路径、摘要和哈希，不会修改原文件。</p>
    ${options ? `<form id="index-form" class="inline-form"><select name="path">${options}</select><button type="submit">更新索引</button></form>` : '<p>没有在用户目录中发现Obsidian知识库。</p>'}
    <form id="knowledge-search" class="inline-form"><input name="q" value="${escapeHtml(query)}" placeholder="搜索标题或摘要"><button type="submit">搜索</button></form></div>
    <div class="knowledge-list">${documentData.documents.length ? documentData.documents.map(doc => `<article class="card"><h3>${escapeHtml(doc.title)}</h3><p>${escapeHtml(doc.relative_path)}</p><p>${escapeHtml(doc.excerpt)}</p><small>SHA-256：${escapeHtml(doc.sha256.slice(0,16))}…</small></article>`).join('') : '<div class="empty">索引中还没有文档。</div>'}</div>`;
  const indexForm = document.querySelector('#index-form');
  if (indexForm) indexForm.addEventListener('submit', async event => {
    event.preventDefault();
    const path = new FormData(indexForm).get('path');
    const result = await api('/api/knowledge/index', {method:'POST', body:JSON.stringify({path})});
    alert(`索引完成：${result.indexed}篇文档`);
    await showKnowledge();
  });
  document.querySelector('#knowledge-search').addEventListener('submit', event => {
    event.preventDefault();
    showKnowledge(new FormData(event.target).get('q')).catch(showError);
  });
}

async function showForecasts() {
  title.textContent = '全部预测';
  const data = await api('/api/forecasts');
  content.innerHTML = data.forecasts.length
    ? `<div class="grid">${data.forecasts.map(forecastCard).join('')}</div>`
    : '<div class="empty">预测账本还是空的。</div>';
}

function showEventForm() {
  title.textContent = '录入新事件';
  content.innerHTML = `<form id="event-form" class="panel">
    <label>发生了什么？</label>
    <textarea name="text" rows="7" placeholder="例如：医院最终结算自付9500元"></textarea>
    <button type="submit">分析这个事件</button>
    <div id="candidate"></div>
  </form>`;
  document.querySelector('#event-form').addEventListener('submit', async event => {
    event.preventDefault();
    const text = new FormData(event.target).get('text');
    const data = await api('/api/events', {method:'POST', body:JSON.stringify({text, occurred_at:new Date().toISOString().slice(0,10)})});
    document.querySelector('#candidate').innerHTML = `<article class="card level-${escapeHtml(data.signal.alert_level)}"><h3>已保存为${escapeHtml(data.signal.alert_level)}信号</h3><p>${escapeHtml(data.signal.why_it_matters)}</p><p class="action">${escapeHtml(data.signal.recommended_action)}</p></article>`;
  });
}

function probabilityOptions(selected) {
  return [0.05,0.10,0.20,0.35,0.50,0.65,0.80,0.90,0.95]
    .map(value => `<option value="${value}" ${Number(selected) === value ? 'selected' : ''}>${Math.round(value*100)}%</option>`)
    .join('');
}

function showForecastForm(initial = {}, forecastId = null) {
  title.textContent = forecastId ? '修订预测' : '新建预测';
  const today = new Date().toISOString().slice(0,10);
  content.innerHTML = `<form id="forecast-form" class="panel structured-form">
    <p class="form-note">把判断写成到期可以核验的句子。${forecastId ? '保存后会新增版本，旧版本不会被覆盖。' : ''}</p>
    <label>预测标题<input name="title" required maxlength="160" value="${escapeHtml(initial.title || '')}" placeholder="例如：月底前收到工资"></label>
    <label>结算标准<textarea name="resolution_criteria" required rows="3" placeholder="写明用什么事实判定发生或未发生">${escapeHtml(initial.resolution_criteria || '')}</textarea></label>
    <div class="form-row">
      <label>开始日期<input name="window_start" type="date" required value="${escapeHtml(initial.window_start || today)}"></label>
      <label>截止日期<input name="window_end" type="date" required value="${escapeHtml(initial.window_end || today)}"></label>
      <label>当前概率<select name="probability" required>${probabilityOptions(initial.probability || 0.50)}</select></label>
    </div>
    <div class="form-row">
      <label>可信度<select name="confidence"><option value="low">低</option><option value="medium" selected>中</option><option value="high">高</option></select></label>
      <label>预警级别<select name="alert_level"><option>L1</option><option selected>L2</option><option>L3</option><option>L4</option></select></label>
      <label>隐私级别<select name="privacy_level"><option>P1</option><option selected>P2</option><option>P3</option></select></label>
    </div>
    <button type="submit">${forecastId ? '保存为新版本' : '登记正式预测'}</button>
  </form>`;
  for (const name of ['confidence','alert_level','privacy_level']) {
    if (initial[name]) document.querySelector(`[name="${name}"]`).value = initial[name];
  }
  document.querySelector('#forecast-form').addEventListener('submit', async event => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.target));
    values.probability = Number(values.probability);
    const path = forecastId ? `/api/forecasts/${encodeURIComponent(forecastId)}/versions` : '/api/forecasts';
    const result = await api(path, {method:'POST', body:JSON.stringify(values)});
    alert(result.duplicate ? '内容没有变化，未生成重复版本' : `已保存为版本 ${result.version}`);
    await showDetail(result.forecast_id);
  });
}

async function showScore() {
  title.textContent = '模型表现';
  const data = await api('/api/score');
  content.innerHTML = `<div class="metrics"><div><strong>${data.resolved_binary}</strong><span>已评分预测</span></div><div><strong>${data.brier_score ?? '—'}</strong><span>Brier Score</span></div></div>`;
}

async function showDetail(id) {
  const item = await api(`/api/forecasts/${encodeURIComponent(id)}`);
  title.textContent = item.title;
  const resolution = item.status === 'open' ? `<form id="resolve-form" class="resolve-form">
    <h3>结算这条预测</h3>
    <select name="outcome"><option value="occurred">已发生</option><option value="not_occurred">未发生</option><option value="partial">部分发生</option><option value="indeterminate">无法判定</option></select>
    <input name="resolved_at" type="date" required>
    <input name="note" placeholder="实际结果说明" required>
    <button type="submit">确认结算</button>
  </form>` : '<p class="settled">这条预测已经结算。</p>';
  content.innerHTML = `<div class="panel"><p><b>概率：</b>${Math.round(item.probability*100)}%</p><p><b>结算标准：</b>${escapeHtml(item.resolution_criteria)}</p><p><b>截止：</b>${escapeHtml(item.window_end)}</p>${item.status === 'open' ? '<button id="revise" type="button">修订预测</button>' : ''}${resolution}<h3>历史版本</h3>${item.versions.map(v=>`<details><summary>版本${v.version} · ${Math.round(v.probability*100)}%</summary><pre>${escapeHtml(v.content)}</pre></details>`).join('')}</div>`;
  const revise = document.querySelector('#revise');
  if (revise) revise.addEventListener('click', () => showForecastForm(item.draft, id));
  const form = document.querySelector('#resolve-form');
  if (form) form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!confirm('结算后将写入预测账本，确定继续吗？')) return;
    const values = Object.fromEntries(new FormData(form));
    const result = await api(`/api/forecasts/${encodeURIComponent(id)}/resolve`, {method:'POST', body:JSON.stringify(values)});
    alert(result.brier_score == null ? '结算完成' : `结算完成，Brier Score：${result.brier_score}`);
    await showDetail(id);
  });
}

document.addEventListener('click', event => {
  const nav = event.target.closest('.nav');
  if (nav) {
    document.querySelectorAll('.nav').forEach(item => item.classList.remove('active'));
    nav.classList.add('active');
    ({cognition:showCognition,external:showExternal,dashboard:showDashboard,event:showEventForm,signals:showSignals,interests:showInterests,knowledge:showKnowledge,create:showForecastForm,forecasts:showForecasts,score:showScore,settings:showSettings})[nav.dataset.view]().catch(showError);
  }
  const clusterDetail = event.target.closest('.cluster-detail');
  if (clusterDetail) showClusterDetail(clusterDetail.dataset.id).catch(showError);
  const detail = event.target.closest('.detail');
  if (detail) showDetail(detail.dataset.id).catch(showError);
});

function showError(error) { content.innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`; }
document.querySelector('#shutdown').addEventListener('click', async () => {
  if (!confirm('确定安全退出远见吗？')) return;
  try {
    await api('/api/shutdown', {method:'POST', body:'{}'});
  } catch (error) {
    if (!String(error.message).includes('fetch')) showError(error);
  }
  document.body.innerHTML = '<main class="closed"><div class="panel"><h1>远见已安全退出</h1><p>现在可以关闭这个页面。</p></div></main>';
});
showCognition().catch(showError);
