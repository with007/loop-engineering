#![windows_subsystem = "console"]
// click-tray: 向 tray_icon_app 窗口发送 WM_COMMAND 测试菜单事件
use std::ffi::OsStr;
use std::os::windows::ffi::OsStrExt;
use std::process::Command;

extern "system" {
    fn FindWindowExW(parent: isize, child: isize, class: *const u16, window: *const u16) -> isize;
    fn SendMessageW(hwnd: isize, msg: u32, wparam: usize, lparam: isize) -> isize;
    fn GetWindowThreadProcessId(hwnd: isize, pid: *mut u32) -> u32;
}
unsafe fn enum_windows() -> Vec<(isize, u32)> {
    use std::mem;
    let mut result = Vec::new();
    // Use tasklist + powershell for simplicity
    result
}

fn main() {
    // Get PID of loop-dashboard
    let output = Command::new("tasklist")
        .args(["/FI", "IMAGENAME eq loop-dashboard.exe", "/FO", "CSV", "/NH"])
        .output().ok();
    let mut pid = 0u32;
    if let Some(o) = output {
        let s = String::from_utf8_lossy(&o.stdout);
        for line in s.lines() {
            let parts: Vec<&str> = line.split(',').collect();
            if parts.len() >= 2 {
                pid = parts[1].trim_matches('"').parse().unwrap_or(0);
                break;
            }
        }
    }
    if pid == 0 {
        println!("loop-dashboard.exe not running");
        return;
    }
    println!("PID: {}", pid);

    // Enumerate windows via PowerShell to find tray_icon_app
    let ps = format!(
        r#"Add-Type -Name W -Namespace T -MemberDefinition '[DllImport("user32.dll")]public static extern bool EnumWindows(EnumW cb,IntPtr l);public delegate bool EnumW(IntPtr h,IntPtr l);[DllImport("user32.dll")]public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);[DllImport("user32.dll")]public static extern int GetClassName(IntPtr h,System.Text.StringBuilder c,int n);'
$pid={pid}
$sb=New-Object System.Text.StringBuilder(256)
$cb=[T.W+EnumW]{{param($h,$l);$procid=0u;[T.W]::GetWindowThreadProcessId($h,[ref]$procid)|Out-Null;if($procid -eq $pid){{$sb.Clear();[T.W]::GetClassName($h,$sb,256)|Out-Null;if($sb.ToString() -match 'tray'){{Write-Host $h}}}}return $true}}
[T.W]::EnumWindows($cb,[IntPtr]::Zero)|Out-Null
"#
    );
    let output = Command::new("powershell")
        .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", &ps])
        .output().ok();
    let mut hwnd: isize = 0;
    if let Some(o) = output {
        let s = String::from_utf8_lossy(&o.stdout).trim().to_string();
        if !s.is_empty() && s != "0" {
            hwnd = s.parse().unwrap_or(0);
        }
    }
    if hwnd == 0 {
        // Try to find by class name directly
        let class = to_wide("tray_icon_app");
        unsafe {
            hwnd = FindWindowExW(0, 0, class.as_ptr(), std::ptr::null());
        }
    }
    if hwnd == 0 {
        println!("Could not find tray window");
        return;
    }
    println!("Tray window: 0x{:X}", hwnd as usize);

    let args: Vec<String> = std::env::args().collect();
    let start: u32 = args.get(1).and_then(|s| s.parse().ok()).unwrap_or(1);
    let end: u32 = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(20);

    println!("Sending WM_COMMAND ids {}-{}", start, end);
    for id in start..=end {
        print!("id={} ", id);
        unsafe { SendMessageW(hwnd, 0x0111, id as usize, 0); }
        std::thread::sleep(std::time::Duration::from_millis(500));
    }
    println!("\nDone. Check dashboard.log.");
}

fn to_wide(s: &str) -> Vec<u16> {
    OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
}
