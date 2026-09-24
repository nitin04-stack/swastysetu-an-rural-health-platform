from backend.ml.predict import explain_biomarker_finding


def test_eye_severe_change_has_clear_problem_description():
    result = explain_biomarker_finding("eye", "Severe_change")
    assert "severe" in result.lower()
    assert "eye" in result.lower() or "conjunctiva" in result.lower()


def test_tongue_normal_has_simple_positive_description():
    result = explain_biomarker_finding("tongue", "Normal")
    assert "normal" in result.lower()
    assert "tongue" in result.lower()
