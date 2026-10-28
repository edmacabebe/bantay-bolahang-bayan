from lotto_signal.cli import report_exit_code


def test_handled_operational_states_allow_cloud_state_commit() -> None:
    assert report_exit_code("ok") == 0
    assert report_exit_code("stale_source") == 0
    assert report_exit_code("source_error") == 0
    assert report_exit_code("pending_source") == 0
    assert report_exit_code("unknown_failure") == 1
