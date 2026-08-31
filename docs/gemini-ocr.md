# Gemini OCR configuration

## Runtime behavior

For image prompts, Houmi now sends the image as base64 `inline_data` directly
to Gemini's `generateContent` REST endpoint. This bypasses the current `agy`
image-media conversion problem. Text-only prompts continue using `agy --print`
or the installed `gemini` CLI.

The backend checks these environment variables in order:

1. `GOOGLE_API_KEY`
2. `GEMINI_API_KEY`
3. `HOUMI_GEMINI_API_KEY`

The key is read by the backend only. It is not sent to the frontend, stored in
the project, or embedded in the EXE. The default REST model is
`gemini-3.6-flash`; override it with `HOUMI_GEMINI_MODEL` when the account uses
another model. `HOUMI_GEMINI_API_VERSION` defaults to `v1beta`.

## Local setup

Create a key in [Google AI Studio](https://aistudio.google.com/apikey), then
set it only in the process that starts the backend/Local Engine:

```powershell
$env:GOOGLE_API_KEY = '<your-key>'
$env:HOUMI_GEMINI_MODEL = 'gemini-3.6-flash'
& 'backend\.venv\Scripts\python.exe' backend\desktop_local.py --host 127.0.0.1 --port 4317
```

Do not commit the key, put it in `frontend/localStorage`, or package it into a
customer installer. Images sent to Gemini leave the local machine; obtain the
required user approval before processing sensitive material.

## Fallback and confirmation

When Gemini REST/CLI fails, the interactive UI reports the failed block count
and waits for the user to choose `ลองใหม่`, `เปลี่ยนไปใช้ Local OCR`, or `ยกเลิก`.
The switch chooses an available local engine in this order: PaddleOCR, GLM-OCR,
then DeepSeek-OCR. It does not silently change OCR engines. The default backend
fallback is disabled for this reason.

Headless automation can explicitly opt into local PaddleOCR:

```powershell
$env:HOUMI_GEMINI_FALLBACK = 'paddleocr'
```

Disable automatic fallback with `HOUMI_GEMINI_FALLBACK=none` (the default). The fallback
needs the selected local engine in the active backend environment. The minimal
frozen desktop sidecar currently excludes the Paddle model stack, so it will offer
another available local engine when present; a Paddle-based offline customer build
must be produced with the model/runtime packaging work completed first.

The OCR engine status endpoint reports Gemini as available when either a key
or a Gemini-compatible CLI is present:

```powershell
Invoke-RestMethod http://127.0.0.1:4317/api/pipeline/ocr/engines
```

The REST request format follows Google's official
[multimodal GenerateContent documentation](https://ai.google.dev/gemini-api/docs/generate-content/image-understanding).
