import zipfile
import pytest
from pathlib import Path
from app.patches.manifest import calculate_file_sha256
from app.patches.patch_engine import AtomicPatchExtractor
from app.patches.rollback import get_rollback_history, execute_rollback, create_rollback_snapshot

def test_sha256_checksum(tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("Hello Houmi Production!", encoding="utf-8")
    h = calculate_file_sha256(test_file)
    assert isinstance(h, str)
    assert len(h) == 64

def test_atomic_patch_application_and_rollback(tmp_path):
    # 1. Create a dummy patch zip
    zip_path = tmp_path / "test_patch.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("test_file.txt", "v1.0.9 content")
        zf.writestr("patch_manifest.json", '{"version": "1.0.9", "notes": "Test"}')

    # Calculate hash
    h = calculate_file_sha256(zip_path)

    # 2. Apply patch
    res = AtomicPatchExtractor.apply_patch_archive(zip_path, expected_sha256=h, create_backup=True)
    assert res["ok"] is True
    assert res["version"] == "1.0.9"
    assert res["extracted_files"] == 2

    # 3. Check rollback history
    history = get_rollback_history()
    assert isinstance(history, list)
