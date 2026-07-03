"""域名归一化 —— 去重与撞单保护的基石，规则必须钉死。"""
from app.common.domain import normalize_domain


def test_strips_protocol_www_and_path():
    assert normalize_domain("https://www.example.com/about?x=1") == "example.com"
    assert normalize_domain("example.com") == "example.com"
    assert normalize_domain("HTTP://EXAMPLE.COM") == "example.com"


def test_subdomain_merges_to_registered_domain():
    assert normalize_domain("https://shop.brightline.co.uk/products") == "brightline.co.uk"


def test_multi_part_tld():
    assert normalize_domain("harborhale.com.au") == "harborhale.com.au"


def test_platform_domains_rejected():
    assert normalize_domain("https://www.linkedin.com/company/foo") is None
    assert normalize_domain("https://facebook.com/somepage") is None


def test_invalid_rejected():
    assert normalize_domain("") is None
    assert normalize_domain("not a url") is None
    assert normalize_domain("localhost") is None
