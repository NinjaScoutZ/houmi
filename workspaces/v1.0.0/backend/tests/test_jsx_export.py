from unittest.mock import MagicMock
from app.models.all_models import Page, TextBlock, Project
from app.services.jsx_export import extract_page_blocks_data, generate_page_jsx_script, generate_project_jsx_script


def test_extract_page_blocks_data_returns_source_and_bg_paths(tmp_path):
    src_file = tmp_path / "page_001.png"
    src_file.write_text("fake image")
    inpaint_file = tmp_path / "page_001_inpainted.png"
    inpaint_file.write_text("fake clean image")

    page = Page(
        id="page_1",
        project_id="proj_1",
        page_number=1,
        source_image_path=str(src_file),
        inpainted_image_path=str(inpaint_file),
    )
    block = TextBlock(
        id="b1",
        page_id="page_1",
        source_text="Hello",
        translation="สวัสดี",
        x=50,
        y=100,
        width=200,
        height=80,
    )
    page.text_blocks = [block]

    bg_path, src_path, psd_target, blocks = extract_page_blocks_data(page)

    assert "page_001_inpainted.png" in bg_path
    assert "page_001.png" in src_path
    assert len(blocks) == 1
    assert blocks[0]["text"] == "สวัสดี"


def test_generate_page_jsx_script_places_original_image_at_bottom(tmp_path):
    src_file = tmp_path / "page_001.png"
    src_file.write_text("fake image")
    inpaint_file = tmp_path / "page_001_inpainted.png"
    inpaint_file.write_text("fake clean image")

    page = Page(
        id="page_1",
        project_id="proj_1",
        page_number=1,
        source_image_path=str(src_file),
        inpainted_image_path=str(inpaint_file),
    )
    block = TextBlock(
        id="b1",
        page_id="page_1",
        translation="ทดสอบ",
        x=50,
        y=100,
        width=200,
        height=80,
    )
    page.text_blocks = [block]

    db = MagicMock()
    db.query().filter().first.return_value = page

    script = generate_page_jsx_script("page_1", db)

    # Verifications for layer hierarchy
    assert 'var bgLayer = doc.activeLayer;' in script
    assert 'bgLayer.name = "Inpainted Background";' in script
    assert 'ElementPlacement.PLACEATEND' in script
    assert 'doc.layers[doc.layers.length - 1].name = "Original Image";' in script


def test_generate_project_jsx_script_places_original_image_at_bottom(tmp_path):
    src_file = tmp_path / "page_001.png"
    src_file.write_text("fake image")
    inpaint_file = tmp_path / "page_001_inpainted.png"
    inpaint_file.write_text("fake clean image")

    proj = Project(id="proj_1", name="Test Manga")
    page = Page(
        id="page_1",
        project_id="proj_1",
        page_number=1,
        source_image_path=str(src_file),
        inpainted_image_path=str(inpaint_file),
    )
    page.project = proj
    block = TextBlock(
        id="b1",
        page_id="page_1",
        translation="ข้อความ",
        x=30,
        y=50,
        width=150,
        height=60,
    )
    page.text_blocks = [block]
    proj.pages = [page]

    db = MagicMock()
    db.query().filter().first.return_value = proj

    script = generate_project_jsx_script("proj_1", db)

    assert 'src_path' in script
    assert 'ElementPlacement.PLACEATEND' in script
    assert 'doc.layers[doc.layers.length - 1].name = "Original Image";' in script
