"""Offline tests for the verification loop (T3.20-T3.25, T3.34):
convergence stop, cap stop, targeted-requery counting, diff-to-requery
mapping, and the confidence guard. No network -- java/dot/plantuml.jar
ARE required, since the loop genuinely renders each round (that's the
point: it diffs against a re-extraction of a real render, not a mock).
Skipped cleanly if the toolchain isn't present, matching T1.8's pattern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from umlregen.ir.models import Diagram
from umlregen.perception.client import VisionResponse
from umlregen.verify.loop import verify

from _toolchain import requires_render_toolchain

pytestmark = requires_render_toolchain


class _KeyedScriptedClient:
    """Dispatches by matching distinctive text unique to each prompt
    template, rather than requiring callers to predict verify()'s
    data-dependent call order. `queue(key, response)` enqueues one
    response for the next call whose prompt contains `key`; `records`
    the (key, prompt) of every call actually made.
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[VisionResponse]] = {}
        self.records: list[tuple[str, str]] = []

    def queue(self, key: str, response: VisionResponse) -> None:
        self._queues.setdefault(key, []).append(response)

    def complete(
        self, image: bytes, prompt: str, schema: dict[str, Any] | None = None
    ) -> VisionResponse:
        for key, pending in self._queues.items():
            if key in prompt and pending:
                self.records.append((key, prompt))
                return pending.pop(0)
        raise AssertionError(
            f"no queued response matches this prompt; queued keys: {list(self._queues)}\n"
            f"prompt was: {prompt[:200]}..."
        )


_STAGE_A_KEY = "Identify every class, interface"
_STAGE_B_KEY = "For every relationship (line or arrow)"
_REQUERY_MEMBERS_KEY = "You are re-examining one specific class"
_REQUERY_REL_KEY = "You are re-examining one specific candidate relationship"


def _diagram(
    classes: list[dict[str, Any]], relationships: list[dict[str, Any]] | None = None
) -> Diagram:
    return Diagram.model_validate({"classes": classes, "relationships": relationships or []})


def _class_response(names: list[str], members: dict[str, list[dict]] | None = None) -> dict:
    members = members or {}
    return {
        "classes": [
            {
                "name": name,
                "kind": "class",
                "attributes": members.get(name, {}).get("attributes", []),
                "methods": members.get(name, {}).get("methods", []),
            }
            for name in names
        ],
        "relationships": [],
    }


def _rel_response(rels: list[dict]) -> dict:
    return {"relationships": rels}


_TWO_CLASS_DIAGRAM = _diagram(
    [
        {"id": "A", "name": "A", "kind": "class", "attributes": [], "methods": []},
        {"id": "B", "name": "B", "kind": "class", "attributes": [], "methods": []},
    ],
    [
        {
            "source": "A",
            "target": "B",
            "kind": "association",
            # Below REQUERY_CONFIDENCE (0.3) deliberately -- a normal
            # stage-B placeholder (0.5) is now high enough that the
            # confidence guard skips re-querying it outright (see
            # test_confidence_guard_skips_relationships_with_real_confidence),
            # and several tests in this file need a relationship
            # disagreement to actually trigger a re-query.
            "confidence": 0.2,
            "evidence": "solid line",
        }
    ],
)


def test_convergence_stops_after_one_round(tmp_path: Path) -> None:
    client = _KeyedScriptedClient()
    # Round 1's re-extraction matches the original diagram exactly -> no diff.
    client.queue(_STAGE_A_KEY, VisionResponse(raw_text="ok", parsed_json=_class_response(["A", "B"]), model_id="test"))
    client.queue(
        _STAGE_B_KEY,
        VisionResponse(
            raw_text="ok",
            parsed_json=_rel_response(
                [{"source": "A", "target": "B", "kind": "association", "evidence": "solid line"}]
            ),
            model_id="test",
        ),
    )

    result = verify(_TWO_CLASS_DIAGRAM, client, debug_dir=tmp_path)

    assert result.stats.converged is True
    assert result.stats.rounds_run == 1
    assert result.stats.requery_calls == 0
    assert result.stats.render_reextract_calls == 2  # one stage-A + one stage-B call


def test_non_convergence_stops_after_cap(tmp_path: Path) -> None:
    client = _KeyedScriptedClient()
    # Every round's re-extraction disagrees (missing class B) and every
    # re-query confirms the original was right, so nothing converges.
    for _ in range(2):
        client.queue(_STAGE_A_KEY, VisionResponse(raw_text="ok", parsed_json=_class_response(["A"]), model_id="test"))
        client.queue(_STAGE_B_KEY, VisionResponse(raw_text="ok", parsed_json=_rel_response([]), model_id="test"))
    # T3.21's targeted re-query for the disagreement -- no bounding on
    # how many times this might be asked across 2 rounds, so queue a few.
    for _ in range(4):
        client.queue(
            _REQUERY_MEMBERS_KEY,
            VisionResponse(raw_text="ok", parsed_json={"attributes": [], "methods": []}, model_id="test"),
        )
        client.queue(
            _REQUERY_REL_KEY,
            VisionResponse(
                raw_text="ok",
                parsed_json={"relationship_exists": True, "kind": "association", "evidence": "solid line"},
                model_id="test",
            ),
        )

    result = verify(_TWO_CLASS_DIAGRAM, client, max_rounds=2, debug_dir=tmp_path)

    assert result.stats.converged is False
    assert result.stats.rounds_run == 2
    assert result.stats.render_reextract_calls == 4  # 2 rounds x (stage A + stage B)


def test_targeted_requery_counting_and_diff_mapping(tmp_path: Path) -> None:
    client = _KeyedScriptedClient()
    # Round 1: re-extraction disagrees on B's members (extra method) and
    # on the A->B relationship's kind -- exactly two disagreements.
    client.queue(
        _STAGE_A_KEY,
        VisionResponse(
            raw_text="ok",
            parsed_json=_class_response(
                ["A", "B"], {"B": {"methods": [{"name": "extra", "visibility": "+"}]}}
            ),
            model_id="test",
        ),
    )
    client.queue(
        _STAGE_B_KEY,
        VisionResponse(
            raw_text="ok",
            parsed_json=_rel_response(
                [{"source": "A", "target": "B", "kind": "dependency", "evidence": "dashed arrow"}]
            ),
            model_id="test",
        ),
    )
    # The two targeted re-queries confirm the *original* was right, so
    # round 2 converges (no more disagreements) after they're applied.
    client.queue(
        _REQUERY_MEMBERS_KEY,
        VisionResponse(raw_text="ok", parsed_json={"attributes": [], "methods": []}, model_id="test"),
    )
    client.queue(
        _REQUERY_REL_KEY,
        VisionResponse(
            raw_text="ok",
            parsed_json={"relationship_exists": True, "kind": "association", "evidence": "solid line, no arrowhead"},
            model_id="test",
        ),
    )
    client.queue(_STAGE_A_KEY, VisionResponse(raw_text="ok", parsed_json=_class_response(["A", "B"]), model_id="test"))
    client.queue(
        _STAGE_B_KEY,
        VisionResponse(
            raw_text="ok",
            parsed_json=_rel_response(
                [{"source": "A", "target": "B", "kind": "association", "evidence": "solid line"}]
            ),
            model_id="test",
        ),
    )

    result = verify(_TWO_CLASS_DIAGRAM, client, debug_dir=tmp_path)

    assert result.stats.requery_calls == 2  # exactly one per disagreement, not a full re-extraction
    requery_keys = [key for key, _ in client.records if key in (_REQUERY_MEMBERS_KEY, _REQUERY_REL_KEY)]
    assert requery_keys == [_REQUERY_MEMBERS_KEY, _REQUERY_REL_KEY]
    # The member re-query's prompt names the disagreeing class.
    member_prompt = next(p for k, p in client.records if k == _REQUERY_MEMBERS_KEY)
    assert '"B"' in member_prompt
    # The relationship re-query's prompt names both endpoints.
    rel_prompt = next(p for k, p in client.records if k == _REQUERY_REL_KEY)
    assert '"A"' in rel_prompt and '"B"' in rel_prompt
    assert result.stats.converged is True
    assert result.stats.rounds_run == 2


def test_confidence_guard_skips_relationships_with_real_confidence(tmp_path: Path) -> None:
    # T3.24 found live that a fixed re-query confidence *above* the
    # stage-B placeholder let re-queries silently overwrite correct
    # answers (observer_pattern: 3 correct relationships replaced by 3
    # wrong ones, 0 rejections logged, because 0.6 >= 0.5 always held).
    # Fixed by lowering REQUERY_CONFIDENCE below the placeholder and
    # skipping the call entirely for anything that already clears it --
    # which also means, by construction, that a re-query is now only
    # ever attempted when it *could* win, so the post-call rejection
    # branch in _apply_targeted_requeries is presently unreachable via
    # any live call path (both constants being equal to the pre-check
    # threshold makes "asked, but lost" impossible) -- it stays as
    # forward-looking code for when real confidence scoring exists, not
    # something this test can exercise honestly through the public API.
    real_confidence_diagram = _diagram(
        [
            {"id": "A", "name": "A", "kind": "class", "attributes": [], "methods": []},
            {"id": "B", "name": "B", "kind": "class", "attributes": [], "methods": []},
        ],
        [
            {
                "source": "A",
                "target": "B",
                "kind": "composition",
                "confidence": 0.5,  # extract.py's ordinary stage-B placeholder, not degraded
                "evidence": "filled diamond at A",
            }
        ],
    )
    client = _KeyedScriptedClient()
    for _ in range(2):
        client.queue(_STAGE_A_KEY, VisionResponse(raw_text="ok", parsed_json=_class_response(["A", "B"]), model_id="test"))
        client.queue(
            _STAGE_B_KEY,
            VisionResponse(
                raw_text="ok",
                # Re-extraction disagrees on kind every round.
                parsed_json=_rel_response(
                    [{"source": "A", "target": "B", "kind": "aggregation", "evidence": "hollow diamond at A"}]
                ),
                model_id="test",
            ),
        )
    # Deliberately no _REQUERY_REL_KEY response queued -- if the guard
    # failed to skip, the scripted client would raise on the unmatched
    # call, failing the test loudly rather than silently passing.

    result = verify(real_confidence_diagram, client, debug_dir=tmp_path)

    assert result.stats.requery_calls == 0
    assert result.stats.rejected_patches == []
    patched_rel = next(
        r for r in result.diagram.relationships if r.source == "A" and r.target == "B"
    )
    assert patched_rel.kind.value == "composition"
    assert patched_rel.confidence == 0.5


def test_confidence_guard_accepts_confirmed_addition(tmp_path: Path) -> None:
    no_relationship_diagram = _diagram(
        [
            {"id": "A", "name": "A", "kind": "class", "attributes": [], "methods": []},
            {"id": "B", "name": "B", "kind": "class", "attributes": [], "methods": []},
        ],
        [],
    )
    client = _KeyedScriptedClient()
    client.queue(_STAGE_A_KEY, VisionResponse(raw_text="ok", parsed_json=_class_response(["A", "B"]), model_id="test"))
    client.queue(
        _STAGE_B_KEY,
        VisionResponse(
            raw_text="ok",
            # Re-extraction finds a relationship the original diagram missed.
            parsed_json=_rel_response(
                [{"source": "A", "target": "B", "kind": "dependency", "evidence": "dashed arrow"}]
            ),
            model_id="test",
        ),
    )
    client.queue(
        _REQUERY_REL_KEY,
        VisionResponse(
            raw_text="ok",
            parsed_json={"relationship_exists": True, "kind": "dependency", "evidence": "dashed open arrowhead"},
            model_id="test",
        ),
    )
    client.queue(_STAGE_A_KEY, VisionResponse(raw_text="ok", parsed_json=_class_response(["A", "B"]), model_id="test"))
    client.queue(
        _STAGE_B_KEY,
        VisionResponse(
            raw_text="ok",
            parsed_json=_rel_response(
                [{"source": "A", "target": "B", "kind": "dependency", "evidence": "dashed arrow"}]
            ),
            model_id="test",
        ),
    )

    result = verify(no_relationship_diagram, client, debug_dir=tmp_path)

    assert result.stats.rejected_patches == []
    assert len(result.diagram.relationships) == 1
    assert result.diagram.relationships[0].kind.value == "dependency"
