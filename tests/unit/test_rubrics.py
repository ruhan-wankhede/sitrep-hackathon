from app.rubrics import resolve_rubric, DEFAULTS

def test_instructions_override_wins():
    r = resolve_rubric("Backend Engineer", "Be strict.\ncompetencies: Kubernetes, GraphQL, Mentoring")
    assert r == ["Kubernetes", "GraphQL", "Mentoring"]

def test_engineering_family_matched_from_title():
    assert resolve_rubric("Senior Backend Engineer", "") == DEFAULTS["engineering"]
    assert resolve_rubric("Software Developer", "") == DEFAULTS["engineering"]

def test_sales_and_pm_families():
    assert resolve_rubric("Account Executive", "") == DEFAULTS["sales"]
    assert resolve_rubric("Product Manager", "") == DEFAULTS["pm"]

def test_unknown_title_falls_back_to_generic():
    assert resolve_rubric("Chief Vibes Officer", "") == DEFAULTS["generic"]
