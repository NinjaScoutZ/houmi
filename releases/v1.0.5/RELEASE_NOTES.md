# Houmi Studio v1.0.5 Release Notes

**Release Date:** 2026-08-31  
**Build Artifact:** `houmi-v1.0.5-p1.zip`  
**SHA-256 Checksum:** `348e85d698e8c7a66b5c513dbe82d2882e667c005a72903df1ede62e3b213d23`  
**Compatibility:** Compatible with Houmi Desktop v1.0.0+

---

### 🌟 Highlights in v1.0.5

1. **4-Domain Clean Architecture & Complete Workspace Isolation:**
   - 100% self-contained workspace runtime.
   - Zero root path dependencies.
   - Eliminates unexpected UI overwriting or timestamp-based fallback glitches.

2. **Multi-Key Priority & Auto-Failover Pool:**
   - Manage multiple AI API keys with priority ordering.
   - Automatic immediate failover on Rate Limit (429) errors.

3. **Gemini Quota Exceeded Protection:**
   - Prevents endless retry loops when Google Gemini quotas are exhausted.

4. **Consolidated ExtendScript (.JSX) & Photoshop Integration:**
   - Enhanced export support for both Paragraph and Point Text layers in Photoshop.

5. **Single-Screen Combined Export Scope:**
   - Seamlessly choose between Current Page or Entire Project within a unified dialog.

---

### 📦 Installation & Verification

Extract `houmi-v1.0.5-p1.zip` into your Houmi application directory, or run `Launch-v1.0.5.bat` within `workspaces/v1.0.5/`.
