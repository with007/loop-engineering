#!/usr/bin/env python3
"""Loop Dashboard 发布脚本

用法:
    python release.py 0.1.0                        # 构建 + 打包
    python release.py 0.1.0 --publish              # 构建 + 打包 + 发布到 GitHub

前提:
    - Rust (cargo)
    - .NET SDK 8+ (vpk CLI: dotnet tool install -g vpk)
    - 发布需要 GITHUB_TOKEN 环境变量 (或手动输入)

产物:
    packaging/releases/
      LoopDashboard-win-Setup.exe
      LoopDashboard-win-Portable.zip
      LoopDashboard-0.1.0-full.nupkg
      releases.win.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.request import Request

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "packaging" / "dist"
RELEASES = ROOT / "packaging" / "releases"
DESKTOP = ROOT / "desktop"
PYTHON_VERSION = "3.14.3"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
PIP_PACKAGES = ["fastapi", "uvicorn", "jinja2", "pyyaml", "python-multipart", "markdown"]
PACK_ID = "LoopDashboard"
GITHUB_REPO = os.environ.get("GITHUB_REPO", "with007/loop-engineering")
GITHUB_TOKEN = "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"


def run(cmd, **kwargs):
    """运行命令，失败时退出."""
    print(f"  RUN: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, shell=isinstance(cmd, str), **kwargs)
    if result.returncode != 0:
        print(f"  FAILED (exit {result.returncode})")
        sys.exit(1)
    return result


def clean():
    """清理旧的构建产物."""
    print("\n=== [1] Clean ===")
    if DIST.exists():
        shutil.rmtree(DIST)
    if RELEASES.exists():
        shutil.rmtree(RELEASES)
    DIST.mkdir(parents=True)
    RELEASES.mkdir(parents=True)
    (DIST / "python").mkdir()
    (DIST / "app" / "src" / "loop_engineering").mkdir(parents=True)
    (DIST / "app" / "templates").mkdir(parents=True)


def build_rust():
    """编译 Rust 二进制."""
    print("\n=== [2] Build Rust ===")
    run(["cargo", "build", "--release"], cwd=DESKTOP)


def setup_python():
    """下载嵌入式 Python 并安装依赖."""
    print("\n=== [3] Setup embedded Python ===")
    python_dir = DIST / "python"

    # 下载 Python embed
    zip_path = python_dir / "python-embed.zip"
    print(f"  Downloading Python {PYTHON_VERSION}...")
    urllib.request.urlretrieve(PYTHON_URL, zip_path)

    # 解压
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(python_dir)
    zip_path.unlink()

    # 配置 site-packages
    pth = python_dir / "python314._pth"
    pth.write_text("python314.zip\n.\nimport site\n..\\app\\src\n", encoding="ascii")
    print(f"  Configured {pth.name}")

    # 安装 pip
    print("  Installing pip...")
    get_pip = python_dir / "get-pip.py"
    urllib.request.urlretrieve(PIP_URL, get_pip)
    run([str(python_dir / "python.exe"), str(get_pip)])
    get_pip.unlink()

    # 安装依赖
    print("  Installing packages...")
    run([
        str(python_dir / "python.exe"), "-m", "pip", "install",
        *PIP_PACKAGES
    ])


def copy_files():
    """复制应用文件."""
    print("\n=== [4] Copy app files ===")
    # Rust 二进制
    src_exe = DESKTOP / "target" / "release" / "loop-dashboard.exe"
    shutil.copy2(src_exe, DIST / "loop-dashboard.exe")
    print(f"  {src_exe.name}")

    # Python 源码
    src_dir = ROOT / "src" / "loop_engineering"
    dst_dir = DIST / "app" / "src" / "loop_engineering"
    for item in src_dir.rglob("*"):
        if item.is_file() and "__pycache__" not in str(item):
            rel = item.relative_to(src_dir)
            (dst_dir / rel.parent).mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst_dir / rel)
    print(f"  src/loop_engineering/")

    # 模板
    templates_src = ROOT / "templates"
    templates_dst = DIST / "app" / "templates"
    if templates_src.exists():
        for item in templates_src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(templates_src)
                (templates_dst / rel.parent).mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, templates_dst / rel)
    print(f"  templates/")

    # 确保不包含运行时生成的配置/日志
    for fname in ["dashboard-settings.json", "dashboard.log"]:
        p = DIST / fname
        if p.exists():
            p.unlink()


def write_version(version: str):
    """写入版本文件 + 同步 Cargo.toml."""
    (DIST / "version.txt").write_text(f"{version}\n")
    print(f"  version.txt → {version}")

    # 同步 Cargo.toml
    cargo_toml = ROOT / "desktop" / "Cargo.toml"
    content = cargo_toml.read_text()
    import re
    new_content = re.sub(r'^version = ".*"', f'version = "{version}"', content, count=1, flags=re.MULTILINE)
    if new_content != content:
        cargo_toml.write_text(new_content)
        print(f"  Cargo.toml → {version}")


def vpk_pack(version: str):
    """运行 vpk 打包，然后清理旧 nupkg."""
    print("\n=== [5] vpk pack ===")
    run([
        "vpk", "pack",
        "--packId", PACK_ID,
        "--packVersion", version,
        "--packDir", str(DIST),
        "--mainExe", "loop-dashboard.exe",
        "--outputDir", str(RELEASES),
        "--channel", "win",
        "--icon", str(ROOT / "desktop" / "icon.ico"),
    ], cwd=ROOT)

    # 清理旧 nupkg：只保留最近两个版本的 full.nupkg（供下次 delta）
    full_nupkgs = sorted(
        [f for f in RELEASES.glob("*-full.nupkg")],
        key=lambda f: [int(x) for x in f.stem.replace(f"{PACK_ID}-", "").replace("-full", "").split(".")],
        reverse=True,
    )
    keep_full = {f.name for f in full_nupkgs[:2]}
    for f in sorted(RELEASES.glob("*.nupkg")):
        if f.name not in keep_full:
            f.unlink()
            print(f"  Cleaned {f.name}")

    print("\n  Release files:")
    for f in sorted(RELEASES.iterdir()):
        if f.is_file():
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"    {f.name} ({size_mb:.1f} MB)")


def get_release_notes(version: str) -> str:
    """从 CHANGELOG.md 读取对应版本的发布说明."""
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.exists():
        return f"Loop Dashboard v{version}"
    content = changelog.read_text(encoding="utf-8")
    import re
    pattern = rf"## v{re.escape(version)}\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, content, re.DOTALL)
    if m:
        return f"Loop Dashboard v{version}\n\n{m.group(1).strip()}"
    return f"Loop Dashboard v{version}"


def publish_github(version: str):
    """发布到 GitHub Releases — 幂等：Release 已存在则只补传缺失文件."""
    print("\n=== [6] Publish to GitHub ===")

    token = os.environ.get("GITHUB_TOKEN") or GITHUB_TOKEN
    tag = f"v{version}"
    api_base = f"https://api.github.com/repos/{GITHUB_REPO}"

    def api_headers():
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    # 检查 Release 是否已存在
    release = None
    list_url = f"{api_base}/releases"
    req = Request(list_url)
    for h, v in api_headers().items():
        req.add_header(h, v)
    try:
        with urllib.request.urlopen(req) as resp:
            releases = json.loads(resp.read())
        for r in releases:
            if r["tag_name"] == tag:
                release = r
                print(f"  Release exists: {release['html_url']}")
                break
    except Exception as e:
        print(f"  Failed to list releases: {e}")
        return

    # 不存在则创建
    if not release:
        print(f"  Creating release {tag}...")
        data = json.dumps({
            "tag_name": tag,
            "target_commitish": "master",
            "name": f"Loop Dashboard v{version}",
            "body": get_release_notes(version),
            "draft": False,
            "prerelease": version.startswith("0."),
        }).encode()

        req = Request(f"{api_base}/releases", data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github.v3+json")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                release = json.loads(resp.read())
            print(f"  Release created: {release['html_url']}")
        except urllib.error.HTTPError as e:
            print(f"  FAILED: {e.code} {e.read().decode()}")
            return

    # 收集已有文件名，只上传缺失的
    existing_names = {a["name"] for a in release.get("assets", [])}
    upload_url = release["upload_url"].split("{")[0]

    for fpath in sorted(RELEASES.iterdir()):
        if not fpath.is_file():
            continue
        if fpath.name in existing_names:
            print(f"  SKIP {fpath.name} (already uploaded)")
            continue

        size_mb = fpath.stat().st_size / 1024 / 1024
        print(f"  Uploading {fpath.name} ({size_mb:.1f} MB)...")
        with open(fpath, "rb") as f:
            data = f.read()

        url = f"{upload_url}?name={fpath.name}"
        for attempt in range(3):
            try:
                req = Request(url, data=data, method="POST")
                req.add_header("Authorization", f"Bearer {token}")
                req.add_header("Content-Type", "application/octet-stream")
                urllib.request.urlopen(req)
                print(f"    OK")
                break
            except urllib.error.HTTPError as e:
                print(f"    FAILED: {e.code}")
                break  # HTTP 错误不重试
            except Exception as e:
                if attempt < 2:
                    print(f"    Retry {attempt + 1}: {e}")
                    import time
                    time.sleep(3)
                else:
                    print(f"    FAILED after 3 attempts: {e}")


def get_current_version():
    """从 version.txt 读取当前版本."""
    vf = ROOT / "desktop" / "version.txt"
    if vf.exists():
        return vf.read_text().strip()
    return None


def bump_patch(version: str) -> str:
    """递增 patch 版本号，如 0.1.0 → 0.1.1."""
    parts = version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Loop Dashboard 发布脚本")
    parser.add_argument("version", nargs="?", help="版本号，如 0.2.0，或 'auto' 自动递增")
    parser.add_argument("--publish", action="store_true", help="构建后发布到 GitHub")
    parser.add_argument("--skip-build", action="store_true", help="跳过 Rust 编译")
    parser.add_argument("--skip-python", action="store_true", help="跳过 Python 下载（使用已有）")
    parser.add_argument("--publish-only", action="store_true", help="仅上传已有产物（跳过所有构建步骤）")
    args = parser.parse_args()

    current = get_current_version()

    if not args.version:
        if current:
            print(f"Current version: {current}")
            args.version = input(f"New version [{bump_patch(current)}]: ").strip()
        if not args.version:
            if current:
                args.version = bump_patch(current)
            else:
                args.version = "0.1.0"
    elif args.version == "auto":
        if current:
            args.version = bump_patch(current)
        else:
            args.version = "0.1.0"

    version = args.version
    print(f"Loop Dashboard Release v{version} (current: {current or 'none'})")
    print(f"Repo: {GITHUB_REPO}")

    if args.publish_only:
        print("\n=== [1-5] SKIPPED (--publish-only) ===")
    else:
        if not args.skip_python:
            clean()
        else:
            DIST.mkdir(parents=True, exist_ok=True)
            RELEASES.mkdir(parents=True, exist_ok=True)
        if not args.skip_build:
            build_rust()
        else:
            print("\n=== [2] Build Rust (SKIPPED) ===")
        if not args.skip_python:
            setup_python()
        else:
            print("\n=== [3] Setup Python (SKIPPED) ===")
        copy_files()
        write_version(version)
        vpk_pack(version)

    if args.publish:
        publish_github(version)

    print(f"\n=== Done: v{version} ===")
    print(f"Files: {RELEASES}")


if __name__ == "__main__":
    main()
