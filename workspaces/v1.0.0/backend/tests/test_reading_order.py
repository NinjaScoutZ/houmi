import unittest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.all_models import Base, Project, Page, TextBlock
from app.services.reading_order_service import (
    compute_reading_order_sequence,
    compute_reading_flow_lines,
    get_page_reading_order,
    apply_page_reading_order,
)


class TestReadingOrder(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.project = Project(
            id=str(uuid.uuid4()),
            name="Manga Project",
            source_lang="ja",
            target_lang="th",
        )
        self.db.add(self.project)

        self.page = Page(
            id=str(uuid.uuid4()),
            project_id=self.project.id,
            page_number=1,
            name="page_01.png",
            width=1000,
            height=1500,
            source_image_path="dummy.png",
        )
        self.db.add(self.page)

        # Create 3 blocks simulating a panel with top-right (first), top-left (second), and bottom (third) in Japanese Manga
        self.b_top_right = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=0,
            x=600,
            y=100,
            width=200,
            height=100,
            source_text="First (Top Right)",
        )
        self.b_top_left = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=1,
            x=150,
            y=120,  # in same row tolerance
            width=200,
            height=100,
            source_text="Second (Top Left)",
        )
        self.b_bottom = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=2,
            x=400,
            y=800,  # lower row
            width=250,
            height=120,
            source_text="Third (Bottom)",
        )
        self.db.add_all([self.b_top_right, self.b_top_left, self.b_bottom])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_manga_rtl_reading_order(self):
        blocks = [self.b_bottom, self.b_top_left, self.b_top_right]
        ordered = compute_reading_order_sequence(blocks, mode="manga_rtl")
        
        # In Manga RTL: Top-Right (x=600, y=100) -> Top-Left (x=150, y=120) -> Bottom (y=800)
        self.assertEqual(ordered[0].id, self.b_top_right.id)
        self.assertEqual(ordered[1].id, self.b_top_left.id)
        self.assertEqual(ordered[2].id, self.b_bottom.id)

    def test_webtoon_ltr_reading_order(self):
        blocks = [self.b_bottom, self.b_top_left, self.b_top_right]
        ordered = compute_reading_order_sequence(blocks, mode="webtoon_ltr")
        
        # In Webtoon: strictly y-ascending (top-to-bottom)
        self.assertEqual(ordered[0].id, self.b_top_right.id)  # y=100
        self.assertEqual(ordered[1].id, self.b_top_left.id)   # y=120
        self.assertEqual(ordered[2].id, self.b_bottom.id)     # y=800

    def test_flow_lines_generation(self):
        ordered = [self.b_top_right, self.b_top_left, self.b_bottom]
        flow_lines = compute_reading_flow_lines(ordered)
        
        self.assertEqual(len(flow_lines), 2)
        # First line connects top-right to top-left
        self.assertEqual(flow_lines[0]["from_index"], 1)
        self.assertEqual(flow_lines[0]["to_index"], 2)
        self.assertEqual(flow_lines[0]["start"]["x"], 700.0)  # center of 600..800

    def test_apply_page_reading_order(self):
        new_order = [str(self.b_bottom.id), str(self.b_top_left.id), str(self.b_top_right.id)]
        res = apply_page_reading_order(str(self.page.id), new_order, self.db)
        self.assertEqual(res["status"], "success")

        # Verify new block_index persisted
        reloaded_b_bottom = self.db.query(TextBlock).filter(TextBlock.id == self.b_bottom.id).first()
        self.assertEqual(reloaded_b_bottom.block_index, 0)


if __name__ == "__main__":
    unittest.main()
