use std::path::PathBuf;
use std::env;

#[derive(Debug, Clone)]
pub struct Config {
    pub port: u16,
    pub ocr_port: u16,
    pub python_path: PathBuf,
    pub backend_dir: PathBuf,
}

impl Config {
    pub fn load() -> Self {
        let exe_dir = env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.to_path_buf()))
            .unwrap_or_else(|| PathBuf::from("."));
            
        let mut root_dir = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        if root_dir.ends_ok_with("backend-rust") {
            root_dir = root_dir.parent().unwrap().to_path_buf();
        } else if exe_dir.to_string_lossy().contains("target") {
            let mut p = exe_dir.clone();
            while p.pop() {
                if p.join("Run-Houmi-Desktop.bat").exists() || p.join("backend").exists() {
                    root_dir = p;
                    break;
                }
            }
        }
        
        let backend_dir = root_dir.join("backend");
        
        // Find python path inside backend/.venv or fallback
        let python_path = if cfg!(target_os = "windows") {
            backend_dir.join(".venv").join("Scripts").join("python.exe")
        } else {
            backend_dir.join(".venv").join("bin").join("python")
        };

        let port = env::var("HOUMI_PORT")
            .ok()
            .and_then(|p| p.parse().ok())
            .unwrap_or(4000);
            
        let ocr_port = env::var("OCR_PORT")
            .ok()
            .and_then(|p| p.parse().ok())
            .unwrap_or(2322);

        Self {
            port,
            ocr_port,
            python_path,
            backend_dir,
        }
    }
}

trait PathBufExt {
    fn ends_ok_with(&self, suffix: &str) -> bool;
}

impl PathBufExt for PathBuf {
    fn ends_ok_with(&self, suffix: &str) -> bool {
        self.ends_with(suffix) || self.to_string_lossy().ends_with(suffix)
    }
}
