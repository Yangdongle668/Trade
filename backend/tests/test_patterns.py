from app.modules.contact.patterns import generate_email_patterns, generic_candidates


def test_two_part_name_order():
    out = generate_email_patterns("John Smith", "example.com")
    assert out[0] == "john.smith@example.com"   # 最常见模式优先
    assert "john@example.com" in out
    assert "jsmith@example.com" in out


def test_name_cleaning_and_middle_name():
    out = generate_email_patterns("  Mary-Jane  O'Connor  ", "x.co.uk")
    assert out[0] == "maryjane.oconnor@x.co.uk"


def test_single_name():
    assert generate_email_patterns("Cher", "x.com") == ["cher@x.com"]


def test_empty_name():
    assert generate_email_patterns("", "x.com") == []


def test_generic():
    assert generic_candidates("x.com")[0] == "sales@x.com"
