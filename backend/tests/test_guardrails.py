from app.modules.ai_gateway.guardrails import check_email_body
from app.modules.sequence.generator import _fact_check

BODY_OK = ("Hi Megan, congrats on opening the Bend showroom last month. We manufacture "
           "adjustable LED track systems for lighting retailers in the US Northwest. "
           "Would it be worth sending over a short line sheet? Best regards, Wei")


def test_clean_email_passes():
    assert check_email_body("Track lighting for your new showroom", BODY_OK).ok


def test_spam_words_flagged():
    r = check_email_body("FREE best price!!!", BODY_OK)
    assert not r.ok and any("spam" in v for v in r.violations)


def test_too_many_links_flagged():
    body = BODY_OK + " https://a.com https://b.com"
    assert not check_email_body("hi", body).ok


def test_fact_check_rejects_unsourced_claims():
    sources = "moq=200 units; cert=ETL; lead_time=25 days"
    assert _fact_check("Our MOQ is 200 units with ETL listing.", sources) == []
    v = _fact_check("Our MOQ is 500 units with UL and CE listing.", sources)
    assert any("500" in x for x in v)
    assert any("UL" in x for x in v) and any("CE" in x for x in v)
