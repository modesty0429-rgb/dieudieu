"""
줄 수 집계 도구: docs/LINE_COUNT.md 를 자동으로 만든다.

파일마다 전체 줄 / 코드 줄 / 주석 줄 / 빈 줄을 센다.
  - C: // 로 시작하는 줄, /* ... */ 안의 줄을 주석으로 본다.
  - Python: # 로 시작하는 줄, 세 따옴표 문자열(docstring) 안의 줄을 주석으로 본다.

실행:
    python tools/count_lines.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
C_TARGETS = [PROJECT_ROOT / "c_core" / "include", PROJECT_ROOT / "c_core" / "src"]
PY_TARGETS = [PROJECT_ROOT / "gui", PROJECT_ROOT / "tools"]


def count_c(lines: list[str]) -> tuple[int, int, int]:
    """(코드, 주석, 빈 줄) 수. 코드 뒤에 붙은 주석은 코드 줄로 센다."""
    code = comment = blank = 0
    in_block = False
    for raw in lines:
        line = raw.strip()
        if not line:
            blank += 1
        elif in_block:
            comment += 1
            if "*/" in line:
                in_block = False
        elif line.startswith("//"):
            comment += 1
        elif line.startswith("/*"):
            comment += 1
            in_block = "*/" not in line
        else:
            code += 1
    return code, comment, blank


def count_python(lines: list[str]) -> tuple[int, int, int]:
    code = comment = blank = 0
    in_doc = False
    for raw in lines:
        line = raw.strip()
        if not line:
            blank += 1
        elif in_doc:
            comment += 1
            if '"""' in line:
                in_doc = False
        elif line.startswith("#"):
            comment += 1
        elif line.startswith('"""'):
            comment += 1
            in_doc = line.count('"""') == 1
        else:
            code += 1
    return code, comment, blank


def collect(targets: list[Path], patterns: list[str], counter) -> list[tuple[str, int, int, int, int]]:
    rows = []
    for folder in targets:
        for pattern in patterns:
            for path in sorted(folder.rglob(pattern)):
                if "__pycache__" in path.parts:
                    continue
                lines = path.read_text(encoding="utf-8").splitlines()
                code, comment, blank = counter(lines)
                rows.append((path.relative_to(PROJECT_ROOT).as_posix(), len(lines), code, comment, blank))
    return rows


def table(rows) -> list[str]:
    out = ["| 파일 | 전체 | 코드 | 주석 | 빈 줄 |", "|---|---:|---:|---:|---:|"]
    for name, total, code, comment, blank in rows:
        out.append(f"| `{name}` | {total} | {code} | {comment} | {blank} |")
    sums = [sum(r[i] for r in rows) for i in range(1, 5)]
    out.append(f"| **합계** | **{sums[0]}** | **{sums[1]}** | **{sums[2]}** | **{sums[3]}** |")
    return out


def main() -> None:
    c_rows = collect(C_TARGETS, ["*.h", "*.c"], count_c)
    py_rows = collect(PY_TARGETS, ["*.py"], count_python)
    c_total = sum(r[1] for r in c_rows)
    py_total = sum(r[1] for r in py_rows)

    lines = [
        "# 줄 수 현황 (LINE_COUNT)",
        "",
        f"> `python tools/count_lines.py` 로 자동 생성 — {date.today().isoformat()}",
        "",
        "| 언어 | 현재 | 목표 | 진행률 |",
        "|---|---:|---:|---:|",
        f"| C | {c_total} | 약 8,000 | {100 * c_total / 8000:.0f}% |",
        f"| Python | {py_total} | 약 4,000 | {100 * py_total / 4000:.0f}% |",
        f"| **합계** | **{c_total + py_total}** | **약 12,000** | **{100 * (c_total + py_total) / 12000:.0f}%** |",
        "",
        "## C",
        "",
        *table(c_rows),
        "",
        "## Python",
        "",
        *table(py_rows),
        "",
    ]
    out_path = PROJECT_ROOT / "docs" / "LINE_COUNT.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"저장 완료: {out_path}  (C {c_total}줄, Python {py_total}줄)")


if __name__ == "__main__":
    main()
