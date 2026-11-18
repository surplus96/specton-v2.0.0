"""Check publishable developer documentation without network access or secret reads."""

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_DOCS = ("specton/implementation/templates/", "tests/fixtures/implementation/")
LOCAL_ONLY = (
    "var/",
    "storage/",
    "outputs/",
    ".claude/",
    ".codex/",
    ".agents/",
    "docs/planning/",
    "docs/evidence/",
    "recordings/",
    "demo-recording/",
    "portfolio-export/",
    "local-archive/",
)
LINK = re.compile(r"\]\((<[^>]+>|[^\s)]+)(?:\s+[\"'][^\n]*?[\"'])?\)")
HTML_LINK = re.compile(r"(?:href|src)=[\"']([^\"']+)[\"']")
FENCE = re.compile(r"^(`{3,}|~{3,}).*?^\1\s*$", re.MULTILINE | re.DOTALL)
LOCAL_CONTEXT = re.compile(
    r"/Users/|[A-Za-z]:\\Users\\|localhost:\d+/(?:specifications|changes)/[a-f0-9-]{36}"
)


def candidates() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        ROOT / name
        for name in sorted(set(result.stdout.split("\0")))
        if name and (ROOT / name).is_file()
    ]


def main() -> int:
    errors: list[str] = []
    files = candidates()
    documents = []
    for path in files:
        name = path.relative_to(ROOT).as_posix()
        if name.startswith(LOCAL_ONLY) or (
            path.name.startswith(".env") and not path.name.endswith(".example")
        ):
            errors.append(f"Local-only file in upload candidates: {name}")
        if path.suffix == ".md" and not name.startswith(PAYLOAD_DOCS):
            documents.append(path)

    ko = {p.name for p in (ROOT / "docs/ko").glob("*.md")}
    en = {p.name for p in (ROOT / "docs/en").glob("*.md")}
    if not ko or ko != en:
        errors.append(f"Language files differ: Korean-only={ko - en}, English-only={en - ko}")
    links = 0
    for path in documents:
        name = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if LOCAL_CONTEXT.search(text):
            errors.append(f"Personal path or execution-specific link: {name}")
        if name.startswith(("docs/ko/", "docs/en/")):
            for lang in ("ko", "en"):
                if f"../{lang}/{path.name}" not in text:
                    errors.append(f"Missing {lang} language switch: {name}")
        prose = FENCE.sub("", text)
        destinations = LINK.findall(prose) + HTML_LINK.findall(prose)
        for destination in destinations:
            link = urlsplit(destination.strip("<>"))
            if link.scheme or link.netloc or not link.path:
                continue
            target = (path.parent / unquote(link.path)).resolve()
            links += 1
            if not target.is_relative_to(ROOT) or not target.exists():
                errors.append(f"Broken/outside link: {name} -> {destination}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Documentation OK: {len(documents)} files, {len(ko)} language pairs, {links} links.")
    print("No local-only files in current upload candidates; Git history is not inspected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
