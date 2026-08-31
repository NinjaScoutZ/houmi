import pytest
from app.services.patch_manager import list_all_releases, set_active_release, build_and_archive_release

def test_list_and_switch_releases():
    releases = list_all_releases()
    assert len(releases) >= 1
    
    # Active release should exist
    active = [r for r in releases if r["is_active"]]
    assert len(active) == 1
    
    # Switch to 1.0.1
    res = set_active_release("1.0.1")
    assert res["ok"] is True
    assert res["active_version"] == "1.0.1"
    
    # Switch back to 1.0.4
    res2 = set_active_release("1.0.4")
    assert res2["ok"] is True
    assert res2["active_version"] == "1.0.4"
