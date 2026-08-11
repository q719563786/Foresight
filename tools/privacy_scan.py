import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScanReport:
    safe: bool = True
    blocked_files: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)


def scan_tree(root):
    """Reject runtime artifacts and recognizable credentials from a source tree."""
    root = Path(root)
    blocked_extensions = {".db", ".sqlite", ".sqlite3", ".log", ".env", ".bak"}
    blocked_names = {"cache", "backups", "__pycache__"}
    secret_patterns = (
        re.compile(r"gh[opsu]_[A-Za-z0-9]{20,}"),
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"C:\\Users\\[^\\\r\n]+", re.IGNORECASE),
    )
    blocked_files = []
    findings = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if any(part.lower() in blocked_names for part in path.relative_to(root).parts):
            if path.is_file():
                blocked_files.append(relative)
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() in blocked_extensions:
            blocked_files.append(relative)
            continue
        if path.suffix.lower() not in {".py", ".md", ".txt", ".json", ".html", ".css", ".js", ".cmd"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in secret_patterns:
            if pattern.search(text):
                findings.append(f"{relative}:敏感内容模式")
                break
    return ScanReport(
        safe=not blocked_files and not findings,
        blocked_files=blocked_files,
        findings=findings,
    )


if __name__ == "__main__":
    report = scan_tree(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(f"safe={report.safe} blocked={len(report.blocked_files)} findings={len(report.findings)}")
    for item in [*report.blocked_files, *report.findings]:
        print(item)
    raise SystemExit(0 if report.safe else 1)
