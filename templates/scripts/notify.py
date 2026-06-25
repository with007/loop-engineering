#!/usr/bin/env python3
"""
跨平台通知工具。
用法: python .claude/scripts/notify.py <title> <message> [diff_path]
带 diff_path 时会自动用 Explorer 选中该文件。
"""
import subprocess, sys, platform, tempfile, os


def main():
    if len(sys.argv) < 3:
        print("Usage: notify.py <title> <message> [diff_path]")
        sys.exit(1)

    title = sys.argv[1]
    message = sys.argv[2]
    diff_path = sys.argv[3] if len(sys.argv) > 3 else None

    system = platform.system()

    if system == 'Windows':
        _notify_windows(title, message, diff_path)
    elif system == 'Darwin':
        _notify_mac(title, message)
    else:
        print(f"[通知] {title}: {message}")


def _notify_windows(title, message, diff_path):
    tmp = tempfile.mktemp(suffix='.ps1')
    with open(tmp, 'w', encoding='utf-8-sig') as f:
        f.write(f'Add-Type -AssemblyName System.Windows.Forms\n')
        f.write(f'[System.Windows.Forms.MessageBox]::Show("{message}", "{title}", "OK", "Information")\n')
        if diff_path:
            abs_path = os.path.abspath(diff_path).replace('/', '\\')
            f.write(f'explorer /select,"{abs_path}"\n')
    subprocess.Popen(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', tmp],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, encoding='utf-8'
    )


def _notify_mac(title, message):
    subprocess.run(['osascript', '-e', f'display notification "{message}" with title "{title}"'],
                   encoding='utf-8', errors='replace')


if __name__ == "__main__":
    main()
