from pathlib import Path
from types import SimpleNamespace

from app.services.project_paths import (
    inpainted_asset_path,
    mask_asset_path,
    rendered_asset_path,
)


def test_generated_assets_use_page_number_not_source_filename(tmp_path: Path):
    project = SimpleNamespace(id="project-1", settings={"local_folder": str(tmp_path)})
    page = SimpleNamespace(
        project=project,
        page_number=7,
        name="source-cover-name.jpg",
        source_image_path=str(tmp_path / "source-cover-name.jpg"),
    )

    assert rendered_asset_path(page) == tmp_path / "rendered" / "07.png"
    assert inpainted_asset_path(page) == tmp_path / "clean" / "07_inpaint.png"
    assert mask_asset_path(page, "effective_mask.png") == tmp_path / "masks" / "07_mask.png"
    assert not (tmp_path / "rendered" / "07").exists()
