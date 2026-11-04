from safezone.transport import Request, Response
from tools.record_fixtures import FailureLog


class Fixed:
    def __init__(self, status: int):
        self.status = status

    def send(self, request: Request) -> Response:
        return Response(self.status, "boom" if self.status >= 400 else "{}", "live")


def _request() -> Request:
    return Request("POST", "https://api.meta.ai/v1/chat/completions", (), b"{}", (), 180)


def test_every_call_prints_a_start_and_an_end_line():
    lines: list[str] = []
    FailureLog(Fixed(200), out=lines.append).send(_request())
    assert "api.meta.ai" in lines[0] and "180s" in lines[0]
    assert lines[1].strip().startswith("ok 200")


def test_failed_call_is_printed_and_kept_with_its_body():
    lines: list[str] = []
    log = FailureLog(Fixed(500), out=lines.append)
    log.send(_request())
    assert lines[1].strip().startswith("ERR 500")
    assert len(log.failures) == 1 and "boom" in log.failures[0]


def test_a_rerun_keeps_fixtures_it_did_not_record(tmp_path):
    from tools.record_fixtures import merge_files
    target, staging = tmp_path / "demo", tmp_path / "staging"
    target.mkdir(); staging.mkdir()
    (target / "japan.json").write_text("{}")
    (target / "same.json").write_text('{"old": 1}')
    (staging / "same.json").write_text('{"new": 1}')
    merge_files(target, staging)
    assert (target / "japan.json").exists()
    assert (target / "same.json").read_text() == '{"new": 1}'
