// Sanitize stale 4317 keys from localStorage
try {
  if (typeof localStorage !== "undefined") {
    const staleKeys = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && (localStorage.getItem(k) || "").includes("4317")) {
        staleKeys.push(k);
      }
    }
    staleKeys.forEach(k => {
      console.log("[Sanitizer] Removing stale 4317 key from localStorage:", k);
      localStorage.removeItem(k);
    });
    localStorage.removeItem("houmi_central_server_url");
  }
} catch (e) {
  console.warn("Storage sanitizer error:", e);
}

window.__HOUMI_RUNTIME_CONFIG__ = {
  localApiBaseUrl: "http://127.0.0.1:4000",
  apiBaseUrl: "http://127.0.0.1:4000",
  wsBaseUrl: "ws://127.0.0.1:4000",
  port: 4000,
  mode: "local"
};
window.__HOUMI_API_URL__ = "http://127.0.0.1:4000";
window.__HOUMI_WS_URL__ = "ws://127.0.0.1:4000";
window.__HOUMI_BACKEND_PORT__ = 4000;
window.__HOUMI_ENVIRONMENT__ = "desktop-tauri";
console.log("[Runtime Config] Active API Host locked to: http://127.0.0.1:4000");
