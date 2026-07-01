// System tray icon + menu
// Menu structure:
//   Loop: <status>
//   ───────────────
//   <Project A> ▼
//     ├─ 打开 Dashboard
//     ├─ ────────────
//     ├─ 暂停/恢复 Loop
//     ├─ 停止 Loop
//     ├─ 启动 Loop
//   <Project B> ▼
//     ├─ ...
//   ───────────────
//   新增项目
//   ───────────────
//   设置...
//   ───────────────
//   退出

use tray_icon::menu::{Menu, MenuItem, Submenu};
use tray_icon::{Icon, TrayIcon, TrayIconBuilder};

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

// ── Project menu data ─────────────────────────────────────────────────────

pub struct ProjectMenu {
    pub name: String,
    pub root: String,
    #[allow(dead_code)]
    pub agent_dir: String,
    pub dashboard: MenuItem,
    pub sep: MenuItem,
    pub pause: MenuItem,
    pub resume: MenuItem,
    pub stop_loop: MenuItem,
    pub start_loop: MenuItem,
}

impl ProjectMenu {
    /// Check if a menu event ID belongs to this project, and return which action.
    pub fn match_event(&self, id: &tray_icon::menu::MenuId) -> Option<ProjectAction> {
        if *id == self.dashboard.id() {
            Some(ProjectAction::OpenDashboard)
        } else if *id == self.pause.id() {
            Some(ProjectAction::Pause)
        } else if *id == self.resume.id() {
            Some(ProjectAction::Resume)
        } else if *id == self.stop_loop.id() {
            Some(ProjectAction::Stop)
        } else if *id == self.start_loop.id() {
            Some(ProjectAction::Start)
        } else {
            None
        }
    }

    /// Rebuild this project's submenu based on loop state.
    fn rebuild_submenu(&self, running: bool, paused: bool) -> Submenu {
        let mut items: Vec<&dyn tray_icon::menu::IsMenuItem> = Vec::with_capacity(6);
        items.push(&self.dashboard);
        items.push(&self.sep);

        if !running {
            items.push(&self.start_loop);
        } else {
            items.push(if paused { &self.resume } else { &self.pause });
            items.push(&self.stop_loop);
        }

        Submenu::with_items(&self.name, true, &items).unwrap()
    }
}

pub enum ProjectAction {
    OpenDashboard,
    Pause,
    Resume,
    Stop,
    Start,
}

// ── Main tray items ───────────────────────────────────────────────────────

pub struct TrayMenuItems {
    pub sep1: MenuItem,
    pub add_project: MenuItem,
    pub sep2: MenuItem,
    pub settings: MenuItem,
    pub sep3: MenuItem,
    pub quit: MenuItem,
    pub projects: Vec<ProjectMenu>,
    /// Owned submenus — rebuilt by `build_menu()` and referenced by the `Menu`.
    /// Stored here so they live as long as the `TrayMenuItems` (no Box::leak).
    pub project_submenus: Vec<Submenu>,
}

#[derive(Clone)]
pub struct TrayMenuIds {
    pub add_project: tray_icon::menu::MenuId,
    pub settings: tray_icon::menu::MenuId,
    pub quit: tray_icon::menu::MenuId,
}

impl TrayMenuItems {
    pub fn clone_ids(&self) -> TrayMenuIds {
        TrayMenuIds {
            add_project: self.add_project.id().clone(),
            settings: self.settings.id().clone(),
            quit: self.quit.id().clone(),
        }
    }
}

// ── Menu builder ──────────────────────────────────────────────────────────

pub fn build_menu(items: &mut TrayMenuItems, running: bool, paused: bool) -> Menu {
    // Rebuild owned submenus (drops old ones, no leak)
    items.project_submenus.clear();
    for proj in &items.projects {
        items.project_submenus.push(proj.rebuild_submenu(running, paused));
    }

    let mut refs: Vec<&dyn tray_icon::menu::IsMenuItem> =
        Vec::with_capacity(items.project_submenus.len() + 5);
    for submenu in &items.project_submenus {
        refs.push(submenu as &dyn tray_icon::menu::IsMenuItem);
    }

    refs.push(&items.sep1);
    refs.push(&items.add_project);
    refs.push(&items.sep2);
    refs.push(&items.settings);
    refs.push(&items.sep3);
    refs.push(&items.quit);

    Menu::with_items(&refs).unwrap()
}

// ── Factory ───────────────────────────────────────────────────────────────

pub fn create_tray() -> (TrayIcon, TrayMenuItems, TrayMenuIds) {
    let icon = create_icon();

    let sep1 = MenuItem::new("───────────────", false, None);
    let add_project = MenuItem::new("新增项目", true, None);
    let sep2 = MenuItem::new("───────────────", false, None);
    let settings = MenuItem::new("设置...", true, None);
    let sep3 = MenuItem::new("───────────────", false, None);
    let quit = MenuItem::new("退出", true, None);

    let projects_data = find_projects(&exe_dir());
    let mut project_menus: Vec<ProjectMenu> = Vec::new();

    for p in &projects_data {
        let dashboard = MenuItem::new("打开 Dashboard", true, None);
        let sep = MenuItem::new("───────────────", false, None);
        let pause = MenuItem::new("暂停 Loop", true, None);
        let resume = MenuItem::new("恢复 Loop", true, None);
        let stop_loop = MenuItem::new("停止 Loop", true, None);
        let start_loop = MenuItem::new("启动 Loop", true, None);

        project_menus.push(ProjectMenu {
            name: p.name.clone(),
            root: p.root.clone(),
            agent_dir: p.agent_dir.clone(),
            dashboard,
            sep,
            pause,
            resume,
            stop_loop,
            start_loop,
        });
    }

    // Build initial menu (loop not running)
    let mut items = TrayMenuItems {
        sep1,
        add_project,
        sep2,
        settings,
        sep3,
        quit,
        projects: project_menus,
        project_submenus: Vec::new(),
    };

    let menu = build_menu(&mut items, false, false);

    let tray_icon = TrayIconBuilder::new()
        .with_menu(Box::new(menu))
        .with_icon(icon)
        .with_tooltip("Loop Engineering")
        .build()
        .unwrap();

    let ids = items.clone_ids();

    (tray_icon, items, ids)
}

// ── Project discovery ─────────────────────────────────────────────────────

struct ProjectInfo {
    name: String,
    root: String,
    agent_dir: String,
}

fn exe_dir() -> std::path::PathBuf {
    std::env::current_exe().unwrap().parent().unwrap().to_path_buf()
}

fn find_projects(_exe_dir: &std::path::Path) -> Vec<ProjectInfo> {
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
                            let ws = cfg.get("agent")
                                .and_then(|a| a.get("workspace"))
                                .and_then(|v| v.as_str()).unwrap_or("");
                            let pname = cfg.get("project")
                                .and_then(|p| p.get("name"))
                                .and_then(|v| v.as_str()).unwrap_or(name);
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
