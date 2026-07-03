from unittest.mock import MagicMock, patch

from app.modules.contact.verifier import verify_email


def test_unconfigured_reacher_degrades_to_low():
    # 默认 settings.reacher_base_url == ""：保守降级，不冒充已验证
    r = verify_email("a@b.com")
    assert r.status == "unverified" and r.confidence == "low"


def _mock_reacher(reachable: str):
    resp = MagicMock()
    resp.json.return_value = {"is_reachable": reachable}
    resp.raise_for_status.return_value = None
    return resp


@patch("app.modules.contact.verifier.get_settings")
@patch("app.modules.contact.verifier.httpx.post")
def test_reacher_mapping(mock_post, mock_settings):
    mock_settings.return_value.reacher_base_url = "http://verify:8080"
    cases = {"safe": ("valid", "high"), "risky": ("catch_all", "medium"),
             "invalid": ("invalid", "invalid"), "unknown": ("unknown", "low")}
    for reachable, (status, conf) in cases.items():
        mock_post.return_value = _mock_reacher(reachable)
        r = verify_email("a@b.com")
        assert (r.status, r.confidence) == (status, conf)
