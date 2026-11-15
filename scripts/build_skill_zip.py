"""Build the Agensi upload: dist/iso20022-payment-reviewer.zip.

Usage: uv run python scripts/build_skill_zip.py

The zip contains the skill folder and the project LICENSE. The script refuses to build
when SKILL.md lacks its front matter, when a file is unexpectedly large, or when anything
looks like a credential, so a mistake cannot be uploaded by accident.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "iso20022-payment-reviewer"
OUTPUT = ROOT / "dist" / "iso20022-payment-reviewer.zip"
MAX_FILE_BYTES = 200_000
TEXT_SUFFIXES = {".md", ".txt", ".json", ".py", ".sh", ".yaml", ".yml", ".toml"}
SECRET_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"AKIA[0-9A-Z]{16}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"(?i)aws_secret_access_key",
        r"ghp_[A-Za-z0-9]{36}",
        r"sk-[A-Za-z0-9]{20,}",
        r"(?i)password\s*[:=]",
    )
]


def check_skill(skill_dir: Path) -> list[str]:
    problems = []
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return [f"{skill_file} is missing"]
    front_matter = re.match(r"^---\n(.*?)\n---\n", skill_file.read_text(encoding="utf-8"), re.DOTALL)
    if not front_matter:
        problems.append("SKILL.md must start with a --- front matter block")
    else:
        fields = dict(line.split(":", 1) for line in front_matter.group(1).splitlines() if ":" in line)
        for key in ("name", "description"):
            if not fields.get(key, "").strip():
                problems.append(f"SKILL.md front matter needs a non-empty '{key}'")
    for path in sorted(skill_dir.rglob("*")):
        if path.is_dir():
            continue
        if path.name.startswith(".env") or path.suffix in {".pem", ".key"}:
            problems.append(f"{path.name} must not be packaged")
        if path.stat().st_size > MAX_FILE_BYTES:
            problems.append(f"{path.name} is larger than {MAX_FILE_BYTES} bytes")
        content = path.read_text(encoding="utf-8", errors="ignore")
        problems += [
            f"{path.name} matches a credential pattern ({pattern.pattern})" for pattern in SECRET_PATTERNS if pattern.search(content)
        ]
    return problems


def build(skill_dir: Path = SKILL_DIR, output: Path = OUTPUT) -> Path:
    problems = check_skill(skill_dir)
    if problems:
        raise SystemExit("Refusing to build:\n- " + "\n- ".join(problems))
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [path for path in sorted(skill_dir.rglob("*")) if path.is_file()] + [ROOT / "LICENSE"]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            name = (Path(skill_dir.name) / (path.relative_to(skill_dir) if path.is_relative_to(skill_dir) else path.name)).as_posix()
            if path.suffix in TEXT_SUFFIXES or path.name == "LICENSE":
                # Git on Windows may check text out with CRLF; ship LF so front matter parses everywhere.
                archive.writestr(name, path.read_bytes().replace(b"\r\n", b"\n"))
            else:
                archive.write(path, name)
    return output


if __name__ == "__main__":
    built = build()
    with zipfile.ZipFile(built) as archive:
        print(f"Built {built.relative_to(ROOT)}:")
        for name in archive.namelist():
            print(f"  {name}")
    sys.exit(0)
