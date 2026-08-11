(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.YuanJianUI = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const evidence = Object.freeze({
    E1: 'E1 · 单一来源线索',
    E2: 'E2 · 多源互证',
    E3: 'E3 · 含官方来源的强证据',
    E4: 'E4 · 高强度公开证据'
  });
  const trends = Object.freeze({
    rising: '上升',
    stable: '稳定',
    falling: '下降',
    low_sample: '样本积累中',
    accumulating: '样本积累中'
  });
  const statuses = Object.freeze({
    active: '有效', unread: '未读', read: '已读', digest: '每日汇总',
    ok: '正常', error: '待重试', paused: '已暂停', stale: '内容陈旧',
    open: '进行中', resolved: '已结算', low: '低', medium: '中', high: '高'
  });
  const categories = Object.freeze({
    health: '健康', finance: '金融', employment: '就业', safety: '安全',
    policy: '政策', technology: '科技', general: '综合'
  });
  const sourceKinds = Object.freeze({
    rss: 'RSS / Atom', html_list: '公开网页列表', gdelt: 'GDELT 全球新闻索引'
  });

  function evidenceLabel(value) { return evidence[value] || String(value || '证据待确认'); }
  function trendLabel(value) { return trends[value] || String(value || '趋势未知'); }
  function statusLabel(value) { return statuses[value] || String(value || '状态未知'); }
  function categoryLabel(value) { return categories[value] || String(value || '综合'); }
  function sourceKindLabel(value) { return sourceKinds[value] || String(value || '公开来源'); }

  function formatLocalTime(value, now = new Date(), offsetMinutes = -new Date().getTimezoneOffset()) {
    if (!value) return '时间未知';
    const point = new Date(value);
    if (Number.isNaN(point.getTime())) return '时间未知';
    const shift = offsetMinutes * 60 * 1000;
    const localPoint = new Date(point.getTime() + shift);
    const localNow = new Date(now.getTime() + shift);
    const day = Date.UTC(localPoint.getUTCFullYear(), localPoint.getUTCMonth(), localPoint.getUTCDate());
    const today = Date.UTC(localNow.getUTCFullYear(), localNow.getUTCMonth(), localNow.getUTCDate());
    const difference = Math.floor((today - day) / 86400000);
    const time = `${String(localPoint.getUTCHours()).padStart(2, '0')}:${String(localPoint.getUTCMinutes()).padStart(2, '0')}`;
    if (difference === 0) return `今天 ${time}`;
    if (difference === 1) return `昨天 ${time}`;
    if (difference > 1 && difference < 7) return `${difference} 天前`;
    return `${localPoint.getUTCFullYear()}-${String(localPoint.getUTCMonth() + 1).padStart(2, '0')}-${String(localPoint.getUTCDate()).padStart(2, '0')}`;
  }

  function buildQuery(values) {
    const params = new URLSearchParams();
    Object.entries(values || {}).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined && value !== false) {
        params.set(key, String(value));
      }
    });
    const text = params.toString();
    return text ? `?${text}` : '';
  }

  function applyMetricFilter(state, filter) {
    const next = {...state, offset: 0};
    delete next.needs_judgment;
    delete next.notification_status;
    if (filter === 'judge') next.needs_judgment = true;
    if (filter === 'unread') next.notification_status = 'unread';
    return next;
  }

  function pageRange(total, limit, offset) {
    const start = total ? offset + 1 : 0;
    return {start, end: Math.min(total, offset + limit), total};
  }

  function movePage(state, direction, total) {
    const step = direction === 'next' ? state.limit : -state.limit;
    const maximum = Math.max(0, Math.floor((Math.max(0, total) - 1) / state.limit) * state.limit);
    return {...state, offset: Math.min(maximum, Math.max(0, state.offset + step))};
  }

  function sourceHealthLabel(source) {
    if (!source?.enabled) return '已暂停';
    if (source.stale) return '内容陈旧';
    return statusLabel(source.last_status);
  }

  return Object.freeze({
    evidenceLabel, trendLabel, statusLabel, categoryLabel, sourceKindLabel, formatLocalTime,
    buildQuery, applyMetricFilter, pageRange, movePage, sourceHealthLabel
  });
});
