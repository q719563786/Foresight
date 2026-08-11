# 远见 0.7 使用体验重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把远见桌面端从一次铺开大量原始信息的后台页面，改成可筛选、可处理、可解释的个人利益行动中心。

**Architecture:** 后端服务增加统一的纯文本边界与 SQL 分页筛选，HTTP API 返回兼容旧字段的分页结果；前端拆出可由 Node 测试的格式化状态模块，重写页面骨架、路由和 CSS。数据库表保持不变，旧数据只在读取时清洗，新数据在写入时清洗。

**Tech Stack:** Python 3 标准库、SQLite、`unittest`、原生 HTML/CSS/JavaScript、Node `assert`、pywebview、PyInstaller、Windows CUA 验收。

## Global Constraints

- 服务只绑定 `127.0.0.1`，全部 `/api/` 请求继续要求 `X-YuanJian-Token`。
- 不删除或重命名数据库表，不批量覆盖私人数据库。
- 不关闭 TLS、不绕过反爬，真实保留来源失败状态。
- API 密钥、私人利益、地址、医疗、债务、Obsidian 原文和数据库不得进入源码或 GitHub。
- GitHub 仓库保持 private；0.7 发布到新目录，0.5 与 0.6 保留。
- 所有行为改动必须先看到相关测试因缺少该行为而失败，再写生产代码。

---

### Task 1: 统一纯文本边界

**Files:**
- Create: `src/yuanjian_app/text_cleaning.py`
- Modify: `src/yuanjian_app/external_radar.py`
- Modify: `src/yuanjian_app/cognition.py`
- Create: `tests/test_text_cleaning.py`
- Modify: `tests/test_external_radar.py`
- Modify: `tests/test_cognition.py`

**Interfaces:**
- Produces: `plain_text(value: object, max_length: int | None = None) -> str`
- Consumed by: external item storage and cognition serializers.

- [ ] **Step 1: Write failing unit tests for HTML removal and safe truncation**

```python
from yuanjian_app.text_cleaning import plain_text

def test_plain_text_removes_markup_script_and_decodes_entities():
    value = '<a href="x">政策&nbsp;更新</a><script>bad()</script>'
    assert plain_text(value) == "政策 更新"

def test_plain_text_truncates_without_leaving_extra_space():
    assert plain_text("  一 二 三  ", max_length=3) == "一 二…"
```

- [ ] **Step 2: Run the new tests and verify import failure**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_text_cleaning -v`

Expected: FAIL because `yuanjian_app.text_cleaning` does not exist.

- [ ] **Step 3: Implement the standard-library cleaner**

```python
class _VisibleTextParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}: self.hidden += 1
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)

def plain_text(value, max_length=None):
    parser = _VisibleTextParser()
    parser.feed(html.unescape(str(value or "")))
    cleaned = " ".join("".join(parser.parts).split())
    return cleaned if not max_length or len(cleaned) <= max_length else cleaned[: max_length - 1].rstrip() + "…"
```

- [ ] **Step 4: Add failing integration assertions for new and historical items**

Insert `<a>标题</a>` and `<font>摘要</font>` through `ExternalRadarService`, and directly into an existing cluster row; assert `radar_items()` and `list_clusters_page()` return only visible text.

- [ ] **Step 5: Apply cleaning at write and serialization boundaries**

Call `plain_text(item.title, 300)` and `plain_text(item.summary, 2000)` before hashing/storing, and clean cluster/item dictionaries before API use without rewriting historical rows.

- [ ] **Step 6: Run focused and full tests**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_text_cleaning tests.test_external_radar tests.test_cognition -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/yuanjian_app/text_cleaning.py src/yuanjian_app/external_radar.py src/yuanjian_app/cognition.py tests/test_text_cleaning.py tests/test_external_radar.py tests/test_cognition.py
git commit -m "fix: keep external evidence text readable"
```

### Task 2: 后端分页、筛选与通知闭环

**Files:**
- Modify: `src/yuanjian_app/cognition.py`
- Modify: `src/yuanjian_app/external_radar.py`
- Modify: `src/yuanjian_app/notifications.py`
- Modify: `src/yuanjian_app/http_api.py`
- Modify: `tests/test_cognition.py`
- Modify: `tests/test_external_radar.py`
- Modify: `tests/test_notifications.py`
- Modify: `tests/test_http_api.py`

**Interfaces:**
- Produces: `CognitionService.list_clusters_page(limit=10, offset=0, query="", category="", evidence="", needs_judgment=None) -> dict`
- Produces: `ExternalRadarService.radar_page(limit=10, offset=0, query="") -> dict`
- Produces: `NotificationService.list_page(limit=20, offset=0, status="") -> dict`
- Produces: `NotificationService.mark_all_read() -> dict`

- [ ] **Step 1: Write failing service tests with literal totals and page contents**

```python
page = service.list_clusters_page(limit=1, offset=1, query="医保", needs_judgment=True)
self.assertEqual(page["total"], 2)
self.assertEqual(len(page["items"]), 1)
self.assertTrue(page["items"][0]["needs_judgment"])
```

Also assert `limit=0`, `limit=101`, negative offset, invalid evidence and invalid notification status raise `ValueError`.

- [ ] **Step 2: Run service tests and verify missing-method failures**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_cognition tests.test_external_radar tests.test_notifications -v`

- [ ] **Step 3: Implement parameterized SQL paging**

Build `WHERE` clauses from validated values, run a `COUNT(*)` query, then the matching ordered `LIMIT ? OFFSET ?` query. Keep `list_clusters(limit)` and `radar_items(limit)` as compatibility wrappers that return `page["items"]`.

- [ ] **Step 4: Implement notification status filtering and batch read**

```python
def mark_all_read(self):
    now = _iso(self.now())
    with self.database.connect() as connection:
        result = connection.execute(
            "UPDATE notification_log SET status='read',read_at=? WHERE status='unread'",
            (now,),
        )
    return {"status": "read", "updated": result.rowcount}
```

- [ ] **Step 5: Write failing HTTP tests for query parsing and `read-all`**

Use the real loopback server. Assert pagination metadata, filtered payloads, 400 for invalid parameters, 403 without token, and a successful `POST /api/notifications/read-all` changes the unread count.

- [ ] **Step 6: Wire validated query parameters into HTTP routes**

Parse `limit`, `offset`, `q`, `category`, `evidence`, `needs_judgment`, and `status`; return `clusters` as an alias of `items` for compatibility. Match `/api/notifications/read-all` before the single-notification route.

- [ ] **Step 7: Run focused and full tests**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_http_api tests.test_cognition tests.test_external_radar tests.test_notifications -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/yuanjian_app/cognition.py src/yuanjian_app/external_radar.py src/yuanjian_app/notifications.py src/yuanjian_app/http_api.py tests/test_cognition.py tests/test_external_radar.py tests/test_notifications.py tests/test_http_api.py
git commit -m "feat: paginate radar and complete notification actions"
```

### Task 3: 可测试的中文表达与页面状态

**Files:**
- Create: `src/yuanjian_app/static/ui_core.js`
- Modify: `src/yuanjian_app/http_api.py`
- Modify: `tests/test_frontend.py`
- Modify: `tests/test_http_api.py`

**Interfaces:**
- Produces: `YuanJianUI.evidenceLabel`, `trendLabel`, `statusLabel`, `formatLocalTime`, `buildQuery`, `pageRange`.
- Consumed by: rewritten `app.js`.

- [ ] **Step 1: Write failing Node behavior tests**

```javascript
assert.equal(ui.evidenceLabel('E2'), 'E2 · 多源互证');
assert.equal(ui.trendLabel('low_sample'), '样本积累中');
assert.equal(ui.statusLabel('active'), '有效');
assert.equal(ui.buildQuery({limit:10, offset:0, q:'医保', evidence:''}), '?limit=10&offset=0&q=%E5%8C%BB%E4%BF%9D');
assert.equal(ui.formatLocalTime('2026-08-12T01:20:00Z', new Date('2026-08-12T04:00:00Z'), 0), '今天 01:20');
```

- [ ] **Step 2: Run and verify missing-module failure**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_frontend -v`

- [ ] **Step 3: Implement a browser/Node UMD module**

Export a frozen API with literal translation maps, local date formatting and omission of empty query values. Avoid DOM dependencies so tests use real functions.

- [ ] **Step 4: Add `/ui_core.js` static route and HTTP test**

Assert the route returns JavaScript from the local package and `index.html` references it before `app.js`.

- [ ] **Step 5: Run focused tests and commit**

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_frontend tests.test_http_api -v
git add src/yuanjian_app/static/ui_core.js src/yuanjian_app/http_api.py tests/test_frontend.py tests/test_http_api.py
git commit -m "feat: add user-facing labels and date formatting"
```

### Task 4: 重写行动中心与四组导航

**Files:**
- Modify: `src/yuanjian_app/static/index.html`
- Modify: `src/yuanjian_app/static/app.js`
- Modify: `src/yuanjian_app/static/styles.css`
- Modify: `tests/test_frontend.py`
- Modify: `tests/test_http_api.py`

**Interfaces:**
- Consumes: all Task 2 page endpoints and Task 3 formatting functions.
- Produces: routes `today`, `world`, `benefit`, `system`; metric filter state; global toast and loading state.

- [ ] **Step 1: Write failing browser-contract and state tests**

Assert the served home contains four primary navigation buttons, three metric buttons with `data-filter`, global `aria-live` toast, search and filter controls, notification entry, and no 11-item flat navigation. In Node, assert `metricFilter('unread')` produces `{notification_status:'unread'}` and resets offset to zero.

- [ ] **Step 2: Run tests and verify the old DOM fails the contract**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_frontend tests.test_http_api -v`

- [ ] **Step 3: Replace the HTML shell**

Use semantic `<aside>`, `<nav>`, `<main>`, native buttons, a compact header status, `#content`, `#toast`, and `#loading`. Keep all scripts local for the existing CSP.

- [ ] **Step 4: Rewrite the CSS as maintainable sections**

Define color/type tokens, desktop navigation, buttons, metrics, toolbar, event rows, side action queue, detail layout, forms, toast, skeleton and responsive rules. At `max-width: 820px` move navigation to a compact top row; at `max-width: 560px` stack metrics and filters. Do not set fixed content widths or allow body-level horizontal scrolling.

- [ ] **Step 5: Rewrite the primary route and render pipeline**

Implement `setView`, `renderToday`, `renderWorld`, `renderBenefit`, `renderSystem`, `withBusy`, `showToast`, and `showPageError`. `renderToday` fetches status, first 10 clusters, trends and unread notifications; metrics call the same render function with filters.

- [ ] **Step 6: Keep existing low-frequency features reachable**

Expose signals, interests, knowledge, create forecast, forecasts and score through secondary navigation inside the corresponding primary group, reusing their current forms and service calls.

- [ ] **Step 7: Replace blocking feedback**

Remove `alert` and non-destructive `confirm` calls. Show success/error through `#toast`; disable action buttons during requests and restore them in `finally`.

- [ ] **Step 8: Run tests and commit**

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_frontend tests.test_http_api -v
git add src/yuanjian_app/static/index.html src/yuanjian_app/static/app.js src/yuanjian_app/static/styles.css tests/test_frontend.py tests/test_http_api.py
git commit -m "feat: turn the desktop home into an action center"
```

### Task 5: 通知、外部世界、详情与设置交互

**Files:**
- Modify: `src/yuanjian_app/static/app.js`
- Modify: `src/yuanjian_app/static/styles.css`
- Modify: `tests/test_frontend.py`
- Modify: `tests/test_http_api.py`

**Interfaces:**
- Consumes: paged notifications/radar/clusters and batch read endpoints.
- Produces: notification center, source-health page, detail back navigation and consistent form controls.

- [ ] **Step 1: Write failing state tests**

Test pagination boundaries, preserving search/filter during next page, changing notification rows to read after a successful action, and source failures mapping to “待重试” rather than “没有消息”.

- [ ] **Step 2: Run and verify expected failures**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_frontend tests.test_http_api -v`

- [ ] **Step 3: Implement notification center**

Render only unread/all toggle, 20-row page, mark-read, mark-all-read and open-related-event actions. Refresh header and metric counts after writes.

- [ ] **Step 4: Implement external source health and paged raw feed**

Separate filtered radar from source management. Preserve exact failure message and next retry time; add search, previous/next pagination and source refresh busy state.

- [ ] **Step 5: Implement event detail and settings polish**

Add explicit back button, public evidence/local impact separation, inline feedback results, `.form-check` checkbox layout, consistent startup button, and safe exit confirmation only for actual shutdown.

- [ ] **Step 6: Run focused/full tests and commit**

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests
git add src/yuanjian_app/static/app.js src/yuanjian_app/static/styles.css tests/test_frontend.py tests/test_http_api.py
git commit -m "feat: complete desktop interaction workflows"
```

### Task 6: 文档、版本与隐私审计

**Files:**
- Modify: `README.md`
- Modify: `使用说明.md`
- Modify: `ARCHITECTURE.md`
- Modify: `src/yuanjian_app/__init__.py`
- Create: `docs/releases/YuanJian-v0.7-verification.md`
- Modify: `tests/test_build_config.py`

**Interfaces:**
- Produces: 0.7 user instructions, architectural boundary notes and release checklist.

- [ ] **Step 1: Write failing version/package assertion**

Assert the package version and build metadata report `0.7.0`, then run `tests.test_build_config` to see the old version fail.

- [ ] **Step 2: Update version and user documentation**

Explain the four entrances, clickable indicators, filters, notification processing, source failure meaning, tray behavior and rollback to 0.6. Keep instructions nontechnical.

- [ ] **Step 3: Run privacy scan and source search**

Run: `$env:PYTHONPATH='src'; python tools/privacy_scan.py .`

Run targeted `rg` for the user-supplied addresses, birth dates, balances, phone/account patterns, tokens and SQLite files. Expected: no private match or artifact.

- [ ] **Step 4: Run full tests and commit**

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests
git add README.md 使用说明.md ARCHITECTURE.md src/yuanjian_app/__init__.py docs/releases/YuanJian-v0.7-verification.md tests/test_build_config.py
git commit -m "docs: prepare YuanJian 0.7 release"
```

### Task 7: 打包、真实桌面验收与私有发布

**Files:**
- Modify: `docs/releases/YuanJian-v0.7-verification.md`
- Output only: `../YuanJianApp-v0.7/YuanJian.exe`

**Interfaces:**
- Produces: verified Windows desktop package and private GitHub branch/main history.

- [ ] **Step 1: Read the verification skill and run the pristine full suite**

Run: `$env:PYTHONPATH='src'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest discover -s tests`

Record exact test count, duration and exit code.

- [ ] **Step 2: Build a new output directory**

Run the existing `build/build_windows.ps1` with a versioned output path resolving to `YuanJianApp-v0.7`. Do not overwrite 0.5 or 0.6.

- [ ] **Step 3: Run packaged smoke tests**

Run `tools/smoke_packaged.ps1` against the new executable using an isolated temporary runtime directory. Verify loopback token, static assets, headless health and clean shutdown.

- [ ] **Step 4: Run real GUI acceptance on isolated data**

Launch the packaged executable with a temporary runtime path. With CUA verify: four navigation entries, metrics filter the list, search gives a visible result/empty state, next page has no horizontal overflow, notifications can be marked read, settings checkboxes align, close hides to tray, tray restores and safe exit stops the process.

- [ ] **Step 5: Hash and document the package**

Record absolute path, SHA-256, file size, build time, tests, privacy scan, CUA checks, and rollback path in `docs/releases/YuanJian-v0.7-verification.md`.

- [ ] **Step 6: Final review, commit and private publish**

Run `git diff --check`, full tests, privacy scan, package smoke, `git status --short`, and `gh repo view --json visibility`. Commit the evidence, merge the feature branch only after all checks pass, push to the existing private repository, and verify `visibility` remains `PRIVATE`.
