from adapters.inbound.matrix_results import capability_scores, handoff_scores


def test_capability_scores_accept_mapping_records_only() -> None:
    assert capability_scores({"capability_scores": "invalid"}) == []
    assert capability_scores({"capability_scores": [{"score": 0.8}, "invalid"]}) == [
        {"score": 0.8}
    ]


def test_handoff_scores_accept_mapping_records_only() -> None:
    assert handoff_scores({"handoff_scores": "invalid"}) == []
    assert handoff_scores({"handoff_scores": [{"agent": "Reporter"}, "invalid"]}) == [
        {"agent": "Reporter"}
    ]
