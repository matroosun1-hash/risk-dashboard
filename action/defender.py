"""
자동 대응 — 방어 ETF 분산매수 권고

매도대금의 50%를 4개 카테고리 방어 ETF로 분산 배분합니다.
나머지 50%는 현금 보유.
"""


def generate_defense_allocation(
    sell_total: float,
    config: dict,
) -> dict:
    """
    방어 포트폴리오 배분을 생성합니다.

    Args:
        sell_total: 매도 예상 총액 ($)
        config: action 설정

    Returns:
        배분 결과 딕셔너리
    """
    defense_pct = config.get("defense_allocation", 0.5)
    cash_pct = config.get("cash_allocation", 0.5)
    etf_config = config.get("defense_etfs", {})

    defense_amount = sell_total * defense_pct
    cash_amount = sell_total * cash_pct

    # 4개 카테고리 균등 배분
    categories = list(etf_config.keys())
    if not categories:
        return {
            "defense_amount": defense_amount,
            "cash_amount": cash_amount,
            "allocations": [],
        }

    per_category = defense_amount / len(categories)

    allocations = []
    for cat in categories:
        tickers = etf_config[cat]
        per_ticker = per_category / len(tickers) if tickers else 0

        for ticker in tickers:
            allocations.append({
                "ticker": ticker,
                "category": cat,
                "amount": per_ticker,
            })

    return {
        "sell_total": sell_total,
        "defense_amount": defense_amount,
        "cash_amount": cash_amount,
        "defense_pct": defense_pct,
        "cash_pct": cash_pct,
        "allocations": allocations,
    }


def format_defense_report(allocation: dict) -> str:
    """방어 ETF 배분을 보기 좋은 텍스트로 포맷합니다."""
    lines = []
    lines.append("  ── 방어 ETF 배분 권고 ──")
    lines.append(f"    매도 예상 총액: ${allocation['sell_total']:,.0f}")
    lines.append(f"    방어 ETF 배분 ({allocation['defense_pct']:.0%}): ${allocation['defense_amount']:,.0f}")
    lines.append(f"    현금 보유 ({allocation['cash_pct']:.0%}): ${allocation['cash_amount']:,.0f}")
    lines.append("")

    # 카테고리별 그룹핑
    by_cat = {}
    for a in allocation["allocations"]:
        cat = a["category"]
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(a)

    cat_labels = {
        "individual": "🏢 방어 개별주",
        "sector": "📊 섹터 ETF",
        "bond": "📈 채권",
        "alternative": "🛢️ 대체자산",
    }

    for cat, items in by_cat.items():
        label = cat_labels.get(cat, cat)
        lines.append(f"    {label}:")
        for item in items:
            lines.append(f"      - {item['ticker']:<8} ${item['amount']:>10,.0f}")

    lines.append("")
    return "\n".join(lines)
