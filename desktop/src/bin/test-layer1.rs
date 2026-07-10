// Layer 1 Automated Test — per Section 6 of CLAUDE.md
// Uses PostMessage/SendMessage to simulate user operations on the tray icon,
// then reads logs to verify key paths were traversed.
//
// Compile: cargo build --release --bin test-layer1
// Run:     cargo run --release --bin test-layer1

#![windows_subsystem = "console"]

use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

use windows::Win32::Foundation::{HWND, LPARAM, WPARAM};
use windows::Win32::UI::Input::KeyboardAndMouse::{keybd_event, KEYBD_EVENT_FLAGS, KEYEVENTF_KEYUP};
use windows::Win32::UI::WindowsAndMessaging::{FindWindowW, PostMessageW, WM_RBUTTONDOWN};

// From tray-icon source: custom callback message ID
const WM_USER_TRAYICON: u32 = 6002;
const VK_ESCAPE: u8 = 0x1B;

fn find_tray_window() -> Option<HWND> {
    let hwnd = unsafe { FindWindowW(windows::core::w!("tray_icon_app"), None) };
    match hwnd {
        Ok(h) if h.0 as isize != 0 => Some(h),
        _ => None,
    }
}

fn post_tray_right_click(hwnd: HWND) {
    unsafe {
        let _ = PostMessageW(
            hwnd,
            WM_USER_TRAYICON,
            WPARAM(0),
            LPARAM(WM_RBUTTONDOWN as isize),
        );
    }
    println!(
        "  [INFO] PostMessage(WM_USER_TRAYICON, WM_RBUTTONDOWN) sent to HWND=0x{:X}",
        hwnd.0 as isize
    );
}

fn send_escape() {
    unsafe {
        keybd_event(VK_ESCAPE, 0, KEYBD_EVENT_FLAGS(0), 0);
        thread::sleep(Duration::from_millis(50));
        keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0);
    }
    println!("  [INFO] keybd_event(VK_ESCAPE) sent to dismiss popup menu");
}

fn wait_for_log(log_path: &str, pattern: &str, timeout_ms: u64) -> bool {
    let start = std::time::Instant::now();
    while start.elapsed().as_millis() < timeout_ms as u128 {
        if let Ok(content) = std::fs::read_to_string(log_path) {
            if content.contains(pattern) {
                return true;
            }
        }
        thread::sleep(Duration::from_millis(200));
    }
    false
}

fn main() {
    println!("=== Layer 1 Test: migrate-desktop-to-winit ===\n");

    // Paths relative to desktop/
    let exe = "target/release/loop-dashboard.exe";
    let log = "target/release/dashboard.log";

    // Clean up previous
    let _ = std::fs::remove_file(log);

    // Kill any existing instance
    let _ = Command::new("taskkill")
        .args(["/F", "/IM", "loop-dashboard.exe"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    // ── Test 1: App startup ────────────────────────────────────────────────
    println!("--- Test 1: Event Loop Startup ---");

    if !std::path::Path::new(exe).exists() {
        eprintln!("  FAIL: Binary not found: {}", exe);
        eprintln!("  Run: cargo build --release");
        std::process::exit(1);
    }

    let mut child = Command::new(exe)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .expect("Failed to start loop-dashboard.exe");

    println!("  Started PID={}", child.id());

    let pass1 = wait_for_log(log, "tray icon created", 10000);
    println!(
        "  [{}] Tray icon created",
        if pass1 { "PASS" } else { "FAIL" }
    );

    let pass2 = wait_for_log(log, "MenuEvent handler registered", 5000);
    println!(
        "  [{}] MenuEvent handler registered",
        if pass2 { "PASS" } else { "FAIL" }
    );

    let pass3 = wait_for_log(log, "heartbeat: poll mode active", 5000);
    println!(
        "  [{}] Event loop running (heartbeat + Poll mode)",
        if pass3 { "PASS" } else { "FAIL" }
    );

    if !pass1 || !pass2 || !pass3 {
        let _ = child.kill();
        eprintln!("\n  Startup checks failed. Log:");
        if let Ok(content) = std::fs::read_to_string(log) {
            eprintln!("{}", content);
        }
        std::process::exit(1);
    }

    // ── Test 2: Simulate tray right-click via PostMessage ──────────────────
    println!("\n--- Test 2: Tray Right-Click via PostMessage ---");

    // Find the tray_icon_app hidden window
    let hwnd = loop {
        if let Some(h) = find_tray_window() {
            break h;
        }
        if child.try_wait().ok().flatten().is_some() {
            println!("  [FAIL] Process exited before tray window found");
            std::process::exit(1);
        }
        thread::sleep(Duration::from_millis(500));
    };
    println!(
        "  [PASS] Found tray_icon_app window (HWND=0x{:X})",
        hwnd.0 as isize
    );

    // PostMessage: simulate right-click on tray icon
    // This triggers: tray_proc → show_tray_menu → TrackPopupMenu (modal loop)
    post_tray_right_click(hwnd);
    thread::sleep(Duration::from_millis(600));

    // Dismiss the popup menu with ESC key
    send_escape();
    thread::sleep(Duration::from_millis(500));

    // Verify: app still running after menu open/close
    let still_alive = child.try_wait().ok().flatten().is_none();
    println!(
        "  [{}] App survives menu open/close",
        if still_alive { "PASS" } else { "FAIL" }
    );

    // Check log for panics
    let log_content = std::fs::read_to_string(log).unwrap_or_default();
    let no_panic = !log_content.contains("panic") && !log_content.contains("FAILED");
    println!(
        "  [{}] No panics or errors in log",
        if no_panic { "PASS" } else { "FAIL" }
    );

    // ── Test 3: Repeated menu open/close ───────────────────────────────────
    println!("\n--- Test 3: Repeated Menu Open/Close ---");

    post_tray_right_click(hwnd);
    thread::sleep(Duration::from_millis(600));
    send_escape();
    thread::sleep(Duration::from_millis(500));

    let still_alive2 = child.try_wait().ok().flatten().is_none();
    println!(
        "  [{}] App survives repeated menu open/close",
        if still_alive2 { "PASS" } else { "FAIL" }
    );

    // ── Cleanup ────────────────────────────────────────────────────────────
    println!("\n--- Final: Read Log & Cleanup ---");

    let _ = child.kill();
    let _ = child.wait();

    // Print key log lines
    println!("\n=== Key Log Lines ===");
    if let Ok(content) = std::fs::read_to_string(log) {
        for line in content.lines() {
            let lower = line.to_lowercase();
            if lower.contains("init")
                || lower.contains("tray")
                || lower.contains("heartbeat")
                || lower.contains("handler")
                || lower.contains("menu")
                || lower.contains("poll")
                || lower.contains("settings")
                || lower.contains("gl")
                || lower.contains("panic")
                || lower.contains("failed")
                || lower.contains("error")
                || lower.contains("exit")
            {
                println!("  {}", line);
            }
        }
    }
    println!("=== End Log ===\n");

    // ── Summary ────────────────────────────────────────────────────────────
    let all_pass =
        pass1 && pass2 && pass3 && still_alive && no_panic && still_alive2;
    println!("=== Layer 1 Summary ===");
    if all_pass {
        println!("  ALL CHECKS PASSED\n");
        println!("  Next: Layer 2 — manual verification by user");
        println!("    1. Right-click tray icon → menu appears");
        println!("    2. Click each menu item → verify action fires");
        println!("    3. Open '设置' → verify Chinese text + GL rendering");
        println!("    4. Click X on settings → verify app stays running");
        println!("    5. Click '退出' → verify process exits cleanly");
        println!("    6. Wait 10s → verify server status polling");
    } else {
        println!("  SOME CHECKS FAILED");
        std::process::exit(1);
    }
}
