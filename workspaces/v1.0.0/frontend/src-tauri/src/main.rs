#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[cfg(debug_assertions)]
use std::path::PathBuf;

#[cfg(not(debug_assertions))]
use tauri_plugin_shell::{process::CommandEvent, ShellExt};

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|_app| {
            #[cfg(debug_assertions)]
            {
                // Development uses the checked-in Python environment. Release
                // builds use the bundled houmi-local sidecar below.
                let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
                let venv_python = repo_root.join("backend/.venv/Scripts/python.exe");
                let (program, args): (PathBuf, Vec<&str>) = if venv_python.exists() {
                    (
                        venv_python,
                        vec![
                            "backend/desktop_local.py",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            "4317",
                        ],
                    )
                } else {
                    (
                        PathBuf::from("python"),
                        vec![
                            "backend/desktop_local.py",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            "4317",
                        ],
                    )
                };

                let child = std::process::Command::new(program)
                    .args(args)
                    .current_dir(repo_root)
                    .spawn()
                    .expect("failed to start Houmi Local Engine in development");
                tauri::async_runtime::spawn_blocking(move || {
                    let mut child = child;
                    let _ = child.wait();
                });
            }

            #[cfg(not(debug_assertions))]
            {
                let (mut events, child) = _app
                    .shell()
                    .sidecar("houmi-local")?
                    .args(["--host", "127.0.0.1", "--port", "4317"])
                    .spawn()?;

                tauri::async_runtime::spawn(async move {
                    // Keep the child handle alive for the lifetime of the
                    // process and forward a minimal diagnostic to stdout.
                    let _child = child;
                    while let Some(event) = events.recv().await {
                        if let CommandEvent::Terminated(payload) = event {
                            eprintln!("Houmi Local Engine terminated: {:?}", payload);
                            break;
                        }
                    }
                });
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Houmi Studio");
}
