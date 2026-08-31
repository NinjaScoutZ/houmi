from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.routes.projects import _matches_folder_workspace, delete_project, get_projects


class _Query:
    def __init__(self, first_value, all_value=None):
        self.first_value = first_value
        self.all_value = all_value if all_value is not None else [first_value]

    def filter(self, *_args):
        return self

    def first(self):
        return self.first_value

    def all(self):
        return self.all_value

    def order_by(self, *_args):
        return self


class _ProjectDeleteDb:
    def __init__(self, project, pages):
        self.project = project
        self.pages = pages
        self.deleted = None
        self.committed = False

    def query(self, model):
        # The route queries Project first, then Page. No database behavior is
        # needed beyond those two result shapes for this filesystem contract.
        return _Query(self.project if model.__name__ == "Project" else None, self.pages)

    def delete(self, value):
        self.deleted = value

    def commit(self):
        self.committed = True


class _ProjectListDb:
    def __init__(self, projects):
        self.projects = projects
        self.deleted = []

    def query(self, _model):
        return _Query(None, self.projects)

    def delete(self, project):
        self.deleted.append(project)

    def commit(self):
        pass


def test_folder_project_requires_matching_project_json_for_reuse(tmp_path: Path):
    source = tmp_path / "001.png"
    source.write_bytes(b"source")
    project = SimpleNamespace(
        id="project-1",
        settings={"local_folder": str(tmp_path.resolve())},
        pages=[SimpleNamespace(source_image_path=str(source))],
    )

    assert not (tmp_path / "project.json").exists()
    assert not _matches_folder_workspace(project, str(tmp_path.resolve()))

    (tmp_path / "project.json").write_text('{"id":"project-1"}', encoding="utf-8")
    assert _matches_folder_workspace(project, str(tmp_path.resolve()))


def test_folder_project_is_not_reused_when_manifest_belongs_to_another_project(tmp_path: Path):
    source = tmp_path / "001.png"
    source.write_bytes(b"source")
    (tmp_path / "project.json").write_text('{"id":"old-project"}', encoding="utf-8")
    project = SimpleNamespace(
        id="project-1",
        settings={"local_folder": str(tmp_path.resolve())},
        pages=[SimpleNamespace(source_image_path=str(source))],
    )

    assert not _matches_folder_workspace(project, str(tmp_path.resolve()))


def test_folder_project_is_not_reused_when_a_source_was_removed(tmp_path: Path):
    project = SimpleNamespace(
        id="project-1",
        settings={"local_folder": str(tmp_path.resolve())},
        pages=[SimpleNamespace(source_image_path=str(tmp_path / "missing.png"))],
    )

    (tmp_path / "project.json").write_text('{"id":"project-1"}', encoding="utf-8")
    assert not _matches_folder_workspace(project, str(tmp_path.resolve()))


def test_deleting_folder_project_preserves_original_images(tmp_path: Path):
    source = tmp_path / "001.png"
    source.write_bytes(b"original-image")
    (tmp_path / "project.json").write_text('{"id":"project-1"}', encoding="utf-8")
    for name in ("masks", "clean", "rendered", "previews", "training", ".houmi"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "generated.bin").write_bytes(b"generated")

    page = SimpleNamespace(source_image_path=str(source))
    project = SimpleNamespace(
        id="project-1",
        settings={"local_folder": str(tmp_path.resolve())},
        pages=[page],
    )
    db = _ProjectDeleteDb(project, [page])

    with patch("app.routes.projects.ensure_project_access"):
        delete_project(project.id, db=db, current_user=None)

    assert source.exists()
    assert not (tmp_path / "project.json").exists()
    for name in ("masks", "clean", "rendered", "previews", "training", ".houmi"):
        assert not (tmp_path / name).exists()


def test_listing_projects_purges_folder_state_removed_by_user(tmp_path: Path):
    source = tmp_path / "001.png"
    source.write_bytes(b"original-image")
    project = SimpleNamespace(
        id="project-1",
        name="chapter",
        settings={"local_folder": str(tmp_path.resolve())},
        pages=[SimpleNamespace(source_image_path=str(source))],
    )
    db = _ProjectListDb([project])

    assert get_projects(db=db, current_user=None) == []
    assert db.deleted == [project]
    assert source.exists()


def test_browse_folder_restores_text_blocks_from_manifest(tmp_path: Path):
    import json
    from PIL import Image
    from app.routes.projects import browse_folder_project
    from app.models.all_models import Project, Page, TextBlock
    from app.database import Base, engine, SessionLocal

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        img_path = tmp_path / "01.png"
        img = Image.new("RGB", (100, 100), color="white")
        img.save(img_path)

        manifest_data = {
            "id": "portable-proj-1",
            "name": "PortableProj",
            "source_lang": "ja",
            "target_lang": "th",
            "settings": {"auto_ocr": False},
            "pages": [
                {
                    "id": "p1",
                    "page_number": 1,
                    "name": "01.png",
                    "width": 100,
                    "height": 100,
                    "text_blocks": [
                        {
                            "id": "b1",
                            "block_index": 1,
                            "x": 10,
                            "y": 20,
                            "width": 50,
                            "height": 30,
                            "source_text": "こんにちは",
                            "translation": "สวัสดีครับ",
                            "font_family": "Tahoma",
                            "font_size": 18,
                            "balloon_type": "bubble"
                        }
                    ]
                }
            ]
        }
        (tmp_path / "project.json").write_text(json.dumps(manifest_data, ensure_ascii=False), encoding="utf-8")

        res = browse_folder_project(folder_path=str(tmp_path), settings=None, db=db, current_user=None)
        assert res["name"] == "PortableProj"

        proj_in_db = db.query(Project).filter(Project.id == res["id"]).first()
        assert proj_in_db is not None
        assert len(proj_in_db.pages) == 1
        assert len(proj_in_db.pages[0].text_blocks) == 1
        block = proj_in_db.pages[0].text_blocks[0]
        assert block.translation == "สวัสดีครับ"
        assert block.source_text == "こんにちは"
    finally:
        db.close()

    assert img_path.exists()
