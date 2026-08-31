import base64
import os
import subprocess
from unittest.mock import patch, MagicMock
from app.services.ocr import (
    crop_and_ocr_block,
    _parse_gemini_grid_response,
    _run_gemini_cli_ocr,
    _run_gemini_command,
    _run_gemini_rest_ocr,
    _run_gemini_rest_text,
    _run_gemini_ocr_with_fallback,
    _gemini_prompt_image_path,
    batch_grid_crop_and_ocr_gemini,
)
from app.models.all_models import TextBlock

def test_run_gemini_cli_ocr_mock():
    with patch("shutil.which", return_value="agy"):
        with patch("subprocess.run") as mock_run:
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "```text\n테스트 OCR\n```"
            mock_run.return_value = mock_res
            
            text, success = _run_gemini_cli_ocr("dummy_path.png")
            assert success is True
            assert text == "테스트 OCR"

def test_crop_and_ocr_block_gemini_backend():
    block = TextBlock(id="b1", x=0, y=0, width=50, height=50)
    with patch("PIL.Image.open") as mock_open:
        mock_img = MagicMock()
        mock_img.size = (100, 100)
        mock_img.crop.return_value = mock_img
        mock_open.return_value.__enter__.return_value = mock_img
        
        with patch("app.services.ocr._run_gemini_cli_ocr", return_value=("성공", True)) as mock_ocr:
            text, success = crop_and_ocr_block("dummy_img.png", block, backend="gemini")
            assert success is True
            assert text == "성공"
            mock_ocr.assert_called_once()


def test_gemini_grid_response_maps_by_stable_box_id_not_response_order():
    raw = '[{"box_id":"BOX_002_deadbeef","text":"สอง"},{"box_id":"BOX_001_abcdef01","text":"หนึ่ง"}]'

    parsed = _parse_gemini_grid_response(
        raw,
        {"BOX_001_abcdef01", "BOX_002_deadbeef"},
    )

    assert parsed == {
        "BOX_001_abcdef01": "หนึ่ง",
        "BOX_002_deadbeef": "สอง",
    }


def test_gemini_grid_response_accepts_banner_prefix_rewritten_as_underscores():
    """Regression: Gemini returns the full banner instead of the stable suffix."""
    raw = (
        '[{"box_id":"HOUMI_BOX_BOX_001_4bdc3e8","text":"ข้อความหนึ่ง"},'
        '{"box_id":"HOUMI_BOX_BOX_002_f6c864ed","text":"ข้อความสอง"}]'
    )

    parsed = _parse_gemini_grid_response(
        raw,
        {"BOX_001_4bdc3e8", "BOX_002_f6c864ed"},
    )

    assert parsed == {
        "BOX_001_4bdc3e8": "ข้อความหนึ่ง",
        "BOX_002_f6c864ed": "ข้อความสอง",
    }


def test_gemini_cli_prompt_attaches_image_and_mentions_source_language():
    with patch("shutil.which", side_effect=lambda cmd: "agy" if cmd == "agy" else None):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ข้อความ", stderr="")

            _run_gemini_cli_ocr("C:/tmp/box 1.png", source_lang="zh")

            command = mock_run.call_args.args[0]
            assert "--dangerously-skip-permissions" in command
            assert "@" in command


def test_gemini_rest_ocr_sends_inline_image_without_leaking_key(tmp_path):
    image_path = tmp_path / "box.png"
    image_bytes = b"fake-png-bytes"
    image_path.write_bytes(image_bytes)

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "REST OCR"}]}}]
    }

    with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False):
        with patch("app.services.ocr.httpx.post", return_value=response) as mock_post:
            text, success = _run_gemini_rest_ocr(
                f"Read the attached image {_gemini_prompt_image_path(str(image_path))}",
                str(image_path),
                model="flash",
            )

    assert (text, success) == ("REST OCR", True)
    request = mock_post.call_args
    assert request.kwargs["headers"]["x-goog-api-key"] == "test-key"
    payload = request.kwargs["json"]
    parts = payload["contents"][0]["parts"]
    assert "@" not in parts[0]["text"]
    assert base64.b64decode(parts[1]["inlineData"]["data"]) == image_bytes
    assert parts[1]["inlineData"]["mimeType"] == "image/png"


def test_gemini_command_prefers_rest_for_image_prompt_when_key_exists():
    """Image prompts try Direct REST first when GOOGLE_API_KEY is configured."""
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False):
        with patch("app.services.ocr._run_gemini_rest_ocr", return_value=("REST", True)) as rest:
            with patch.object(subprocess, "run") as cli:
                result = _run_gemini_command("Read image", image_path="C:/tmp/box.png")

    assert result == ("REST", True)
    rest.assert_called_once()
    cli.assert_not_called()


def test_gemini_command_honors_persisted_settings_agy(tmp_path, monkeypatch):
    """When user selects 'agy' in Settings, REST is skipped completely."""
    from app.services import ai_provider_settings
    monkeypatch.setattr(ai_provider_settings, "SETTINGS_PATH", tmp_path / "settings" / "ai_provider.json")
    ai_provider_settings.update_ai_provider_preferences(provider="agy", google_api_key="valid-secret-key")

    with patch("app.services.ocr._run_gemini_rest_ocr") as rest:
        with patch("shutil.which", return_value="agy"):
            with patch.object(subprocess, "run", return_value=MagicMock(returncode=0, stdout="AGY Direct Result", stderr="")) as cli:
                result = _run_gemini_command("Read image", image_path="C:/tmp/box.png", provider="auto")

    assert result == ("AGY Direct Result", True)
    rest.assert_not_called()
    assert str(cli.call_args.args[0]).startswith("agy")


def test_gemini_ocr_uses_paddle_fallback_when_cloud_path_fails():
    with patch.dict(os.environ, {"HOUMI_GEMINI_FALLBACK": "paddleocr"}, clear=False):
        with patch("app.services.ocr._run_gemini_cli_ocr", return_value=("", False)):
            with patch("app.services.ocr._run_paddle_ocr_path", return_value=("Paddle", True)) as paddle:
                result = _run_gemini_ocr_with_fallback("C:/tmp/box.png")

    assert result == ("Paddle", True)
    paddle.assert_called_once_with("C:/tmp/box.png", source_lang="")


def test_gemini_batch_uses_paddle_when_no_cloud_or_cli(tmp_path):
    from PIL import Image
    page_img = tmp_path / "page.png"
    Image.new("RGB", (100, 100), color="white").save(page_img, "PNG")
    block = TextBlock(id="b1", x=0, y=0, width=20, height=20)
    with patch.dict(os.environ, {"GOOGLE_API_KEY": "", "HOUMI_GEMINI_FALLBACK": "paddleocr"}, clear=False):
        with patch("shutil.which", return_value=None):
            with patch("app.services.ocr.crop_and_ocr_block", return_value=("Paddle", True)) as paddle:
                result = batch_grid_crop_and_ocr_gemini(str(page_img), [block])

    assert result == [(block, "Paddle", True)]
    paddle.assert_called_once_with(
        str(page_img),
        block,
        backend="paddleocr",
        source_lang="",
    )


def test_crop_and_ocr_block_strict_no_silent_fallback_when_port_2322_offline(tmp_path):
    import requests
    from PIL import Image
    block = TextBlock(id="b1", x=0, y=0, width=50, height=50)
    dummy_img = tmp_path / "test.png"
    Image.new("RGB", (100, 100), color="white").save(dummy_img, "PNG")

    with patch("requests.post", side_effect=requests.RequestException("connection refused")):
        text, success = crop_and_ocr_block(str(dummy_img), block, backend="glm")
        assert success is False
        assert "Local GLM VLM Server (Port 2322) is not running" in text
