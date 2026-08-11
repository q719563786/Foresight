import subprocess
import unittest
from pathlib import Path


class CognitionFrontendTests(unittest.TestCase):
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "yuanjian_app"
        / "static"
        / "cognition_ui.js"
    )
    ui_core_path = module_path.with_name("ui_core.js")

    def run_node(self, body):
        script = f"""
const assert = require('node:assert/strict');
const ui = require({str(self.module_path)!r});
(async () => {{
{body}
}})().catch(error => {{ console.error(error); process.exit(1); }});
"""
        result = subprocess.run(
            ["node", "-e", script],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_ui_core(self, body):
        script = f"""
const assert = require('node:assert/strict');
const ui = require({str(self.ui_core_path)!r});
{body}
"""
        result = subprocess.run(
            ["node", "-e", script],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_user_facing_labels_query_and_time_are_stable(self):
        self.run_ui_core(
            """
assert.equal(ui.evidenceLabel('E2'), 'E2 · 多源互证');
assert.equal(ui.trendLabel('low_sample'), '样本积累中');
assert.equal(ui.categoryLabel('employment'), '就业');
assert.equal(ui.categoryLabel('general'), '综合');
assert.equal(ui.sourceKindLabel('rss'), 'RSS / Atom');
assert.equal(ui.sourceKindLabel('html_list'), '公开网页列表');
assert.equal(ui.sourceKindLabel('gdelt'), 'GDELT 全球新闻索引');
assert.equal(ui.statusLabel('active'), '有效');
assert.equal(ui.statusLabel('error'), '待重试');
assert.equal(
  ui.buildQuery({limit:10, offset:0, q:'医保', evidence:''}),
  '?limit=10&offset=0&q=%E5%8C%BB%E4%BF%9D'
);
const now = new Date('2026-08-12T04:00:00Z');
assert.equal(ui.formatLocalTime('2026-08-12T01:20:00Z', now, 0), '今天 01:20');
assert.equal(ui.formatLocalTime('2026-08-11T03:10:00Z', now, 0), '昨天 03:10');
assert.equal(ui.formatLocalTime('', now, 0), '时间未知');
"""
        )

    def test_metric_filter_resets_pagination_and_maps_unread(self):
        self.run_ui_core(
            """
assert.deepEqual(
  ui.applyMetricFilter({limit:10, offset:30, q:'医保'}, 'unread'),
  {limit:10, offset:0, q:'医保', notification_status:'unread'}
);
assert.deepEqual(
  ui.applyMetricFilter({limit:10, offset:20, q:'医保'}, 'judge'),
  {limit:10, offset:0, q:'医保', needs_judgment:true}
);
"""
        )

    def test_pagination_and_source_health_keep_user_context(self):
        self.run_ui_core(
            """
assert.deepEqual(
  ui.movePage({limit:10, offset:10, q:'医保'}, 'next', 35),
  {limit:10, offset:20, q:'医保'}
);
assert.deepEqual(
  ui.movePage({limit:10, offset:0, q:'医保'}, 'prev', 35),
  {limit:10, offset:0, q:'医保'}
);
assert.equal(ui.sourceHealthLabel({enabled:false, last_status:'ok', stale:false}), '已暂停');
assert.equal(ui.sourceHealthLabel({enabled:true, last_status:'error', stale:false}), '待重试');
assert.equal(ui.sourceHealthLabel({enabled:true, last_status:'ok', stale:true}), '内容陈旧');
"""
        )

    def test_success_shows_busy_then_refreshes_with_a_specific_result(self):
        self.run_node(
            """
let finish;
const button = {disabled:false, textContent:'立即运行认知'};
const status = {textContent:'', className:''};
let notice;
const running = ui.runCognitionWithFeedback({
  apiCall: () => new Promise(resolve => { finish = resolve; }),
  button,
  status,
  onComplete: async value => { notice = value; },
  setIntervalFn: () => 7,
  clearIntervalFn: id => assert.equal(id, 7)
});
await Promise.resolve();
assert.equal(button.disabled, true);
assert.equal(button.textContent, '正在运行认知…');
assert.match(status.textContent, /正在聚合信息/);
finish({backfill:{processed:3}, queued:2, judgments:{succeeded:1}, mapped_impacts:4, notifications_created:1, elapsed_ms:5300});
await running;
assert.equal(button.disabled, false);
assert.equal(button.textContent, '立即运行认知');
assert.equal(notice.kind, 'success');
assert.match(notice.text, /处理3条信息/);
assert.match(notice.text, /形成4条利益影响/);
assert.equal(notice.text.includes('5.3秒'), true);
"""
        )

    def test_zero_result_and_error_are_both_visible_and_button_recovers(self):
        self.run_node(
            """
const makeElement = () => ({disabled:false, textContent:'立即运行认知', className:''});
let button = makeElement();
let status = makeElement();
let notice;
await ui.runCognitionWithFeedback({
  apiCall: async () => ({backfill:{processed:0}, queued:0, judgments:{succeeded:0}, mapped_impacts:0, notifications_created:0, elapsed_ms:9}),
  button, status, onComplete: async value => { notice = value; },
  setIntervalFn: () => 1, clearIntervalFn: () => {}
});
assert.equal(notice.text, '运行完成，本次没有新增待处理信息（0.0秒）');
button = makeElement(); status = makeElement(); let failure;
await ui.runCognitionWithFeedback({
  apiCall: async () => { throw new Error('认知任务正在运行，请稍候'); },
  button, status, onComplete: async () => {},
  onFailure: notice => { failure = notice; },
  setIntervalFn: () => 2, clearIntervalFn: () => {}
});
assert.equal(status.textContent, '运行失败：认知任务正在运行，请稍候');
assert.match(status.className, /error/);
assert.deepEqual(failure, {kind:'error', text:'运行失败：认知任务正在运行，请稍候'});
assert.equal(button.disabled, false);
assert.equal(button.textContent, '立即运行认知');
"""
        )


if __name__ == "__main__":
    unittest.main()
