from app import fundamentals

SNAP = {
    "instrument": {"name": "SAP SE"},
    "company": {"name": "SAP SE", "branch": {"name": "Standardsoftware", "sector": {"name": "Software"}}, "nameCountry": "Deutschland"},
    "stocksCnFundamentalList": {"list": [
        {"label": "2024", "cnPer": 50.1},
        {"label": "2025", "cnPer": 33.93, "cnDivYield": 1.2, "cnDps": 2.5, "cnPeg": 1.96, "cnPriceBookvalue": 5.46,
         "cnMarketCap": 243260045913.6, "cnFreeFloat": 75.5, "dateExDividend": "2025-05-14T12:00:00.000+00:00", "employees": 110650},
        {"label": "2026e", "cnPer": 28.0, "cnDivYield": 1.4}]},
    "stocksCnFinancialList": {"list": [
        {"label": "2025", "cnEbitMa": 28.79, "cnMarginNet": 19.46, "cnReturnEquity": 15.7, "cnEquityRatio": 62.7, "cnMarketCap": 243e9},
        {"label": "2026e", "cnMarketCap": 237935489082.75, "cnEpsAdj": 7.2}]},
    "stocksBalanceSheetList": {"list": [
        {"label": "2024", "turnover": 34176000000},
        {"label": "2025", "turnover": 36800000000, "earningsAfterTax": 7326000000, "eps": 6.14, "employees": 110650, "isoCurrency": "EUR"}]},
}


def test_stock_figures():
    out = fundamentals._stock(SNAP)
    f = out["figures"]
    assert out["kind"] == "stock" and out["sector"] == "Software" and out["year"] == "2025" and out["est_year"] == "2026"
    assert f["pe"] == 33.9 and f["pe_est"] == 28.0 and f["div_yield"] == 1.4 and f["revenue_growth"] == 7.7
    assert f["market_cap"] == 237935489083 and f["employees"] == 110650 and f["ex_dividend"] == "2025-05-14"


def test_fund_figures_and_text():
    snap = {
        "instrument": {"name": "iShares Core MSCI World"},
        "fundsDetails": {"nameTypeFund": "Aktienfonds", "fundsTypeCapitalisation": {"name": "Thesaurierend"},
                         "fundsTypeReplication": {"name": "sampling"}, "fundsInvestmentRegion": {"name": "International"}},
        "fundsBaseData": {"ongoingCharges": 0.20000000298, "volumeFundEuro": 131527516160.0, "dateEmission": "2009-09-25T00:00:00.000+00:00"},
        "fundsIssuer": {"nameGroupIssuer": "BlackRock"},
        "background": [{"type": "NewsParagraph", "value": "Der Fonds bildet den <b>MSCI World</b> ab."}],
        "fundsPerformanceList": {"list": [{"timeSpan": "1Y", "performanceTimeSpanPct": 14.91}]},
        "fundsHoldingList": {"list": [{"instrument": {"name": "Apple", "isin": "US0378331005"}, "investmentPct": 5.62}]},
    }
    out = fundamentals._fund(snap)
    assert out["kind"] == "fund" and out["issuer"] == "BlackRock"
    assert out["figures"]["ter"] == 0.2 and out["figures"]["perf_1y"] == 14.9 and out["figures"]["inception"] == "2009-09-25"
    assert out["description"]["text"] == "Der Fonds bildet den MSCI World ab."
    assert out["holdings"][0] == {"name": "Apple", "isin": "US0378331005", "pct": 5.62}


def test_short_text_cuts_at_sentence():
    t = "Erster Satz ist hier. " * 60
    s = fundamentals._short(t, 100)
    assert len(s) <= 100 and s.endswith(".")


def test_home_layout_setting_is_normalized():
    import json

    from app import settings_store
    raw = json.dumps({"order": ["news", "bogus", "tiles", "news"], "hidden": ["alerts", "x"], "private": 1})
    out = json.loads(settings_store.coerce("home_layout", raw))
    assert out["order"][:2] == ["news", "tiles"] and set(out["order"]) == set(settings_store.HOME_WIDGETS)
    assert out["hidden"] == ["alerts"] and out["private"] is True
    assert settings_store.coerce("home_layout", "") == ""
    assert "home_layout" in settings_store.USER_KEYS
