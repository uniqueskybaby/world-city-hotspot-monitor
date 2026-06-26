from __future__ import annotations

import fnmatch
import zipfile
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = PROJECT_ROOT / "release"
PACKAGE_NAME = "world-city-hotspot-monitor-local.zip"

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".npm-cache",
    "node_modules",
    "artifacts",
    "release",
    "__pycache__",
}

EXCLUDED_FILES = {
    ".DS_Store",
    ".env",
    "design-qa.md",
}

EXCLUDED_PATTERNS = (
    "*.pyc",
    "data/*.db-*",
    ".github/*",
)


def should_include(path: Path) -> bool:
    relative = path.relative_to(PROJECT_ROOT)
    parts = set(relative.parts)
    if parts & EXCLUDED_DIRS:
        return False
    if path.name in EXCLUDED_FILES:
        return False
    relative_posix = relative.as_posix()
    return not any(fnmatch.fnmatch(relative_posix, pattern) for pattern in EXCLUDED_PATTERNS)


def main() -> None:
    RELEASE_DIR.mkdir(exist_ok=True)
    output = RELEASE_DIR / PACKAGE_NAME
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(PROJECT_ROOT.rglob("*")):
            if not path.is_file() or not should_include(path):
                continue
            archive.write(path, path.relative_to(PROJECT_ROOT).as_posix())

        archive.writestr(
            "PACKAGE_INFO.txt",
            "\n".join(
                [
                    "世界城招商热点监测 - 本地运行包",
                    f"打包时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                    "双击 start-mac.command 或 start-windows.bat 即可安装后端依赖并启动。",
                    "包内已包含 dist 页面文件，正常情况下 Windows 不需要安装 Node.js。",
                    "包内保留 data/hotspots.db 作为演示和测试数据。",
                ]
            )
            + "\n",
        )

    print(f"Created {output}")


if __name__ == "__main__":
    main()
