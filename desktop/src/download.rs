//! HTTP Range-aware download with resume support for update packages.
//!
//! Velopack's built-in `download_updates()` has no resume capability.
//! This module replaces it with a custom download that uses HTTP Range
//! requests to resume interrupted downloads from where they left off.

use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

// ── DownloadState ──────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, Debug)]
struct DownloadState {
    url: String,
    expected_size: u64,
    bytes_downloaded: u64,
    version: String,
}

// ── Public API ─────────────────────────────────────────────────────────────

/// Update the URL in a download-state file (keeps the same offset).
/// Used when the original S3 signed URL expires and a fresh one is needed.
pub fn refresh_state_url(state_path: &Path, new_url: &str) -> Result<(), String> {
    let content = std::fs::read_to_string(state_path)
        .map_err(|e| format!("read state: {}", e))?;
    let mut state: DownloadState = serde_json::from_str(&content)
        .map_err(|e| format!("parse state: {}", e))?;
    state.url = new_url.to_string();
    let json = serde_json::to_string(&state)
        .map_err(|e| format!("serialize state: {}", e))?;
    std::fs::write(state_path, json)
        .map_err(|e| format!("write state: {}", e))
}

/// Construct the GitHub CDN download URL for a release asset.
///
/// Public repos: github.com/releases/download/ uses Fastly CDN with global
/// edge nodes — much faster than the S3 redirect path, especially from Asia.
///
/// Returns: `https://github.com/{owner}/{repo}/releases/download/v{version}/{filename}`
pub fn get_github_release_url(repo_url: &str, version: &str, filename: &str) -> Result<String, String> {
    let path = repo_url
        .strip_prefix("https://github.com/")
        .or_else(|| repo_url.strip_prefix("http://github.com/"))
        .ok_or_else(|| format!("invalid repo URL: {}", repo_url))?;
    let path = path.trim_end_matches('/');
    let parts: Vec<&str> = path.split('/').collect();
    if parts.len() < 2 {
        return Err(format!("cannot parse owner/repo from: {}", repo_url));
    }
    let owner = parts[0];
    let repo = parts[1];

    Ok(format!(
        "https://github.com/{}/{}/releases/download/v{}/{}",
        owner, repo, version, filename
    ))
}

/// Download a file with HTTP Range resume support.
///
/// The download is streamed to `<packages_dir>/<filename>.partial`, with
/// progress state saved to `<packages_dir>/<filename>.download-state.json`.
/// On successful completion, the `.partial` file is renamed to the final
/// filename and the state file is deleted.
///
/// `progress` is called with floor-rounded percentage (0-100) whenever it
/// changes. It is invoked from the download thread.
pub fn download_with_resume(
    url: &str,
    packages_dir: &Path,
    filename: &str,
    expected_size: u64,
    token: &str,
    progress: impl Fn(u32) + Send + 'static,
) -> Result<PathBuf, String> {
    fs::create_dir_all(packages_dir)
        .map_err(|e| format!("cannot create packages dir: {}", e))?;

    let partial_path = packages_dir.join(format!("{}.partial", filename));
    let final_path = packages_dir.join(filename);
    let state_path = packages_dir.join(format!("{}.download-state.json", filename));

    // Already fully downloaded?
    if final_path.exists() {
        let existing = fs::metadata(&final_path)
            .map_err(|e| format!("stat final: {}", e))?;
        if existing.len() == expected_size {
            return Ok(final_path);
        }
        // Size mismatch — delete and re-download
        let _ = fs::remove_file(&final_path);
    }

    // Determine resume offset
    let start_offset = load_state(&state_path, url, expected_size)
        .unwrap_or(0)
        .min(partial_path.metadata().map(|m| m.len()).unwrap_or(0));

    // If no state but partial exists, or mismatch, clean up
    if start_offset == 0 {
        let _ = fs::remove_file(&partial_path);
        let _ = fs::remove_file(&state_path);
    }

    // Open file for append (or create)
    let mut file = if start_offset > 0 {
        std::fs::OpenOptions::new()
            .append(true)
            .open(&partial_path)
            .map_err(|e| format!("open partial for append: {}", e))?
    } else {
        fs::File::create(&partial_path)
            .map_err(|e| format!("create partial: {}", e))?
    };

    progress(0);

    // Build HTTP request
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_global(Some(std::time::Duration::from_secs(7200))) // 2h total
        .timeout_connect(Some(std::time::Duration::from_secs(60)))
        .timeout_recv_response(Some(std::time::Duration::from_secs(120)))
        .timeout_recv_body(Some(std::time::Duration::from_secs(120)))
        .build()
        .into();

    let mut req = agent
        .get(url)
        .header("Accept", "application/octet-stream")
        .header("Authorization", &format!("Bearer {}", token))
        .header("User-Agent", "LoopDashboard/1.0");

    if start_offset > 0 {
        req = req.header("Range", &format!("bytes={}-", start_offset));
    }

    let response = req.call().map_err(|e| format!("HTTP request failed: {}", e))?;

    let status = response.status();
    let status_code = status.as_u16();
    let (total_for_progress, mut bytes_downloaded) = match status_code {
        206 => {
            // Normal resume — parse Content-Range for total size
            (expected_size, start_offset)
        }
        200 if start_offset > 0 => {
            // Server ignored Range — restart from scratch
            file = fs::File::create(&partial_path)
                .map_err(|e| format!("re-create partial: {}", e))?;
            (expected_size, 0u64)
        }
        200 => {
            // Normal first download
            (expected_size, 0u64)
        }
        416 => {
            // Range not satisfiable — file may already be complete
            let existing = partial_path
                .metadata()
                .map(|m| m.len())
                .unwrap_or(0);
            if existing == expected_size {
                fs::rename(&partial_path, &final_path)
                    .map_err(|e| format!("rename partial→final: {}", e))?;
                let _ = fs::remove_file(&state_path);
                return Ok(final_path);
            }
            // Size mismatch — restart
            file = fs::File::create(&partial_path)
                .map_err(|e| format!("re-create partial after 416: {}", e))?;
            (expected_size, 0u64)
        }
        code => {
            let body_str = response.into_body().read_to_string().unwrap_or_default();
            return Err(format!("unexpected HTTP {}: {}", code, body_str));
        }
    };

    // Stream body to file
    let mut reader = response.into_body().into_reader();
    let mut buf = vec![0u8; 65536]; // 64KB chunks
    let mut last_pct = 0u32;

    loop {
        let n = reader
            .read(&mut buf)
            .map_err(|e| format!("read error: {}", e))?;
        if n == 0 {
            break;
        }
        file.write_all(&buf[..n])
            .map_err(|e| format!("write error: {}", e))?;
        file.flush()
            .map_err(|e| format!("flush error: {}", e))?;

        bytes_downloaded += n as u64;

        // Save state and report progress
        save_state(
            &state_path,
            url,
            expected_size,
            bytes_downloaded,
        );

        let pct = if total_for_progress > 0 {
            ((bytes_downloaded * 100) / total_for_progress) as u32
        } else {
            0
        };
        if pct != last_pct {
            last_pct = pct;
            progress(pct);
        }
    }

    // Verify
    if bytes_downloaded != expected_size {
        let _ = fs::remove_file(&partial_path);
        let _ = fs::remove_file(&state_path);
        return Err(format!(
            "size mismatch: expected {}, got {}",
            expected_size, bytes_downloaded
        ));
    }

    // Finalize
    fs::rename(&partial_path, &final_path)
        .map_err(|e| format!("rename partial→final: {}", e))?;
    let _ = fs::remove_file(&state_path);

    progress(100);
    Ok(final_path)
}

// ── Internal helpers ───────────────────────────────────────────────────────

fn load_state(state_path: &Path, url: &str, expected_size: u64) -> Option<u64> {
    let content = fs::read_to_string(state_path).ok()?;
    let state: DownloadState = serde_json::from_str(&content).ok()?;
    if state.url != url || state.expected_size != expected_size {
        return None; // URL or size changed — stale state
    }
    Some(state.bytes_downloaded)
}

fn save_state(state_path: &Path, url: &str, expected_size: u64, bytes_downloaded: u64) {
    let state = DownloadState {
        url: url.to_string(),
        expected_size,
        bytes_downloaded,
        version: env!("CARGO_PKG_VERSION").to_string(),
    };
    if let Ok(json) = serde_json::to_string(&state) {
        // Write to temp file, then rename (atomic on same filesystem)
        let tmp = state_path.with_extension("download-state.json.tmp");
        if fs::write(&tmp, json).is_ok() {
            let _ = fs::rename(&tmp, state_path);
        }
    }
}
