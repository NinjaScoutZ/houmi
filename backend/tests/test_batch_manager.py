import pytest
from app.services.batch_manager import (
    CancellationToken,
    OperationCancelledException,
    BatchPipelineManager,
    batch_manager
)

def test_cancellation_token_behavior():
    token = CancellationToken()
    assert token.is_cancelled is False
    assert token() is False

    cb_called = []
    token.register_callback(lambda: cb_called.append(True))

    token.cancel("User test cancel")
    assert token.is_cancelled is True
    assert token() is True
    assert token.cancel_reason == "User test cancel"
    assert len(cb_called) == 1

    with pytest.raises(OperationCancelledException):
        token.throw_if_cancelled()

def test_batch_manager_duplicate_rejection():
    mgr = BatchPipelineManager()
    res = mgr.start_batch_job("PROJ_TEST_123")
    assert res["status"] == "success"

    # Second start on same project should raise RuntimeError
    with pytest.raises(RuntimeError):
        mgr.start_batch_job("PROJ_TEST_123")

    # Cancel should succeed
    cancel_res = mgr.cancel_batch_job("PROJ_TEST_123")
    assert cancel_res["status"] == "success"
