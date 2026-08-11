# YuanJian v0.6 Desktop Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace YuanJian's default-browser UI with a pywebview Windows desktop window that closes to the tray, keeps monitoring, wakes on a second launch, and makes manual cognition visibly responsive.

**Architecture:** Keep the existing loopback HTTP API, scheduler, SQLite database, and web UI. Add a dependency-isolated `DesktopShell` that owns pywebview and pystray, add authenticated local window-control endpoints for second-instance wakeup, and serialize scheduled/manual cognition through one lock. GUI libraries are lazy-imported so core tests stay headless.

**Tech Stack:** Python 3.14, pywebview 6.2.1, pystray 0.19.5, Pillow, stdlib `http.server`/`urllib`, SQLite, vanilla JavaScript, PyInstaller 6.21.0.

## Global Constraints

- The program must listen only on `127.0.0.1`; never bind a LAN interface.
- Closing the window hides it to the tray; only “退出远见” and “安全退出” stop the process.
- Login startup launches hidden and leaves monitoring active.
- No browser fallback when WebView2 initialization fails; show a Chinese error and exit safely.
- Keep `%LOCALAPPDATA%\YuanJian` data and schema unchanged.
- External AI stays disabled by default and receives no private context.
- Implement every production behavior only after its regression test fails for the expected reason.
- Produce `YuanJianApp-v0.6` without overwriting `YuanJianApp-v0.5`.

---

### Task 1: Desktop lifecycle independent of GUI libraries

**Files:**
- Create: `src/yuanjian_app/desktop.py`
- Create: `tests/test_desktop.py`

**Interfaces:**
- Consumes: callbacks `run_cognition: Callable[[], dict]`, `pause_monitoring`, `resume_monitoring`, `request_shutdown`.
- Produces: `DesktopLifecycle(window, tray, monitor, run_cognition, request_shutdown)`, methods `close_to_tray() -> bool`, `show_window()`, `run_cognition_once() -> dict`, `toggle_monitoring() -> bool`, `request_exit()`.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_close_hides_window_and_keeps_process_alive(self):
    lifecycle = self.make_lifecycle()
    self.assertFalse(lifecycle.close_to_tray())
    self.assertEqual(self.window.calls, ["hide"])
    self.assertFalse(self.shutdown.called)

def test_tray_exit_stops_tray_and_requests_safe_shutdown(self):
    lifecycle = self.make_lifecycle()
    lifecycle.request_exit()
    self.assertEqual(self.tray.calls, ["stop"])
    self.assertTrue(self.shutdown.called)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_desktop -v`

Expected: import failure for `yuanjian_app.desktop`.

- [ ] **Step 3: Implement the state machine**

```python
class DesktopLifecycle:
    def close_to_tray(self):
        if self.exiting:
            return True
        self.window.hide()
        return False

    def show_window(self):
        self.window.show()
        self.window.restore()

    def request_exit(self):
        if self.exiting:
            return
        self.exiting = True
        self.tray.stop()
        self.request_shutdown()
```

Generate the tray image in memory with Pillow; do not add a binary asset. Keep all `webview`, `pystray`, and Pillow imports inside the concrete adapter factory.

- [ ] **Step 4: Run the focused tests and full suite**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_desktop -v`

Run: `$env:PYTHONPATH='src'; $env:PYTHONWARNINGS='error::ResourceWarning'; python -m unittest discover -s tests -q`

Expected: all tests pass with no warnings.

- [ ] **Step 5: Commit only Task 1 files**

```powershell
git add -- src/yuanjian_app/desktop.py tests/test_desktop.py
git commit -m "feat: add desktop lifecycle state machine"
```

### Task 2: Serialize cognition and pause automatic monitoring

**Files:**
- Create: `src/yuanjian_app/operations.py`
- Create: `tests/test_operations.py`
- Modify: `src/yuanjian_app/radar_scheduler.py`
- Modify: `tests/test_radar_scheduler.py`

**Interfaces:**
- Consumes: `CognitionController.process_once() -> dict`, scheduler callbacks.
- Produces: `CognitionOperation.run(source: str) -> dict`, raising `OperationBusy`; `RadarScheduler.pause()`, `resume()`, `paused: bool`.

- [ ] **Step 1: Write failing single-flight and pause tests**

```python
def test_second_cognition_run_is_rejected_while_first_is_active(self):
    operation = CognitionOperation(self.blocking_controller)
    worker = threading.Thread(target=operation.run, args=("manual",))
    worker.start()
    self.started.wait(1)
    with self.assertRaises(OperationBusy):
        operation.run("scheduled")

def test_paused_scheduler_skips_automatic_callbacks(self):
    scheduler.pause()
    self.assertEqual(scheduler.run_external_once(), {"status": "paused"})
    self.assertEqual(scheduler.run_cognition_once(), {"status": "paused"})
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_operations tests.test_radar_scheduler -v`

Expected: missing `operations` module and missing `pause` method.

- [ ] **Step 3: Implement minimal synchronization**

```python
class CognitionOperation:
    def run(self, source="manual"):
        if not self._lock.acquire(blocking=False):
            raise OperationBusy("认知任务正在运行")
        started = time.monotonic()
        try:
            return {**self.controller.process_once(), "source": source,
                    "elapsed_ms": round((time.monotonic() - started) * 1000)}
        finally:
            self._lock.release()
```

Use one shared instance for tray, HTTP, and scheduler calls. Scheduler pause affects only automatic runs; tray/manual runs remain available.

- [ ] **Step 4: Verify focused and full tests**

Run the two commands from Step 2, then the full warning-as-error suite.

- [ ] **Step 5: Commit Task 2 files**

```powershell
git add -- src/yuanjian_app/operations.py src/yuanjian_app/radar_scheduler.py tests/test_operations.py tests/test_radar_scheduler.py
git commit -m "feat: serialize cognition and pause monitoring"
```

### Task 3: Authenticated window control and second-launch wakeup

**Files:**
- Modify: `src/yuanjian_app/http_api.py`
- Modify: `src/yuanjian_app/runtime.py`
- Modify: `tests/test_http_api.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Consumes: `Services.desktop`, `Services.cognition_operation`, runtime `{port, token}`.
- Produces: `POST /api/window/show`, `POST /api/monitoring/toggle`, revised `POST /api/cognition/run`; `RuntimeClient(runtime).show_window() -> bool`.

- [ ] **Step 1: Write failing API and runtime-client tests**

```python
def test_window_show_requires_token_and_calls_desktop(self):
    status, _ = self.post_json("/api/window/show", {}, token="wrong")
    self.assertEqual(status, 403)
    status, payload = self.post_json("/api/window/show", {})
    self.assertEqual((status, payload["status"]), (200, "shown"))
    self.assertEqual(self.desktop.shown, 1)

def test_runtime_client_posts_token_to_existing_instance(self):
    client = RuntimeClient(self.runtime, opener=self.opener)
    self.assertTrue(client.show_window())
    self.assertEqual(self.opener.request.full_url, "http://127.0.0.1:4567/api/window/show")
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_http_api tests.test_runtime -v`

Expected: missing route and `RuntimeClient`.

- [ ] **Step 3: Implement routes and loopback client**

Use `urllib.request.Request` with `X-YuanJian-Token`, JSON body `{}`, a two-second timeout, and an exact `127.0.0.1` URL built from validated integer port. Do not log the token. Return `False` on connection failure so a stale runtime file cannot crash startup.

Map `OperationBusy` to HTTP 409 with the Chinese message `认知任务正在运行，请稍候`.

- [ ] **Step 4: Verify focused and full tests**

Run the focused command, then the full suite.

- [ ] **Step 5: Commit Task 3 files**

```powershell
git add -- src/yuanjian_app/http_api.py src/yuanjian_app/runtime.py tests/test_http_api.py tests/test_runtime.py
git commit -m "feat: add authenticated desktop control endpoints"
```

### Task 4: Integrate pywebview and tray with application startup

**Files:**
- Modify: `src/yuanjian_app/desktop.py`
- Modify: `src/yuanjian_app/application.py`
- Modify: `tests/test_desktop.py`
- Modify: `tests/test_application.py`

**Interfaces:**
- Consumes: `Application.url`, scheduler, server, runtime discovery, `DesktopLifecycle`.
- Produces: `PyWebViewDesktop.run(url: str, hidden: bool)`, `Application.run_desktop(hidden=False)`, second-instance wakeup.

- [ ] **Step 1: Write failing integration tests with injected adapters**

```python
def test_normal_launch_uses_desktop_and_never_default_browser(self):
    app = self.make_application(desktop=self.desktop)
    app.run()
    self.assertEqual(self.desktop.run_calls[0]["hidden"], False)
    self.assertEqual(self.browser.calls, [])

def test_background_launch_starts_desktop_hidden(self):
    app = self.make_application(desktop=self.desktop, background=True)
    app.run()
    self.assertTrue(self.desktop.run_calls[0]["hidden"])
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_desktop tests.test_application -v`

Expected: browser call remains or desktop run interface is absent.

- [ ] **Step 3: Implement concrete adapters and application wiring**

Create the window with title `远见 · 外部认知大脑`, minimum size `(900, 620)`, default size `1180 x 780`, and `gui="edgechromium"`. Register `window.events.closing` to `close_to_tray`. Start the HTTP server and scheduler on managed background threads before `webview.start`; stop and join them in one `finally` path.

When the single-instance lock is already held, call `RuntimeClient(existing).show_window()` and exit instead of opening a browser.

Catch WebView initialization errors at the outer boundary, show one Windows message box with `远见无法启动桌面窗口，请安装或修复 Microsoft Edge WebView2 Runtime`, and leave no runtime file or lock behind.

- [ ] **Step 4: Verify focused and full tests**

Run the focused command, then the full suite.

- [ ] **Step 5: Commit Task 4 files**

```powershell
git add -- src/yuanjian_app/desktop.py src/yuanjian_app/application.py tests/test_desktop.py tests/test_application.py
git commit -m "feat: launch YuanJian in a desktop webview"
```

### Task 5: Make manual cognition visibly responsive

**Files:**
- Modify: `src/yuanjian_app/static/app.js`
- Modify: `src/yuanjian_app/static/styles.css`
- Modify: `tests/test_http_api.py`

**Interfaces:**
- Consumes: cognition response fields `backfill.processed`, `queued`, `judgments`, `mapped_impacts`, `notifications_created`, `elapsed_ms`.
- Produces: visible `#cognition-run-status`, busy button, completion/zero/error summaries.

- [ ] **Step 1: Add a failing front-end contract test**

```python
def test_cognition_button_has_busy_success_error_and_finally_states(self):
    script = self.fetch_text("/static/app.js")
    self.assertIn("正在运行认知", script)
    self.assertIn("cognition-run-status", script)
    self.assertIn("运行完成，本次没有新增待处理信息", script)
    self.assertIn("finally", script)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_http_api.HttpApiTests.test_cognition_button_has_busy_success_error_and_finally_states -v`

Expected: assertion failure because status rendering is absent.

- [ ] **Step 3: Implement feedback with `try/catch/finally`**

```javascript
button.disabled = true;
button.textContent = '正在运行认知…';
status.textContent = '正在聚合信息、核验证据并映射个人利益…';
try {
  const result = await api('/api/cognition/run', {method:'POST', body:'{}'});
  status.textContent = summarizeCognitionRun(result);
} catch (error) {
  status.textContent = `运行失败：${error.message}`;
  status.className = 'run-status error';
} finally {
  button.disabled = false;
  button.textContent = '立即运行认知';
}
```

Add an elapsed-time counter updated every second and always clear it in `finally`. Preserve the result banner when the event list refreshes.

- [ ] **Step 4: Verify focused and full tests**

Run the focused command, then the full warning-as-error suite.

- [ ] **Step 5: Commit Task 5 files**

```powershell
git add -- src/yuanjian_app/static/app.js src/yuanjian_app/static/styles.css tests/test_http_api.py
git commit -m "fix: show cognition progress and results"
```

### Task 6: Package and verify the real Windows desktop application

**Files:**
- Modify: `build/build_windows.ps1`
- Modify: `build/yuanjian.spec`
- Modify: `tools/smoke_packaged.ps1`
- Modify: `tests/test_build_config.py`
- Modify: `README.md`
- Modify: `使用说明.md`

**Interfaces:**
- Consumes: pywebview 6.2.1, pystray 0.19.5, Pillow, PyInstaller 6.21.0.
- Produces: `dist/YuanJian/YuanJian.exe`, then `outputs/YuanJianApp-v0.6`.

- [ ] **Step 1: Write failing build-contract tests**

```python
def test_windows_build_pins_desktop_dependencies(self):
    script = self.build_script.read_text(encoding="utf-8")
    self.assertIn('pywebview==6.2.1', script)
    self.assertIn('pystray==0.19.5', script)

def test_packaged_smoke_disables_gui_only_when_explicit(self):
    script = self.smoke_script.read_text(encoding="utf-8")
    self.assertIn('YUANJIAN_HEADLESS', script)
```

- [ ] **Step 2: Run build tests and verify RED**

Run: `$env:PYTHONPATH='src'; python -m unittest tests.test_build_config -v`

Expected: missing dependency pins and headless smoke mode.

- [ ] **Step 3: Update build and smoke configuration**

Install exact dependency versions into `.venv-build`, add necessary pywebview/pystray hidden imports through PyInstaller's collected submodules, and keep the existing static-data mapping. Headless smoke mode is allowed only when `YUANJIAN_HEADLESS=1`; normal launches must always create the desktop shell.

Update user documentation to say: closing hides to tray; tray “退出远见” stops the app; external news opens in the browser; the app itself does not.

- [ ] **Step 4: Run all automated checks and build**

Run:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONWARNINGS='error::ResourceWarning'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests -q
powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
powershell -ExecutionPolicy Bypass -File tools\smoke_packaged.ps1 -ExePath 'dist\YuanJian\YuanJian.exe'
```

Expected: zero test failures, successful build, loopback-only listener, local fallback cognition, second-instance rejection/wakeup, and safe shutdown.

- [ ] **Step 5: Perform visible desktop acceptance**

Start the packaged EXE normally and verify with real clicks:

- no default browser opens;
- desktop window title is correct;
- clicking “立即运行认知” immediately shows progress and then a result;
- closing hides the window but process and scheduler remain alive;
- tray restores the same window;
- tray exit removes the process and runtime file;
- login startup test creates/removes only the current-user Startup entry.

- [ ] **Step 6: Commit Task 6 files**

```powershell
git add -- build/build_windows.ps1 build/yuanjian.spec tools/smoke_packaged.ps1 tests/test_build_config.py README.md 使用说明.md
git commit -m "build: package YuanJian desktop shell"
```

### Task 7: Release v0.6 safely and update the private repository

**Files:**
- Create: `docs/releases/YuanJian-v0.6-verification.md`
- Update local deliverables outside repository: `outputs/00_项目连续性状态.md`, `outputs/YuanJianApp-v0.6/`

**Interfaces:**
- Consumes: verified `dist/YuanJian`, private database, privacy scanner, Git remote `origin`.
- Produces: rollback-safe v0.6 package, verification report, private GitHub commits.

- [ ] **Step 1: Verify private data without modifying it**

Run read-only SQLite checks for `PRAGMA integrity_check`, migrations `[1,2,3,4]`, forecasts, external items, clusters, judgments, and impacts. Confirm no database or DPAPI file exists inside the repository.

- [ ] **Step 2: Create the v0.6 package without replacing v0.5**

Copy the verified `dist/YuanJian` contents to a new `outputs/YuanJianApp-v0.6` directory. Preserve `outputs/YuanJianApp-v0.5` unchanged and record both EXE hashes.

- [ ] **Step 3: Clean the verified legacy process only**

List each `YuanJian.exe` process and resolve its executable path. Stop only a process whose resolved path exactly points inside `YuanJianApp-v0.3`; do not terminate by process name or wildcard.

- [ ] **Step 4: Run final verification**

Run the full suite from the repository, package smoke, private database integrity query, and privacy scans against both repository and v0.6 package. Record exact test count, file counts, EXE hash, visibility `PRIVATE`, and actual GUI acceptance results.

- [ ] **Step 5: Commit the verification report and push**

```powershell
git add -- docs/releases/YuanJian-v0.6-verification.md
git commit -m "docs: record YuanJian v0.6 verification"
git push origin main
```

After pushing, verify local HEAD equals `refs/heads/main`, the worktree is clean, and `gh repo view q719563786/yuanjian --json visibility` returns `PRIVATE`.
