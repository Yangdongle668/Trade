"""反垃圾写作闸门（FR-GEN-04）：超标 = 拒绝入队，宁可重生成。

结构化校验而非提示词约定（ADR-7 同源思想）：
字数、链接数、大写比例、spam 触发词。
"""
import re
from dataclasses import dataclass, field

SPAM_WORDS = {
    "free", "100%", "guarantee", "guaranteed", "no risk", "act now", "buy now",
    "cheap", "cheapest", "best price", "lowest price", "limited time", "click here",
    "winner", "urgent", "!!!", "$$$", "amazing deal", "once in a lifetime",
}
MAX_WORDS = 180          # 首信短于 180 词回复率最好
MAX_LINKS = 1
MAX_UPPER_RATIO = 0.2


@dataclass
class GuardrailReport:
    ok: bool
    violations: list[str] = field(default_factory=list)


def check_email_body(subject: str, body: str) -> GuardrailReport:
    violations: list[str] = []
    text = f"{subject}\n{body}".lower()

    hits = sorted(w for w in SPAM_WORDS if w in text)
    if hits:
        violations.append(f"spam 触发词: {', '.join(hits[:5])}")

    words = len(body.split())
    if words > MAX_WORDS:
        violations.append(f"正文过长 {words} 词（上限 {MAX_WORDS}）")
    if words < 20:
        violations.append("正文过短，疑似生成失败")

    links = len(re.findall(r"https?://", body))
    if links > MAX_LINKS:
        violations.append(f"链接过多 {links} 个（上限 {MAX_LINKS}）")

    letters = [c for c in subject if c.isalpha()]
    if letters:
        upper = sum(c.isupper() for c in letters) / len(letters)
        if upper > MAX_UPPER_RATIO:
            violations.append("主题行大写比例过高")

    return GuardrailReport(ok=not violations, violations=violations)
