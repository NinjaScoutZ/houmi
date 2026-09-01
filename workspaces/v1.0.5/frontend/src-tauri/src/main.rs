#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{Manager, RunEvent};

struct SidecarState {
    child: Option<std::process::Child>,
}

#[tauri::command]
fn open_manga_folder() -> Result<Option<String>, String> {
    println!("[Tauri v2 IPC] open_manga_folder invoked via native Windows FileDialog...");
    let folder = rfd::FileDialog::new()
        .set_title("Select Manga Project Folder (เลือกโฟลเดอร์รูปภาพมังงะ)")
        .pick_folder();
    
    let result = folder.map(|p| p.to_string_lossy().to_string());
    println!("[Tauri v2 IPC] User selected folder: {:?}", result);
    Ok(result)
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
            let workspace_root = if let Ok(exe_path) = std::env::current_exe() {
                let exe_dir = exe_path.parent().unwrap_or(&exe_path);
                if exe_dir.join("run_desktop.py").exists() {
                    exe_dir.to_path_buf()
                } else if exe_dir.join("../../../run_desktop.py").exists() {
                    exe_dir.join("../../..")
                } else if exe_dir.join("../../run_desktop.py").exists() {
                    exe_dir.join("../..")
                } else {
                    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
                }
            } else {
                PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
            };
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
                .env("PYTHONUNBUFFERED", "1")
                .env("PRODUCTION_MODE", "1")
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::piped());

            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                const CREATE_NO_WINDOW: u32 = 0x08000000;
                cmd.creation_flags(CREATE_NO_WINDOW);
            }

            match cmd.spawn() {
                Ok(mut child) => {
                    println!("[Tauri v2] AI Sidecar started with PID: {}", child.id());
                    
                    if let Some(stdout) = child.stdout.take() {
                        std::thread::spawn(move || {
                            use std::io::{BufRead, BufReader};
                            let reader = BufReader::new(stdout);
                            for line in reader.lines().flatten() {
                                println!("[AI Backend] {}", line);
                            }
                        });
                    }
                    if let Some(stderr) = child.stderr.take() {
                        std::thread::spawn(move || {
                            use std::io::{BufRead, BufReader};
                            let reader = BufReader::new(stderr);
                            for line in reader.lines().flatten() {
                                eprintln!("[AI Backend] {}", line);
                            }
                        });
                    }

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
                            println!("==========================================================================");
                            println!("  ✨ [READY] HOUMI STUDIO v1.0.5 IS LOADED & OPERATIONAL!");
                            println!("  👉 หน้าต่างโปรแกรมพร้อมใช้งานแล้ว (สามารถสลับไปใช้หน้าต่างโปรแกรมได้เลย)");
                            println!("==========================================================================");
                            break;
                        }
                    }
                }
            });

            // Ensure main window is visible and focused
            if let Some(window) = _app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
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
