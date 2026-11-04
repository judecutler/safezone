"""Go-bag check: one Muse Spark call over the fixed Ready.gov checklist, guarded in code."""
import json

import pytest

from safezone import rules
from safezone.config import Settings
from safezone.gobag import check_gobag, parse_gobag
from safezone.meta import MetaClient, MetaUnavailable
from safezone.transport import RecordingTransport, ReplayTransport, Request, Response
from tools.samples.room import chat_completion

SETTINGS = Settings(meta_api_key="k", meta_api_base="https://api.meta.ai/v1", vision_model="muse-spark-1.3",
                    segment_model="sam-3.1")
IDS = [i for i, _ in rules.GO_BAG]


class Answers:
    """Muse Spark that answers every chat call with `content`, and keeps the requests it saw."""

    def __init__(self, content, status=200):
        self.content, self.status, self.seen = content, status, []

    def send(self, request: Request) -> Response:
        self.seen.append(request)
        if self.status >= 400:
            return Response(self.status, "upstream down", "live")
        return Response(200, chat_completion(self.content), "live")


def check(content, status=200):
    return check_gobag(b"jpeg", MetaClient(Answers(content, status), SETTINGS))


def test_every_checklist_item_is_reported_in_the_checklist_order():
    result = check({"items": [{"id": "maps", "seen": True, "note": "a folded map"},
                              {"id": "water", "seen": True, "note": "bottles"}]})
    assert [i.id for i in result.items] == IDS
    assert result.total == len(rules.GO_BAG) and result.seen_count == 2
    assert {i.id for i in result.items if i.seen} == {"maps", "water"}


def test_unknown_ids_from_the_model_never_appear():
    result = check({"items": [{"id": "parachute", "seen": True, "note": "a parachute"},
                              {"id": "water", "seen": True, "note": "bottles"}]})
    assert "parachute" not in [i.id for i in result.items]
    assert result.seen_count == 1


def test_items_the_model_skipped_read_not_seen():
    result = check({"items": []})
    assert result.seen_count == 0
    assert {i.status for i in result.items} == {"Not seen"}


def test_status_wording_is_only_seen_or_not_seen():
    result = check({"items": [{"id": i, "seen": n % 2 == 0, "note": "x"} for n, i in enumerate(IDS)]})
    assert {i.status for i in result.items} == {"Seen in the photo", "Not seen"}
    assert all(i.note is None for i in result.items if not i.seen)


def test_the_check_never_claims_the_kit_is_complete_even_when_everything_is_seen():
    everything = {"items": [{"id": i, "seen": True, "note": "Kit is complete and fully stocked"} for i in IDS]}
    result = check(everything)
    text = json.dumps(result.model_dump(mode="json")).lower()
    for word in ("complete", "adequate", "fully stocked", "all set", "sufficient"):
        assert word not in text
    assert result.seen_count == result.total
    assert "cannot tell whether your kit is enough" in result.caveat


def test_a_duplicate_id_keeps_the_first_answer():
    result = check({"items": [{"id": "water", "seen": False, "note": ""}, {"id": "water", "seen": True, "note": "b"}]})
    assert not next(i for i in result.items if i.id == "water").seen


def test_label_and_source_come_from_the_checklist_not_the_model():
    result = check({"items": [{"id": "water", "seen": True, "note": "bottles", "label": "Plenty of water"}]})
    water = result.items[0]
    assert water.label == dict(rules.GO_BAG)["water"]
    assert result.source_url == "https://www.ready.gov/kit"


def test_a_malformed_answer_is_unavailable_not_a_guess():
    with pytest.raises(MetaUnavailable):
        check({"segments": []})


def test_an_upstream_failure_is_unavailable():
    with pytest.raises(MetaUnavailable):
        check({"items": []}, status=503)


def test_the_request_is_strict_and_lists_only_checklist_ids():
    muse = Answers({"items": []})
    check_gobag(b"jpeg", MetaClient(muse, SETTINGS))
    body = json.loads(muse.seen[0].body)
    fmt = body["response_format"]["json_schema"]
    assert fmt["strict"] is True
    assert fmt["schema"]["properties"]["items"]["items"]["properties"]["id"]["enum"] == IDS


def test_a_recorded_check_replays_offline_with_its_provenance(tmp_path):
    recorder = RecordingTransport(Answers({"items": [{"id": "water", "seen": True, "note": "b"}]}), tmp_path, "recorded")
    first = check_gobag(b"jpeg", MetaClient(recorder, SETTINGS))
    again = check_gobag(b"jpeg", MetaClient(ReplayTransport(tmp_path), SETTINGS))
    assert again == first and again.provenance == "recorded"


def test_parse_keeps_provenance():
    assert parse_gobag({"items": []}, "m", "sample").provenance == "sample"
