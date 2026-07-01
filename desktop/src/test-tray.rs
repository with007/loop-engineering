// test-tray.rs — 通过 Windows API 向托盘图标窗口发送 WM_COMMAND 消息
// 编译: cd desktop && rustc --edition 2021 src/test-tray.rs -o target/debug/test-tray.exe
// 用法: test-tray.exe <menu_index>
//   menu_index: 0=打开Dashboard, 1=新增项目, 2=项目子菜单(跳过), 3=设置...,
//               4=开机自启, 5=暂停, 6=恢复, 7=停止, 8=启动, 9=退出
//   实际索引需要根据 tray_icon 分配的内部 ID 调整

use std::process::Command;

fn main() {
    // 找到 loop-dashboard 进程
    let pid = match find_pid("loop-dashboard.exe") {
        Some(p) => p,
        None => {
            eprintln!("loop-dashboard.exe not running");
            std::process::exit(1);
        }
    };
    println!("Found PID: {}", pid);

    // 遍历所有窗口找到属于该进程的隐藏窗口
    let hwnd = match find_tray_window(pid) {
        Some(h) => h,
        None => {
            eprintln!("No tray window found");
            std::process::exit(1);
        }
    };
    println!("Found tray window: {:?}", hwnd);

    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: test-tray.exe <menu_id>");
        eprintln!("Try IDs 1-20 to find the right one");
        std::process::exit(1);
    }

    let menu_id: u32 = args[1].parse().unwrap_or(1);
    println!("Sending WM_COMMAND with id={}", menu_id);

    unsafe {
        send_message(hwnd, 0x0111, menu_id as usize, 0); // WM_COMMAND
    }
    println!("Message sent. Check dashboard.log for result.");
}

fn find_pid(name: &str) -> Option<u32> {
    let output = Command::new("tasklist")
        .args(["/FI", &format!("IMAGENAME eq {}", name), "/FO", "CSV", "/NH"])
        .output()
        .ok()?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    for line in stdout.lines() {
        let parts: Vec<&str> = line.split(',').collect();
        if parts.len() >= 2 {
            let pid_str = parts[1].trim_matches('"');
            if let Ok(p) = pid_str.parse::<u32>() {
                return Some(p);
            }
        }
    }
    None
}

fn find_tray_window(pid: u32) -> Option<isize> {
    // 使用 tasklist 无法直接获取窗口句柄
    // 用 PowerShell 来枚举
    let ps_script = format!(
        r#"
Add-Type -Name W -Namespace Tmp -MemberDefinition '
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
[DllImport("user32.dll")] public static extern int GetClassName(IntPtr hWnd, System.Text.StringBuilder lpClassName, int nMaxCount);
'
$pid = {}
$sb = New-Object System.Text.StringBuilder(256)
$found = [IntPtr]::Zero
$cb = [Tmp.W+EnumWindowsProc]{{ param($h, $l); $p = 0u; [Tmp.W]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null; if ($p -eq $pid) {{ $sb.Clear(); [Tmp.W]::GetClassName($h, $sb, 256) | Out-Null; $cn = $sb.ToString(); if ($cn -match 'tray' -or $cn -match 'static' -or $cn -match 'Tray') {{ $found = $h; }} }} return $true }}
[Tmp.W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
if ($found -ne [IntPtr]::Zero) {{ Write-Host $found }} else {{ Write-Host "NOTFOUND" }}
"#, pid);

    let output = Command::new("powershell")
        .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", &ps_script])
        .output()
        .ok()?;
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if stdout == "NOTFOUND" || stdout.is_empty() {
        None
    } else if let Ok(h) = stdout.parse::<isize>() {
        Some(h)
    } else {
        None
    }
}

extern "system" {
    fn SendMessageW(hWnd: isize, Msg: u32, wParam: usize, lParam: isize) -> isize;
}

unsafe fn send_message(hwnd: isize, msg: u32, wparam: usize, lparam: isize) {
    SendMessageW(hwnd, msg, wparam, lparam);
}
