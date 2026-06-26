from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "startup-log.txt"
REQUIREMENTS = ROOT / "requirements.txt"
DIST_INDEX = ROOT / "dist" / "index.html"


def log(message: str = "") -> None:
    print(message, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{message}\n")


def run_step(title: str, command: list[str]) -> None:
    log(f"{title}...")
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n[{title}]\n")
        log_file.write(f"{' '.join(command)}\n")
        result = subprocess.run(command, cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{title}失败，请查看 startup-log.txt。")
    log(f"{title}完成。")


def venv_python() -> Path:
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_python_version() -> None:
    if sys.version_info < (3, 9):
        raise RuntimeError("当前 Python 版本过低，请安装 Python 3.9 或更高版本。")


def ensure_backend_environment() -> Path:
    python_path = venv_python()
    if not python_path.exists():
        run_step("创建 Python 运行环境", [sys.executable, "-m", "venv", str(ROOT / ".venv")])

    stamp = ROOT / ".venv" / "requirements.sha256"
    requirements_hash = digest(REQUIREMENTS)
    if stamp.exists() and stamp.read_text(encoding="utf-8").strip() == requirements_hash:
        log("Python 后端依赖已安装，跳过重复安装。")
        return python_path

    run_step("升级 pip", [str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
    run_step("安装后端依赖", [str(python_path), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    stamp.write_text(requirements_hash, encoding="utf-8")
    return python_path


def node_version_ok() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    script = (
        "const [major, minor] = process.versions.node.split('.').map(Number);"
        "process.exit((major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major > 22 ? 0 : 1)"
    )
    return subprocess.run([node, "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def ensure_frontend() -> None:
    if DIST_INDEX.exists():
        log("已检测到内置页面文件，跳过 Node.js 前端构建。")
        return

    npm = shutil.which("npm")
    if not npm or not node_version_ok():
        raise RuntimeError(
            "未检测到可用的内置页面文件，且 Node.js 不可用。"
            "请安装 Node.js 20.19+ 或 22.12+，或使用包含 dist 的交付包。"
        )
    run_step("安装前端依赖", [npm, "install"])
    run_step("构建前端页面", [npm, "run", "build"])


def find_free_port(start: int = 8000, end: int = 8020) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("8000-8020 端口都被占用，无法启动本地服务。")


def health_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def open_browser(url: str) -> None:
    log(f"正在打开网页：{url}")
    opened = False
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "", url], cwd=ROOT)
            opened = True
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url], cwd=ROOT)
            opened = True
        elif shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", url], cwd=ROOT)
            opened = True
    except Exception as exc:
        log(f"系统默认方式打开浏览器失败：{exc}")

    if not opened:
        opened = webbrowser.open(url, new=2)
    if not opened:
        log("浏览器没有自动打开，请手动复制上面的地址到浏览器。")


def start_server(python_path: Path, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("DATA_DIR", str(ROOT / "data"))
    env.setdefault("USE_SAMPLE_DATA", "true")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    command = [
        str(python_path),
        "-m",
        "uvicorn",
        "backend.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write("\n[启动本地服务]\n")
        log_file.write(f"{' '.join(command)}\n")
    return subprocess.Popen(command, cwd=ROOT, env=env, stdout=LOG_PATH.open("a", encoding="utf-8"), stderr=subprocess.STDOUT)


def main() -> int:
    LOG_PATH.write_text("世界城招商热点监测启动日志\n", encoding="utf-8")
    log(f"当前目录：{ROOT}")
    try:
        ensure_python_version()
        python_path = ensure_backend_environment()
        ensure_frontend()
        port = find_free_port()
        url = f"http://127.0.0.1:{port}"
        log(f"本地服务端口：{port}")
        server = start_server(python_path, port)

        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError("本地服务启动后立即退出，请查看 startup-log.txt。")
            if health_ok(url):
                open_browser(url)
                break
            time.sleep(1)
        else:
            open_browser(url)
            log("服务健康检查超时，但已尝试打开网页；如果页面不可用，请查看 startup-log.txt。")

        log("服务正在运行。关闭此窗口或按 Ctrl+C 可停止服务。")
        return server.wait()
    except KeyboardInterrupt:
        log("收到停止信号，正在退出。")
        return 0
    except Exception as exc:
        log("")
        log(f"启动失败：{exc}")
        log("请把 startup-log.txt 发给项目维护方定位。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
