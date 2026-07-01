// System tray icon + menu

use tray_icon::menu::{Menu, MenuItem, Submenu};
use tray_icon::{Icon, TrayIcon, TrayIconBuilder};

/// Spawn a static turquoise icon (32x32) as raw RGBA bytes
fn create_icon() -> Icon {
    let mut pixels = vec![0u8; 32 * 32 * 4];
    let cx = 16.0;
    let cy = 16.0;
    let r = 14.0;
    for y in 0..32 {
        for x in 0..32 {
            let dx = x as f64 - cx;
            let dy = y as f64 - cy;
            let dist = (dx * dx + dy * dy).sqrt();
            let idx = (y * 32 + x) as usize * 4;
            if dist <= r {
                pixels[idx] = 59;
                pixels[idx + 1] = 130;
                pixels[idx + 2] = 246;
                pixels[idx + 3] = 255;
            }
        }
    }
    Icon::from_rgba(pixels, 32, 32).unwrap()
}

pub struct TrayMenuItems {
    pub status: MenuItem,
    pub pause: MenuItem,
    pub resume: MenuItem,
    pub stop_loop: MenuItem,
    pub start_loop: MenuItem,
    pub open_dashboard: MenuItem,
    pub add_project: MenuItem,
    pub settings: MenuItem,
    pub autostart: MenuItem,
    pub quit: MenuItem,
    pub projects: Vec<ProjectItem>,
}

impl TrayMenuItems {
    pub fn clone_ids(&self) -> TrayMenuIds {
        TrayMenuIds {
            status: self.status.id().clone(),
            pause: self.pause.id().clone(),
            resume: self.resume.id().clone(),
            stop_loop: self.stop_loop.id().clone(),
            start_loop: self.start_loop.id().clone(),
            open_dashboard: self.open_dashboard.id().clone(),
            add_project: self.add_project.id().clone(),
            settings: self.settings.id().clone(),
            autostart: self.autostart.id().clone(),
            quit: self.quit.id().clone(),
        }
    }
}

#[derive(Clone)]
pub struct TrayMenuIds {
    pub status: tray_icon::menu::MenuId,
    pub pause: tray_icon::menu::MenuId,
    pub resume: tray_icon::menu::MenuId,
    pub stop_loop: tray_icon::menu::MenuId,
    pub start_loop: tray_icon::menu::MenuId,
    pub open_dashboard: tray_icon::menu::MenuId,
    pub add_project: tray_icon::menu::MenuId,
    pub settings: tray_icon::menu::MenuId,
    pub autostart: tray_icon::menu::MenuId,
    pub quit: tray_icon::menu::MenuId,
}

pub struct ProjectItem {
    pub id: tray_icon::menu::MenuId,
    pub name: String,
    pub root: String,
    pub agent_dir: String,
}

/// Create the system tray icon and menu. Returns the TrayIcon (must be kept alive),
/// the menu items (for state updates), and the menu IDs (for event matching).
pub fn create_tray() -> (TrayIcon, TrayMenuItems, TrayMenuIds) {
    let icon = create_icon();

    let status = MenuItem::new("Loop: 未启动", false, None);
    let sep1 = MenuItem::new("───────────────", false, None);
    let pause = MenuItem::new("暂停 Loop", true, None);
    let resume = MenuItem::new("恢复 Loop", true, None);
    let stop_loop = MenuItem::new("停止 Loop", true, None);
    let start_loop = MenuItem::new("启动 Loop", true, None);
    let sep2 = MenuItem::new("───────────────", false, None);
    let open_dashboard = MenuItem::new("打开 Dashboard", true, None);
    let sep3 = MenuItem::new("───────────────", false, None);
    let add_project = MenuItem::new("新增项目", true, None);
    let sep4 = MenuItem::new("───────────────", false, None);
    let settings = MenuItem::new("设置...", true, None);
    let sep5 = MenuItem::new("───────────────", false, None);
    let autostart = MenuItem::new("✓ 开机自启", true, None);
    let sep6 = MenuItem::new("───────────────", false, None);
    let quit = MenuItem::new("退出", true, None);

    // Build projects submenu
    let projects = find_projects(&exe_dir());
    let mut proj_data: Vec<ProjectItem> = Vec::new();
    let mut menu_refs: Vec<&dyn tray_icon::menu::IsMenuItem> = Vec::new();
    let placeholder = MenuItem::new("（无项目）", false, None);

    for p in &projects {
        let item = Box::new(MenuItem::new(&p.name, true, None));
        proj_data.push(ProjectItem {
            id: item.id().clone(),
            name: p.name.clone(),
            root: p.root.clone(),
            agent_dir: p.agent_dir.clone(),
        });
        menu_refs.push(Box::leak(item) as &dyn tray_icon::menu::IsMenuItem);
    }

    let projects_menu = if menu_refs.is_empty() {
        Submenu::with_items("项目", true, &[&placeholder as &dyn tray_icon::menu::IsMenuItem]).unwrap()
    } else {
        Submenu::with_items("项目", true, &menu_refs).unwrap()
    };

    let menu = Menu::with_items(&[
        &status, &sep1,
        &pause, &resume, &stop_loop, &start_loop,
        &sep2,
        &open_dashboard,
        &sep3,
        &add_project, &projects_menu,
        &sep4,
        &settings,
        &sep5,
        &autostart,
        &sep6,
        &quit,
    ]).unwrap();

    let tray_icon = TrayIconBuilder::new()
        .with_menu(Box::new(menu))
        .with_icon(icon)
        .with_tooltip("Loop Engineering")
        .build()
        .unwrap();

    start_loop.set_enabled(true);
    pause.set_enabled(false);
    resume.set_enabled(false);
    stop_loop.set_enabled(false);

    let items = TrayMenuItems {
        status, pause, resume, stop_loop, start_loop,
        open_dashboard, add_project, settings, autostart, quit,
        projects: proj_data,
    };

    let ids = items.clone_ids();

    (tray_icon, items, ids)
}

struct ProjectInfo {
    name: String,
    root: String,
    agent_dir: String,
}

fn exe_dir() -> std::path::PathBuf {
    std::env::current_exe().unwrap().parent().unwrap().to_path_buf()
}

fn find_projects(_exe_dir: &std::path::Path) -> Vec<ProjectInfo> {
    // Read from ~/.config/loop-engineering/projects.yaml (same as Python registry)
    let registry_path = dirs::home_dir()
        .unwrap_or_default()
        .join(".config")
        .join("loop-engineering")
        .join("projects.yaml");

    let mut projects = Vec::new();

    if let Ok(data) = std::fs::read_to_string(&registry_path) {
        if let Ok(doc) = serde_yaml::from_str::<serde_yaml::Value>(&data) {
            if let Some(proj_list) = doc.get("projects").and_then(|v| v.as_sequence()) {
                for entry in proj_list {
                    let root = entry.get("root").and_then(|v| v.as_str()).unwrap_or("");
                    let name = entry.get("name").and_then(|v| v.as_str()).unwrap_or("");

                    if root.is_empty() { continue; }

                    let root_path = std::path::Path::new(root);
                    let config_path = root_path.join(".loop-engineering").join("loop-config.yaml");
                    if !config_path.exists() { continue; }

                    if root_path.join(".git").is_file() { continue; }
                    let agent_dir = if let Ok(cfg_data) = std::fs::read_to_string(&config_path) {
                        if let Ok(cfg) = serde_yaml::from_str::<serde_yaml::Value>(&cfg_data) {
                            let ws = cfg.get("agent").and_then(|a| a.get("workspace")).and_then(|v| v.as_str()).unwrap_or("");
                            let pname = cfg.get("project").and_then(|p| p.get("name")).and_then(|v| v.as_str()).unwrap_or(name);
                            format!("{}/{}", ws, pname)
                        } else { String::new() }
                    } else { String::new() };

                    projects.push(ProjectInfo {
                        name: name.to_string(),
                        root: root.to_string(),
                        agent_dir,
                    });
                }
            }
        }
    }

    projects
}
