import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.all_models import Project, User
from app.routes.projects import get_project, get_projects


class TestOwnershipAccess(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user_a = User(username="owner-a", email="a@example.test", password_hash="hash")
        self.user_b = User(username="owner-b", email="b@example.test", password_hash="hash")
        self.db.add_all([self.user_a, self.user_b])
        self.db.flush()
        self.project_a = Project(name="A", owner_id=self.user_a.id)
        self.project_b = Project(name="B", owner_id=self.user_b.id)
        self.db.add_all([self.project_a, self.project_b])
        self.db.commit()
        self.db.refresh(self.project_a)
        self.db.refresh(self.project_b)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_user_can_read_only_owned_projects(self):
        visible = get_projects(self.db, self.user_a)
        self.assertEqual([project.id for project in visible], [self.project_a.id])
        self.assertEqual(get_project(self.project_a.id, self.db, self.user_a).id, self.project_a.id)

    def test_foreign_project_is_hidden(self):
        with self.assertRaises(HTTPException) as error:
            get_project(self.project_b.id, self.db, self.user_a)
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
