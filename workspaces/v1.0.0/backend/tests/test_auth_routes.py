import datetime
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.all_models import Project, RedeemCode, User
from app.routes.auth import (
    LoginRequest,
    RedeemRequest,
    RefreshRequest,
    RegisterRequest,
    WsTicketRequest,
    consume_ws_ticket,
    issue_ws_ticket,
    login,
    redeem,
    refresh,
    register,
)
from app.security.tokens import hash_opaque_token


class TestAuthRoutes(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_register_login_refresh_and_reuse_detection(self):
        registered = register(
            RegisterRequest(
                username="alice",
                email="alice@example.test",
                password="correct horse battery staple",
            ),
            self.db,
        )
        self.assertEqual(registered["status"], "active")

        first = login(
            LoginRequest(identifier="alice", password="correct horse battery staple"),
            self.db,
        )
        rotated = refresh(RefreshRequest(refresh_token=first["refresh_token"]), self.db)
        self.assertNotEqual(first["refresh_token"], rotated["refresh_token"])

        with self.assertRaises(Exception):
            refresh(RefreshRequest(refresh_token=first["refresh_token"]), self.db)

        user = self.db.query(User).filter(User.id == registered["id"]).one()
        sessions = self.db.query(user.sessions[0].__class__).filter_by(user_id=user.id).all()
        self.assertTrue(all(session.revoked_at is not None for session in sessions))

    def test_redeem_extends_existing_entitlement(self):
        registered = register(
            RegisterRequest(
                username="bob",
                email="bob@example.test",
                password="correct horse battery staple",
            ),
            self.db,
        )
        user = self.db.query(User).filter(User.id == registered["id"]).one()
        first = login(LoginRequest(identifier="bob", password="correct horse battery staple"), self.db)

        code = "HOU-30-DAYS"
        self.db.add(
            RedeemCode(
                code_hash=hash_opaque_token(code),
                code_prefix="HOU-30",
                duration_days=30,
            )
        )
        self.db.commit()

        first_result = redeem(RedeemRequest(code=code), user, self.db)
        second_code = "HOU-90-DAYS"
        self.db.add(
            RedeemCode(
                code_hash=hash_opaque_token(second_code),
                code_prefix="HOU-90",
                duration_days=90,
            )
        )
        self.db.commit()
        second_result = redeem(RedeemRequest(code=second_code), user, self.db)
        self.assertGreater(second_result["expires_at"], first_result["expires_at"])
        self.assertTrue(first["access_token"])

    def test_ws_ticket_is_single_use_and_project_scoped(self):
        registered = register(
            RegisterRequest(
                username="carol",
                email="carol@example.test",
                password="correct horse battery staple",
            ),
            self.db,
        )
        user = self.db.query(User).filter(User.id == registered["id"]).one()
        project = Project(name="owned", owner_id=user.id)
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)

        issued = issue_ws_ticket(WsTicketRequest(project_id=project.id), user, self.db)
        consumed_user_id = consume_ws_ticket(issued["ticket"], project.id, self.db)
        consumed_again = consume_ws_ticket(issued["ticket"], project.id, self.db)
        self.assertEqual(consumed_user_id, user.id)
        self.assertIsNone(consumed_again)


if __name__ == "__main__":
    unittest.main()
