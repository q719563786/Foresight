# YuanJian v0.8 Risk Cockpit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the news-centric desktop front end with a risk cockpit that tells the user what affects them, when it matters and what to do, while keeping raw intelligence available only on demand.

**Architecture:** Add a read-only risk-dashboard projection in the cognition controller and expose it through one authenticated local API. The front end consumes that projection directly, renders at most five L3/L4 risk cards, and moves raw feeds and source management into a lazy-loaded settings subview. Existing collection, clustering, evidence, database and privacy boundaries remain unchanged.

**Tech Stack:** Python 3 standard library, SQLite, local `ThreadingHTTPServer`, vanilla JavaScript/CSS, pywebview, PyInstaller, Python `unittest`, Node assertions for pure UI helpers.

## Global Constraints

- The default screen must answer “is there risk, what comes first, and what should I do” within 10 seconds.
- L1/L2 items must not appear on the risk home page.
- The risk home page may show at most five cards.
- Raw news, source health, watch rules and technical errors must not appear in primary navigation or the default screen.
- Raw evidence remains traceable through an explicit secondary action.
- If all enabled sources are unavailable, the system must report insufficient monitoring coverage instead of “currently stable”.
- No database migration, new runtime dependency, private-field transmission or automatic medical, lending, investment or external action.

---

### Task 1: Read-only risk dashboard projection

**Files:**
- Modify: `src/yuanjian_app/cognition.py`
- Modify: `src/yuanjian_app/http_api.py`
- Test: `tests/test_cognition.py`
- Test: `tests/test_http_api.py`

**Interfaces:**
- Produces: `CognitionController.risk_dashboard(source_states: list[dict] | None = None, limit: int = 5) -> dict`
- Produces: authenticated `GET /api/risk-dashboard`
- Returns: `state`, `summary`, `counts`, `items`, `coverage` and `generated_at`.

- [ ] **Step 1: Write failing controller tests**

Create fixture judgments and impacts covering L2, urgent L3, non-urgent L3 and L4. Assert that `risk_dashboard()` excludes L2, returns at most five items, classifies urgent L3/L4 as `action`, classifies other L3 as `watch`, counts pending clusters as `verifying`, and never uses the cluster/news title as the risk-card title.

- [ ] **Step 2: Run the controller tests and verify RED**

Run: `$env:PYTHONPATH='src'; python tests/test_cognition.py -v`

Expected: FAIL because `CognitionController.risk_dashboard` does not exist.

- [ ] **Step 3: Implement the minimal projection**

Query only the latest judgment and current personal impacts, excluding muted and `false_positive` rows. Parse `content_json`, `candidate_json` and `components_json`. Build each item with:

```python
{
    "cluster_id": str,
    "impact_id": str,
    "mode": "action" | "watch",
    "risk_level": "高风险" | "需留意",
    "interest_name": str,
    "title": f"{interest_name}：{fact_summary}",
    "time_window": "今天" | "7 天内" | "30 天内" | "更长期",
    "confidence": "较高" | "中等" | "仍在核实",
    "action": str,
    "direction": "风险上升" | "没有明显变化" | "风险缓解",
    "decision_by": str,
    "updated_at": str,
}
```

Use judgment horizons and triggers for time/direction. Use the candidate action when non-empty; otherwise use `暂不做不可逆决定；按时间窗口复查。`. Sort action before watch, then L4 before L3, then score descending and update time descending. Clamp `limit` to 1–5.

Set the overall state to `coverage_gap` when enabled sources exist but none is healthy, otherwise `action`, `watch` or `stable`. Write a one-sentence summary matching the state.

- [ ] **Step 4: Run controller tests and verify GREEN**

Run: `$env:PYTHONPATH='src'; python tests/test_cognition.py -v`

Expected: PASS.

- [ ] **Step 5: Write the failing HTTP contract test**

Assert that `GET /api/risk-dashboard` requires the session token and returns the projection with source coverage from `services.external.list_sources()`. Confirm no `canonical_url`, raw source error or watch-rule payload appears in the response.

- [ ] **Step 6: Run the HTTP test and verify RED**

Run: `$env:PYTHONPATH='src'; python tests/test_http_api.py HttpApiTests.test_risk_dashboard_returns_decisions_without_raw_news -v`

Expected: FAIL with HTTP 404.

- [ ] **Step 7: Add the authenticated route and verify GREEN**

In `do_GET`, call:

```python
source_states = services.external.list_sources() if services.external else []
self._json(services.cognition_controller.risk_dashboard(source_states, limit=5))
```

Run the targeted HTTP test, then both cognition and HTTP modules.

- [ ] **Step 8: Commit**

```powershell
git add -- src/yuanjian_app/cognition.py src/yuanjian_app/http_api.py tests/test_cognition.py tests/test_http_api.py
git commit -m "feat: project external intelligence into personal risks"
```

### Task 2: Pure front-end risk presentation helpers

**Files:**
- Create: `src/yuanjian_app/static/risk_ui.js`
- Modify: `src/yuanjian_app/http_api.py`
- Modify: `build/yuanjian.spec`
- Modify: `tests/test_frontend.py`
- Modify: `tests/test_http_api.py`

**Interfaces:**
- Produces: `window.YuanJianRiskUI.overviewLabel(state) -> string`
- Produces: `window.YuanJianRiskUI.counts(dashboard) -> Array<{key,value,label}>`
- Produces: `window.YuanJianRiskUI.visibleRisks(items) -> Array<object>`
- Produces: local static route `/risk_ui.js`.

- [ ] **Step 1: Write failing Node tests**

Assert state labels `需要行动`, `继续观察`, `目前平稳`, `监控覆盖不足`; count labels `现在要处理`, `继续观察`, `系统核实中`; and `visibleRisks` removes L1/L2, orders action first and returns no more than five items.

- [ ] **Step 2: Run and verify RED**

Run: `python tests/test_frontend.py -v`

Expected: FAIL because `risk_ui.js` is missing.

- [ ] **Step 3: Implement the pure UMD helper**

Implement only the four labels, stable filtering/sorting, defensive numeric conversion and five-item limit. Do not access DOM or network.

- [ ] **Step 4: Run and verify GREEN**

Run: `python tests/test_frontend.py -v`

Expected: PASS.

- [ ] **Step 5: Add asset route and package inclusion test first**

Add failing assertions that `/risk_ui.js` returns HTTP 200 and `index.html` loads it before `app.js`; then update the static route and PyInstaller data list if the spec does not already include the whole static directory.

- [ ] **Step 6: Run static and build tests**

Run: `$env:PYTHONPATH='src'; python tests/test_http_api.py tests/test_build_config.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add -- src/yuanjian_app/static/risk_ui.js src/yuanjian_app/http_api.py build/yuanjian.spec tests/test_frontend.py tests/test_http_api.py
git commit -m "feat: add risk cockpit presentation model"
```

### Task 3: Replace the default screen and primary navigation

**Files:**
- Modify: `src/yuanjian_app/static/index.html`
- Modify: `src/yuanjian_app/static/app.js`
- Modify: `src/yuanjian_app/static/styles.css`
- Test: `tests/test_http_api.py`
- Test: `tests/test_frontend.py`

**Interfaces:**
- Consumes: `GET /api/risk-dashboard` and `window.YuanJianRiskUI`.
- Produces: `renderRiskHome(runNotice = null)` as the default renderer.

- [ ] **Step 1: Write failing home-page structure tests**

Assert exactly three primary navigation buttons labeled `风险首页`, `我的情况`, `设置`. Assert `外部世界`, `来源健康状态`, `关注规则`, search controls and raw event filters do not appear in initial HTML. Assert `risk_ui.js` is loaded.

- [ ] **Step 2: Run and verify RED**

Run: `$env:PYTHONPATH='src'; python tests/test_http_api.py HttpApiTests.test_home_page_is_a_three_entry_risk_cockpit -v`

Expected: FAIL because four navigation entries still exist.

- [ ] **Step 3: Replace navigation and initial shell**

Keep views `today`, `benefit`, `system`, relabel them, remove the `world` primary button, update the header copy, and replace the initial placeholder with a risk-summary loading state.

- [ ] **Step 4: Write failing render-contract tests**

Assert `app.js` requests `/api/risk-dashboard`, contains the exact user labels, renders no raw cluster list/search/pagination on the default page, and routes the default initial call through `renderRiskHome()`.

- [ ] **Step 5: Run and verify RED**

Run: `$env:PYTHONPATH='src'; python tests/test_http_api.py -v`

Expected: FAIL on the old news-centric render contract.

- [ ] **Step 6: Implement risk-home rendering**

Render a top status panel, three static count cards and at most five `.risk-card` elements. Each card must contain interest, risk label, time, confidence, direction, action and buttons `查看怎么做` and `为什么这样判断`. An empty dashboard must show only the stable/coverage message, never raw news.

- [ ] **Step 7: Simplify interaction wiring**

Remove default metric filtering, cluster searching, raw event pagination and notification-list switching from the home view. Keep `立即更新判断` and refresh `renderRiskHome` after completion. The notification header opens the settings notification subview.

- [ ] **Step 8: Add focused cockpit styles**

Use one status banner, one three-column count strip and a single-column risk-card list. Keep card actions visually secondary to the recommendation. Preserve responsive behavior below 980px and 620px.

- [ ] **Step 9: Run targeted tests and commit**

Run: `python tests/test_frontend.py -v`

Run: `$env:PYTHONPATH='src'; python tests/test_http_api.py -v`

```powershell
git add -- src/yuanjian_app/static/index.html src/yuanjian_app/static/app.js src/yuanjian_app/static/styles.css tests/test_frontend.py tests/test_http_api.py
git commit -m "feat: make personal risks the only default workload"
```

### Task 4: Layer risk details and lazy-load the intelligence back office

**Files:**
- Modify: `src/yuanjian_app/static/app.js`
- Modify: `src/yuanjian_app/static/styles.css`
- Test: `tests/test_http_api.py`
- Test: `tests/test_frontend.py`

**Interfaces:**
- Produces: simplified `showClusterDetail(id, evidenceOpen = false)`.
- Produces: settings subview `intelligence` that does not fetch raw radar data until explicitly opened.

- [ ] **Step 1: Write failing detail hierarchy tests**

Assert the default risk detail contains `对你的影响`, `现在怎么做`, `最迟决定时间`, `升级或解除条件`; evidence sits inside a closed `<details>` labeled `为什么这样判断`; raw source links occur only inside that details section.

- [ ] **Step 2: Run and verify RED**

Run: `python tests/test_frontend.py -v`

Expected: FAIL because evidence and analysis are always expanded.

- [ ] **Step 3: Implement the two-layer detail**

Use the selected impact and judgment to put action and decision timing first. Keep feedback controls. Move fact summary, causal chain, uncertainty and source links into one closed evidence `<details>` element.

- [ ] **Step 4: Write failing intelligence-back-office tests**

Assert the settings subnav contains `情报后台`, the initial back-office screen calls only cognition status and external source summary, and raw radar/rules are requested only after `查看原始情报` or `管理来源` is clicked.

- [ ] **Step 5: Run and verify RED**

Run: `$env:PYTHONPATH='src'; python tests/test_http_api.py -v`

Expected: FAIL because `renderWorld` eagerly loads and renders everything.

- [ ] **Step 6: Implement lazy back-office disclosure**

Move `renderWorld` behind the `system` subview `intelligence`. First render only processed counts, healthy/retry counts and pending-judgment count. Add two explicit buttons which reveal and fetch raw intelligence or source/rule management. Preserve existing source refresh, pause, add-source and add-rule actions after expansion.

- [ ] **Step 7: Run targeted tests and commit**

Run: `python tests/test_frontend.py -v`

Run: `$env:PYTHONPATH='src'; python tests/test_http_api.py -v`

```powershell
git add -- src/yuanjian_app/static/app.js src/yuanjian_app/static/styles.css tests/test_frontend.py tests/test_http_api.py
git commit -m "feat: hide evidence and raw intelligence until requested"
```

### Task 5: Version, documentation, full verification and packaged acceptance

**Files:**
- Modify: `src/yuanjian_app/__init__.py`
- Modify: `src/yuanjian_app/http_api.py`
- Modify: `README.md`
- Modify: `使用说明.md`
- Create: `docs/releases/YuanJian-v0.8-verification.md`
- Modify: `tests/test_build_config.py`

**Interfaces:**
- Produces: version `0.8.0`, server identifier `YuanJian/0.8`, final portable package `YuanJianApp-v0.8/YuanJian.exe`.

- [ ] **Step 1: Write failing version tests**

Change the expected application version to `0.8.0`, expected server version to `YuanJian/0.8`, and packaged default view to `today` risk home.

- [ ] **Step 2: Run and verify RED**

Run: `$env:PYTHONPATH='src'; python tests/test_build_config.py -v`

Expected: FAIL on version 0.7.

- [ ] **Step 3: Update version and user documentation**

Explain that the user normally reads only the risk home page, raw intelligence lives under settings, and closing the window still minimizes to tray. Keep technical setup details in README, not the first-run user instructions.

- [ ] **Step 4: Run the complete source verification**

Run: `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests`

Run: `git diff --check`

Expected: all tests PASS and no whitespace errors.

- [ ] **Step 5: Run privacy checks**

Copy only `git ls-files` into a fresh temporary directory and run `python tools/privacy_scan.py <temp-dir>`. Search tracked source for the previously supplied private addresses, exact birthdays and financial figures. Expected: `safe=True blocked=0 findings=0` and zero targeted matches.

- [ ] **Step 6: Build and smoke-test v0.8**

Run: `powershell -ExecutionPolicy Bypass -File build\build_windows.ps1`

Copy `dist\YuanJian` to the versioned output directory `YuanJianApp-v0.8`, preserving v0.7. Run:

```powershell
powershell -ExecutionPolicy Bypass -File tools\smoke_packaged.ps1 -ExePath '<absolute-output>\YuanJianApp-v0.8\YuanJian.exe'
```

Expected: database true, one loopback listener, HTTP 200, no remote scripts, default view `today`, local fallback, second-instance exit 0 and safe shutdown.

- [ ] **Step 7: Perform real desktop acceptance**

Use a temporary copy of the private runtime database. Verify three primary navigation entries, risk status/counts, no raw news on home, one risk detail with evidence closed by default, settings intelligence summary, explicit expansion of raw intelligence, close-to-tray, restore and safe exit. Remove the temporary database after exit.

- [ ] **Step 8: Record release evidence and commit**

Record test count, privacy result, smoke JSON, desktop checklist, executable size and SHA-256 in `docs/releases/YuanJian-v0.8-verification.md`.

```powershell
git add -- src/yuanjian_app/__init__.py src/yuanjian_app/http_api.py README.md '使用说明.md' tests/test_build_config.py docs/releases/YuanJian-v0.8-verification.md
git commit -m "release: verify YuanJian 0.8 risk cockpit"
```
