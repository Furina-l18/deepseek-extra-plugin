"""校验版本号在 metadata.yaml、CODE_VERSION、@register 三处一致。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = r"([0-9]+\.[0-9]+\.[0-9]+)"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    meta = read(ROOT / "metadata.yaml")
    src = read(ROOT / "main.py")

    m_meta = re.search(rf"^version:\s*v?{SEMVER}", meta, re.M)
    m_code = re.search(rf'CODE_VERSION\s*=\s*"{SEMVER}"', src)
    m_reg_block = re.search(r"@register\((.*?)\n\)", src, re.S)
    m_reg = (
        re.search(rf'"{SEMVER}"', m_reg_block.group(1)) if m_reg_block else None
    )

    versions = {
        "metadata.yaml": m_meta.group(1) if m_meta else None,
        "CODE_VERSION": m_code.group(1) if m_code else None,
        "@register": m_reg.group(1) if m_reg else None,
    }

    for name, value in versions.items():
        print(f"{name:16} {value or '(未找到)'}")

    missing = [k for k, v in versions.items() if not v]
    if missing:
        print(f"\n失败：{', '.join(missing)} 里没有解析到版本号", file=sys.stderr)
        return 1

    if len(set(versions.values())) != 1:
        print("\n失败：三处版本号不一致", file=sys.stderr)
        return 1

    print(f"\n通过：版本号统一为 {versions['metadata.yaml']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
