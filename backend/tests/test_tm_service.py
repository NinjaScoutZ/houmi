import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.all_models import Base, TranslationMemory
from app.services.tm_service import (
    search_tm,
    record_tm_entry,
    import_tm_entries,
    export_tm_entries,
)


class TestTMService(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()

    def test_record_and_search_tm(self):
        entry = record_tm_entry(
            source_text="おはようございます",
            translation="อรุณสวัสดิ์ครับ",
            source_lang="ja",
            target_lang="th",
            db=self.db,
        )
        self.assertEqual(entry.frequency, 1)

        # Increment frequency on second record
        entry2 = record_tm_entry(
            source_text="おはようございます",
            translation="อรุณสวัสดิ์ครับ",
            source_lang="ja",
            target_lang="th",
            db=self.db,
        )
        self.assertEqual(entry2.frequency, 2)

        # Search exact
        results = search_tm("おはようございます", self.db, source_lang="ja", target_lang="th")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["translation"], "อรุณสวัสดิ์ครับ")
        self.assertEqual(results[0]["frequency"], 2)

    def test_import_and_export_tm(self):
        entries = [
            {"source_text": "こんにちは", "translation": "สวัสดีตอนกลางวัน", "source_language": "ja", "target_language": "th"},
            {"source_text": "こんばんは", "translation": "สวัสดีตอนเย็น", "source_language": "ja", "target_language": "th"},
        ]
        res = import_tm_entries(entries, self.db)
        self.assertEqual(res["imported_count"], 2)

        exported = export_tm_entries(self.db, source_lang="ja", target_lang="th")
        self.assertEqual(len(exported), 2)
        sources = [e["source_text"] for e in exported]
        self.assertIn("こんにちは", sources)
        self.assertIn("こんばんは", sources)


if __name__ == "__main__":
    unittest.main()
