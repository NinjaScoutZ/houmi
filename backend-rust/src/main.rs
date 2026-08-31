#![windows_subsystem = "windows"]

mod config;

use std::process::{Command, Child};
use std::sync::Arc;
use std::thread;
use std::time::Duration;
use std::net::{TcpStream, SocketAddr};
use crate::config::Config;

use tao::{
    event::{Event, WindowEvent},
    event_loop::{ControlFlow, EventLoopBuilder},
    window::WindowBuilder,
};
use wry::WebViewBuilder;

#[derive(Debug)]
enum UserEvent {
    ServerReady,
}

const LOADING_HTML: &str = r#"
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Loading Houmi Studio</title>
    <style>
        :root {
            --bg-color: #0b0f19;
            --text-color: #f1f5f9;
            --accent-color: #f59e0b; /* Amber */
            --accent-glow: rgba(245, 158, 11, 0.4);
            --secondary-text: #94a3b8;
            --card-bg: rgba(30, 41, 59, 0.5);
            --card-border: rgba(255, 255, 255, 0.05);
        }
        
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            overflow: hidden;
        }

        .container {
            text-align: center;
            max-width: 480px;
            padding: 2.5rem;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 24px;
            backdrop-filter: blur(12px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
            animation: fadeIn 0.8s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .logo-container {
            position: relative;
            width: 80px;
            height: 80px;
            margin: 0 auto 2rem;
        }

        .logo-ring {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: 4px solid rgba(255, 255, 255, 0.03);
            border-top: 4px solid var(--accent-color);
            border-radius: 50%;
            animation: spin 1.2s cubic-bezier(0.5, 0.1, 0.5, 0.9) infinite;
            box-shadow: 0 0 15px var(--accent-glow);
        }

        .logo-ring-inner {
            position: absolute;
            top: 12px;
            left: 12px;
            right: 12px;
            bottom: 12px;
            border: 2px solid rgba(255, 255, 255, 0.02);
            border-bottom: 2px solid var(--accent-color);
            border-radius: 50%;
            animation: spin-reverse 2s linear infinite;
            opacity: 0.6;
        }

        .logo-icon {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 24px;
            font-weight: bold;
            color: var(--accent-color);
            text-shadow: 0 0 10px var(--accent-glow);
            animation: pulse 2s ease-in-out infinite;
        }

        h1 {
            font-size: 1.5rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
            letter-spacing: -0.025em;
            background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        p {
            font-size: 0.95rem;
            color: var(--secondary-text);
            line-height: 1.5;
            margin-bottom: 1.5rem;
        }

        .progress-bar-container {
            width: 100%;
            height: 6px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 99px;
            overflow: hidden;
            position: relative;
            margin-bottom: 0.75rem;
        }

        .progress-bar-fill {
            position: absolute;
            left: 0;
            top: 0;
            height: 100%;
            width: 50%;
            background: linear-gradient(90deg, transparent, var(--accent-color), transparent);
            border-radius: 99px;
            animation: loadingProgress 1.5s infinite linear;
        }

        .status-text {
            font-size: 0.8rem;
            color: var(--accent-color);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 500;
            opacity: 0.8;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(16px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        @keyframes spin-reverse {
            0% { transform: rotate(360deg); }
            100% { transform: rotate(0deg); }
        }

        @keyframes pulse {
            0%, 100% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
            50% { transform: translate(-50%, -50%) scale(0.95); opacity: 0.8; }
        }

        @keyframes loadingProgress {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(200%); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo-container">
            <div class="logo-ring"></div>
            <div class="logo-ring-inner"></div>
            <div class="logo-icon">HM</div>
        </div>
        <h1>Houmi Translation Studio</h1>
        <p>Warming up local AI engines and database. This will take just a moment...</p>
        <div class="progress-bar-container">
            <div class="progress-bar-fill"></div>
        </div>
        <div class="status-text">Starting Backend Services...</div>
    </div>
</body>
</html>
"#;

fn force_kill_port_owner(port: u16) {
    println!("[INFO] force-kill-port: Checking for any process holding port {}...", port);
    
    #[cfg(target_os = "windows")]
    {
        let mut netstat_cmd = std::process::Command::new("netstat");
        netstat_cmd.args(&["-a", "-o", "-n"]);
        
        use std::os::windows::process::CommandExt;
        netstat_cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
        
        if let Ok(output) = netstat_cmd.output() {
            let stdout_str = String::from_utf8_lossy(&output.stdout);
            let port_str = port.to_string();
            for line in stdout_str.lines() {
                let tokens: Vec<&str> = line.split_whitespace().collect();
                if tokens.len() >= 4 {
                    let proto = tokens[0].to_uppercase();
                    if proto == "TCP" || proto == "UDP" {
                        let local_addr = tokens[1];
                        if let Some(pos) = local_addr.rfind(':') {
                            let port_part = &local_addr[pos + 1..];
                            if port_part == port_str {
                                if let Some(pid_str) = tokens.last() {
                                    if let Ok(pid) = pid_str.parse::<u32>() {
                                        if pid <= 4 {
                                            println!("[WARNING] force-kill-port: Refusing to kill critical system PID {}", pid);
                                            continue;
                                        }
                                        println!("[WARNING] force-kill-port: Found process (PID: {}) using port {}. Killing it...", pid, port);
                                        let mut kill_cmd = std::process::Command::new("taskkill");
                                        kill_cmd.args(&["/F", "/PID", &pid.to_string()]);
                                        kill_cmd.creation_flags(0x08000000);
                                        let _ = kill_cmd.output();
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

fn kill_process_tree(mut child: Child) {
    let pid = child.id();
    println!("[INFO] Terminating Python backend process tree (PID: {})...", pid);
    
    #[cfg(target_os = "windows")]
    {
        let mut kill_cmd = std::process::Command::new("taskkill");
        kill_cmd.args(&["/F", "/T", "/PID", &pid.to_string()]);
        use std::os::windows::process::CommandExt;
        kill_cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
        let _ = kill_cmd.output();
    }
    
    let _ = child.kill();
    let _ = child.wait();
}

fn main() {
    let config = Arc::new(Config::load());
    
    // 1. Force kill prior zombie processes on the backend port (4000) and OCR port (2322)
    force_kill_port_owner(config.port);
    force_kill_port_owner(config.ocr_port);
    
    // 2. Spawn Python backend subprocess
    let mut cmd = Command::new(&config.python_path);
    cmd.args(&[
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        &config.port.to_string(),
    ])
    .current_dir(&config.backend_dir)
    .env("HOUMI_PORT", config.port.to_string())
    .env("OCR_PORT", config.ocr_port.to_string())
    .stdout(std::process::Stdio::null())
    .stderr(std::process::Stdio::null());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }

    let mut backend_process = match cmd.spawn() {
        Ok(child) => {
            println!("[INFO] Python backend process spawned successfully (PID: {}).", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[ERROR] Failed to start Python backend: {}", e);
            None
        }
    };

    // 3. Build Tao Event Loop & Window
    let event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
    let window = WindowBuilder::new()
        .with_title("Houmi Translation Studio")
        .with_inner_size(tao::dpi::LogicalSize::new(1280.0, 800.0))
        .with_min_inner_size(tao::dpi::LogicalSize::new(1024.0, 768.0))
        .build(&event_loop)
        .unwrap();

    // 4. Initialize Wry WebView with Premium Dark loading screen HTML
    let webview = WebViewBuilder::new()
        .with_html(LOADING_HTML)
        .build(&window)
        .unwrap();

    let webview_ref = Some(webview);
    let app_url = format!("http://127.0.0.1:{}/", config.port);

    // 5. Spawn background thread to poll port 4000 for readiness
    let proxy = event_loop.create_proxy();
    let poll_port = config.port;
    thread::spawn(move || {
        let addr_str = format!("127.0.0.1:{}", poll_port);
        let addr: SocketAddr = addr_str.parse().expect("Failed to parse local server address");
        
        // Give subprocess a tiny headstart
        thread::sleep(Duration::from_millis(500));
        
        println!("[INFO] Polling {} for readiness...", addr_str);
        loop {
            if TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok() {
                println!("[INFO] Backend server ready. Dispatching ready event.");
                let _ = proxy.send_event(UserEvent::ServerReady);
                break;
            }
            thread::sleep(Duration::from_millis(200));
        }
    });

    // 6. Run Event Loop
    event_loop.run(move |event, _, control_flow| {
        *control_flow = ControlFlow::Wait;

        match event {
            Event::UserEvent(UserEvent::ServerReady) => {
                if let Some(ref wv) = webview_ref {
                    println!("[INFO] Redirecting WebView to app: {}", app_url);
                    let _ = wv.load_url(&app_url);
                }
            }
            Event::WindowEvent {
                event: WindowEvent::CloseRequested,
                ..
            } => {
                println!("[INFO] Window close requested. Exiting event loop.");
                if let Some(child) = backend_process.take() {
                    kill_process_tree(child);
                }
                *control_flow = ControlFlow::Exit;
            }
            _ => {}
        }
    });
}
