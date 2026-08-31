import pytest
from app.routes.pipeline import run_style_judge, run_batch_pipeline_task, batch_jobs
from app.models.all_models import Project, Page, TextBlock
from app.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch


def test_style_judge_pipeline_function():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    proj = Project(name="Test Proj")
    db.add(proj)
    db.commit()

    page = Page(project_id=proj.id, page_number=1, source_image_path="test.png", width=1000, height=1400)
    db.add(page)
    db.commit()

    block1 = TextBlock(
        page_id=page.id,
        block_index=0,
        x=100, y=100, width=200, height=100,
        translation="สวัสดีครับ!!",
        balloon_type="bubble"
    )
    block2 = TextBlock(
        page_id=page.id,
        block_index=1,
        x=100, y=300, width=500, height=80,
        translation="บรรยายฉากในเมืองยามค่ำคืน",
        balloon_type="narration"
    )
    db.add(block1)
    db.add(block2)
    db.commit()

    res = run_style_judge(page.id, db=db)
    assert res["status"] == "success"
    assert res["evaluated_blocks"] == 2
    assert res["applied_blocks"] >= 1
    db.close()


def test_batch_font_judge_task():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    proj = Project(name="Batch Proj")
    db.add(proj)
    db.commit()
    proj_id = proj.id

    page = Page(project_id=proj_id, page_number=1, source_image_path="test.png", width=1000, height=1400)
    db.add(page)
    db.commit()

    block1 = TextBlock(
        page_id=page.id,
        block_index=0,
        x=100, y=100, width=200, height=100,
        translation="โกรธแล้วนะ!!",
        balloon_type="bubble"
    )
    db.add(block1)
    db.commit()

    def mock_get_db():
        yield db

    with patch("app.routes.pipeline.get_db", side_effect=mock_get_db):
        run_batch_pipeline_task(proj_id, steps_str="font_judge")

    assert batch_jobs.get(proj_id, {}).get("status") == "success"
    db.close()
