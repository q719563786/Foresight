import re


DOMAIN_KEYWORDS = {
    "health": ("医院", "住院", "手术", "医保", "医疗", "复课", "身体"),
    "cashflow": ("元", "工资", "收入", "支出", "费用", "账单", "贷款", "还款"),
    "work": ("工作", "工资", "客户", "工地", "全勤", "报销"),
    "policy": ("政策", "税", "平台规则", "监管"),
}


def create_candidate(text, occurred_at):
    """Create a conservative offline classification without pretending to be AI."""
    normalized = text.strip()
    domains = [
        domain
        for domain, keywords in DOMAIN_KEYWORDS.items()
        if any(keyword in normalized for keyword in keywords)
    ]
    amounts = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\s*元", normalized)]
    future_markers = ("预计", "可能", "将", "计划", "之前", "以后", "下周", "下月")
    high_risk = bool({"health", "cashflow"}.intersection(domains))
    return {
        "original_text": normalized,
        "occurred_at": occurred_at,
        "domains": domains or ["general"],
        "amounts": amounts,
        "requires_human_confirmation": high_risk,
        "can_register_forecast": any(marker in normalized for marker in future_markers),
        "confidence": "low",
    }
