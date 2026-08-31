import asyncio
import json
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.database import Base
from app.models.all_models import Project, User
from app.security.dependencies import require_resource_access


class TestResourceDependency(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.owner = User(username="body-owner", email="body-owner@example.test", password_hash="hash")
        self.foreign = User(username="body-foreign", email="body-foreign@example.test", password_hash="hash")
        self.db.add_all([self.owner, self.foreign])
        self.db.flush()
        self.project = Project(name="body-foreign-project", owner_id=self.foreign.id)
        self.db.add(self.project)
        self.db.commit()
        self.db.refresh(self.project)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_json_project_id_is_checked_before_route_handler(self):
        payload = json.dumps({"project_id": self.project.id}).encode()

        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path_params": {},
                "query_string": b"",
                "headers": [(b"content-type", b"application/json")],
            },
            receive,
        )
        with self.assertRaises(HTTPException) as error:
            asyncio.run(require_resource_access(request, user=self.owner, db=self.db))
        self.assertEqual(error.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
