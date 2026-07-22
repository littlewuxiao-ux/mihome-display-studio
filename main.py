"""MiHome Display Studio web entry point."""
from __future__ import annotations

import argparse
from pathlib import Path

from app.web_server import run_server


def main() -> int:
    parser = argparse.ArgumentParser(description="米家中枢屏幕工作台")
    parser.add_argument("--port", type=int, default=8765, help="本地Web端口")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()
    run_server(Path.cwd(), args.port, not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
