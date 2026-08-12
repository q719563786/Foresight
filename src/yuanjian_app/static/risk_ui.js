(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.YuanJianRiskUI = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const overviewLabels = Object.freeze({
    action: '需要行动',
    watch: '继续观察',
    stable: '目前平稳',
    coverage_gap: '监控覆盖不足'
  });

  function overviewLabel(state) {
    return overviewLabels[state] || '系统核实中';
  }

  function counts(dashboard) {
    const values = dashboard?.counts || {};
    return [
      {key: 'action', value: Number(values.action) || 0, label: '现在要处理'},
      {key: 'watch', value: Number(values.watch) || 0, label: '继续观察'},
      {key: 'verifying', value: Number(values.verifying) || 0, label: '系统核实中'}
    ];
  }

  function visibleRisks(items) {
    return [...(Array.isArray(items) ? items : [])]
      .filter(item => item && (item.alert_level === 'L3' || item.alert_level === 'L4'))
      .sort((left, right) => {
        const mode = Number(right.mode === 'action') - Number(left.mode === 'action');
        if (mode) return mode;
        const level = Number(right.alert_level === 'L4') - Number(left.alert_level === 'L4');
        if (level) return level;
        return (Number(right.impact_score) || 0) - (Number(left.impact_score) || 0);
      })
      .slice(0, 5);
  }

  function detailSummary(detail) {
    const judgment = detail?.judgment || {};
    const impact = Array.isArray(detail?.impacts) ? detail.impacts[0] || {} : {};
    const candidate = impact.candidate || {};
    const triggers = [
      ...(judgment.up_triggers || []).map(value => `风险升级：${value}`),
      ...(judgment.down_triggers || []).map(value => `风险解除：${value}`)
    ];
    return {
      interest: impact.interest_name || '已登记利益',
      impact: impact.reason || '系统仍在核实具体影响',
      action: candidate.recommended_action || '暂不做不可逆决定；按时间窗口复查。',
      decisionBy: candidate.window_end || (judgment.horizons || []).join('、') || '等待下一次核实',
      triggers
    };
  }

  function intelligenceRequests(mode) {
    if (mode === 'raw') return ['/api/external/radar?limit=10&offset=0'];
    if (mode === 'manage') return ['/api/external/sources', '/api/external/rules'];
    return ['/api/cognition/status', '/api/external/sources'];
  }

  return Object.freeze({overviewLabel, counts, visibleRisks, detailSummary, intelligenceRequests});
});
