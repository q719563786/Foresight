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

  return Object.freeze({overviewLabel, counts, visibleRisks});
});
