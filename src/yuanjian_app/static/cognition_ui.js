(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.CognitionUI = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function count(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? Math.floor(number) : 0;
  }

  function summarizeCognitionRun(result) {
    const processed = count(result?.backfill?.processed);
    const queued = count(result?.queued);
    const judgments = count(result?.judgments?.succeeded);
    const impacts = count(result?.mapped_impacts);
    const notifications = count(result?.notifications_created);
    const seconds = (count(result?.elapsed_ms) / 1000).toFixed(1);
    if (processed + queued + judgments + impacts + notifications === 0) {
      return `运行完成，本次没有新增待处理信息（${seconds}秒）`;
    }
    return `运行完成：处理${processed}条信息，排队${queued}个事件，完成${judgments}次研判，形成${impacts}条利益影响，新增${notifications}条提醒（${seconds}秒）`;
  }

  async function runCognitionWithFeedback(options) {
    const {
      apiCall,
      button,
      status,
      onComplete,
      onFailure = () => {},
      setIntervalFn = setInterval,
      clearIntervalFn = clearInterval
    } = options;
    let elapsed = 0;
    button.disabled = true;
    button.textContent = '正在运行认知…';
    status.className = 'run-status busy';
    status.textContent = '正在聚合信息、核验证据并映射个人利益…';
    const timer = setIntervalFn(() => {
      elapsed += 1;
      status.textContent = `正在聚合信息、核验证据并映射个人利益… 已用${elapsed}秒`;
    }, 1000);
    try {
      const result = await apiCall();
      const notice = {kind: 'success', text: summarizeCognitionRun(result)};
      status.className = 'run-status success';
      status.textContent = notice.text;
      await onComplete(notice);
      return result;
    } catch (error) {
      const notice = {kind: 'error', text: `运行失败：${error.message || '未知错误'}`};
      status.className = 'run-status error';
      status.textContent = notice.text;
      await onFailure(notice);
      return null;
    } finally {
      clearIntervalFn(timer);
      button.disabled = false;
      button.textContent = '立即运行认知';
    }
  }

  return {runCognitionWithFeedback, summarizeCognitionRun};
}));
