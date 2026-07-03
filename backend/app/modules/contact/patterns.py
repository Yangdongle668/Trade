"""邮箱模式推测（03 文档 S7 第一步）。

生成顺序即优先级：北美/英国 B2B 最常见的模式在前。
"""
import re

GENERIC_MAILBOXES = ["sales", "info", "hello", "contact"]  # 兜底，置信度恒为 low


def _clean(part: str) -> str:
    return re.sub(r"[^a-z]", "", part.lower())


def generate_email_patterns(full_name: str, domain: str) -> list[str]:
    parts = [p for p in (_clean(x) for x in full_name.strip().split()) if p]
    out: list[str] = []
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        out = [
            f"{first}.{last}@{domain}",   # john.smith@
            f"{first}@{domain}",          # john@（小公司最常见）
            f"{first[0]}{last}@{domain}", # jsmith@
            f"{first}{last}@{domain}",    # johnsmith@
            f"{first[0]}.{last}@{domain}",# j.smith@
            f"{last}.{first}@{domain}",   # smith.john@
        ]
    elif len(parts) == 1:
        out = [f"{parts[0]}@{domain}"]
    return out


def generic_candidates(domain: str) -> list[str]:
    return [f"{box}@{domain}" for box in GENERIC_MAILBOXES]
