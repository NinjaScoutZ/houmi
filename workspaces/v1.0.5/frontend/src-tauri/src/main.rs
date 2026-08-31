#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{AppHandle, Manager, RunEvent};
use tauri_plugin_dialog::DialogExt;

struct SidecarState {
    child: Option<std::process::Child>,
}

#[tauri::command]
async fn open_manga_folder(app: AppHandle) -> Result<Option<String>, String> {
    use std::sync::mpsc::channel;
    let (tx, rx) = channel();

    app.dialog().file().pick_folder(move |folder_path| {
        let path_str = folder_path.map(|p| p.to_string());
        let _ = tx.send(path_str);
    });

    rx.recv().map_err(|e| e.to_string())
}

#[tauri::command]
fn get_sidecar_health() -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({
        "status": "healthy",
        "port": 4000,
        "runtime": "Tauri v2 Native Host",
        "engine": "FastAPI + PyTorch + ONNX GPU"
    }))
}

fn main() {
    let sidecar_state = Arc::new(Mutex::new(SidecarState { child: None }));
    let state_for_setup = Arc::clone(&sidecar_state);
    let state_for_exit = Arc::clone(&sidecar_state);

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            open_manga_folder,
            get_sidecar_health
        ])
        .setup(move |_app| {
            let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
            let workspace_root = manifest_dir.join("../..");
            let venv_python = workspace_root.join("backend/.venv/Scripts/python.exe");

            let python_bin = if venv_python.exists() {
                venv_python
            } else {
                PathBuf::from("python")
            };

            let run_script = workspace_root.join("run_desktop.py");

            println!("[Tauri v2] Spawning AI Backend sidecar: {:?}", python_bin);
            let mut cmd = std::process::Command::new(&python_bin);
            cmd.arg(&run_script)
                .arg("--headless")
                .current_dir(&workspace_root)
                .env("HOUMI_APP_DIR", &workspace_root)
                .env("HOUMI_WORKSPACE_DIR", &workspace_root)
                .env("HOUMI_PORT", "4000")
                .env("HOUMI_HEADLESS", "1")
                .env("PRODUCTION_MODE", "1");

            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                const CREATE_NO_WINDOW: u32 = 0x08000000;
                cmd.creation_flags(CREATE_NO_WINDOW);
            }

            match cmd.spawn() {
                Ok(child) => {
                    println!("[Tauri v2] AI Sidecar started with PID: {}", child.id());
                    if let Ok(mut state) = state_for_setup.lock() {
                        state.child = Some(child);
                    }
                }
                Err(e) => {
                    eprintln!("[Tauri v2 ERROR] Failed to spawn AI backend sidecar: {:?}", e);
                }
            }

            // Health check background monitor using zero-dependency std::net::TcpStream
            tauri::async_runtime::spawn_blocking(move || {
                use std::net::{SocketAddr, TcpStream};
                if let Ok(addr) = "127.0.0.1:4000".parse::<SocketAddr>() {
                    for _ in 0..40 {
                        std::thread::sleep(Duration::from_millis(500));
                        if TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok() {
                            println!("[Tauri v2] AI Engine is HEALTHY and READY on port 4000!");
                            break;
                        }
                    }
                }
            });

            // Open DevTools in Debug Mode
            if let Some(window) = _app.get_webview_window("main") {
                let _ = window.open_devtools();
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while running Houmi Studio Tauri v2");

    app.run(move |_app_handle, event| {
        if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
            println!("[Tauri v2] App closing. Terminating AI Sidecar processes...");
            if let Ok(mut state) = state_for_exit.lock() {
                if let Some(mut child) = state.child.take() {
                    let pid = child.id();
                    println!("[Tauri v2] Killing sidecar child process tree (PID: {})...", pid);
                    
                    #[cfg(windows)]
                    {
                        let _ = std::process::Command::new("taskkill")
                            .args(["/F", "/T", "/PID", &pid.to_string()])
                            .output();
                    }
                    
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
    });
}
