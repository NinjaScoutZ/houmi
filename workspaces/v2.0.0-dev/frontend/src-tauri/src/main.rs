#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[cfg(debug_assertions)]
use std::path::PathBuf;

#[cfg(not(debug_assertions))]
use tauri_plugin_shell::{process::CommandEvent, ShellExt};

#[cfg(windows)]
extern "system" {
    fn AttachConsole(dwProcessId: u32) -> i32;
}

fn main() {
    #[cfg(windows)]
    unsafe {
        // Attach to the parent console if launched from CMD or batch script
        AttachConsole(0xFFFFFFFF);
    }

    println!("=========================================================");
    println!("  HOUMI MANGA & WEBTOON TRANSLATION STUDIO v2.0.0");
    println!("  Tauri v2 Native Desktop Engine");
    println!("=========================================================");

    tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|_app| {
            #[cfg(debug_assertions)]
            {
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

                println!("⚡ [Dev] Spawning Local AI Backend: {:?}", program);
                match std::process::Command::new(program)
                    .args(args)
                    .current_dir(repo_root)
                    .spawn()
                {
                    Ok(mut child) => {
                        tauri::async_runtime::spawn_blocking(move || {
                            let _ = child.wait();
                        });
                    }
                    Err(e) => {
                        eprintln!("❌ Warning: failed to start Local Engine in development: {:?}", e);
                    }
                }
            }

            #[cfg(not(debug_assertions))]
            {
                println!("⚡ [Release] Initializing Python AI Sidecar on 127.0.0.1:4317 ...");
                match _app
                    .shell()
                    .sidecar("houmi-local")
                    .and_then(|cmd| cmd.args(["--host", "127.0.0.1", "--port", "4317"]).spawn())
                {
                    Ok((mut events, child)) => {
                        println!("✓ Python AI Sidecar successfully spawned!");
                        tauri::async_runtime::spawn(async move {
                            while let Some(event) = events.recv().await {
                                match event {
                                    CommandEvent::Stdout(line) => {
                                        print!("{}", String::from_utf8_lossy(&line));
                                    }
                                    CommandEvent::Stderr(line) => {
                                        eprint!("{}", String::from_utf8_lossy(&line));
                                    }
                                    CommandEvent::Terminated(payload) => {
                                        eprintln!("Houmi Local Engine terminated: {:?}", payload);
                                        break;
                                    }
                                    CommandEvent::Error(err) => {
                                        eprintln!("Houmi Local Engine error: {}", err);
                                    }
                                    _ => {}
                                }
                            }
                            let _ = child.kill();
                        });
                    }
                    Err(e) => {
                        eprintln!("❌ Warning: failed to start Houmi Local Engine sidecar: {:?}", e);
                    }
                }
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Houmi Studio");
}
