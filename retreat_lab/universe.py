"""The screen universe: liquid instruments across every asset class IBKR lists.

Chosen for BREADTH OF MECHANISM, not for plausibility. The point of a wide
screen is to test the one-factor claim — that SOXL's overnight edge is levered
semiconductor beta and therefore anything hedging it also hedges the return —
rather than to confirm it with a list of things already believed to work.

So this deliberately includes the categories most likely to falsify it:

  * managed futures and anti-beta funds (DBMF, KMLM, CTA, BTAL, TAIL, SWAN),
    which target a payoff shape rather than a direction
  * currencies, especially the yen and the dollar, which move on carry unwinds
    that have nothing to do with semiconductor earnings
  * gold and precious metals, the classical flight-to-quality
  * the whole rates complex including inverse, because "bonds rally in a crash"
    is an assumption this repository has not tested overnight
  * international equity, where a US semis gap may or may not transmit

and the categories that will obviously score well and must be in the table so
the trap is visible: inverse equity and volatility products.

Liquidity is enforced downstream by the screen (minimum session count), not
here — a name with thin history simply drops out.
"""

UNIVERSE = {
    "volatility": ["VIXY", "VXX", "UVXY", "SVXY", "VIXM", "TAIL", "SWAN"],
    "inverse_equity": ["SQQQ", "SPXS", "SDOW", "SOXS", "TZA", "SH", "PSQ",
                       "DOG", "RWM", "SPXU", "FAZ", "LABD", "TECS"],
    "anti_beta_alt": ["BTAL", "DBMF", "KMLM", "CTA", "NTSX", "MNA", "QAI"],
    "rates_long": ["TLT", "IEF", "SHY", "TMF", "UBT", "TYD", "AGG", "BND",
                   "GOVT", "SPTL", "VGLT", "EDV", "ZROZ"],
    "rates_short": ["TBT", "TMV", "TBF", "PST", "TYO"],
    "credit": ["LQD", "HYG", "JNK", "EMB", "BKLN", "SRLN", "SJB"],
    "inflation_cash": ["TIP", "VTIP", "SCHP", "BIL", "SGOV", "SHV", "USFR"],
    "metals": ["GLD", "IAU", "SLV", "GDX", "GDXJ", "NUGT", "DUST", "JDST",
               "UGL", "AGQ", "PPLT", "PALL", "SIVR", "SGOL"],
    "energy_commod": ["USO", "UNG", "DBC", "PDBC", "DBA", "CPER", "BNO",
                      "UCO", "KOLD", "BOIL", "DBO"],
    "currency": ["UUP", "UDN", "FXE", "FXY", "FXB", "FXF", "FXA", "FXC",
                 "CEW", "YCS", "EUO"],
    "crypto": ["BITO", "GBTC", "IBIT", "ETHE", "MSTR", "COIN", "MARA", "RIOT",
               "BITX", "ETHU"],
    "international": ["EWJ", "EWZ", "EWG", "EWU", "EWY", "EWT", "FXI", "MCHI",
                      "INDA", "EFA", "EEM", "VGK", "VWO", "EWH", "EWA", "EWC",
                      "EWW", "EZA", "TUR", "EPOL", "ARGT", "KWEB", "YINN"],
    "sectors": ["XLU", "XLP", "XLV", "XLE", "XLF", "XLI", "XLB", "XLRE",
                "XLK", "XLY", "XLC", "VNQ", "IYR", "KRE", "XBI", "IBB",
                "ITA", "XME", "XOP", "OIH", "KIE", "XRT", "PAVE", "JETS",
                "MOO", "WOOD", "COPX", "URA", "LIT", "TAN", "ICLN"],
    "semis": ["SMH", "SOXX", "SOXL", "USD", "NVDA", "AMD", "INTC", "TSM",
              "AVGO", "MU", "QCOM", "TXN", "ASML", "AMAT", "LRCX", "KLAC"],
    "defensive_equity": ["USMV", "SPLV", "VYM", "SCHD", "NOBL", "DVY", "HDV",
                         "SPHD", "FDLO", "JEPI", "JEPQ", "DIVO"],
    "broad_equity": ["SPY", "QQQ", "IWM", "DIA", "VTI", "MDY", "RSP", "VOO",
                     "IVV", "EQAL"],
    "leveraged_long": ["TQQQ", "UPRO", "SPXL", "TECL", "FAS", "TNA", "LABU",
                       "QLD", "SSO", "UDOW", "UMDD", "UTSL", "DRN", "NAIL"],
    "megacap": ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "BRK B",
                "JPM", "XOM", "WMT", "PG", "JNJ", "KO", "PEP", "VZ", "T",
                "PFE", "MRK", "CVX", "UNH", "HD", "MCD", "COST", "LLY"],
}


def symbols() -> "list[str]":
    """Every symbol, de-duplicated, in a stable order."""
    seen, out = set(), []
    for group in UNIVERSE.values():
        for s in group:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def group_of(symbol: str) -> str:
    for name, members in UNIVERSE.items():
        if symbol in members:
            return name
    return "?"


if __name__ == "__main__":
    print(f"{len(symbols())} symbols across {len(UNIVERSE)} classes")
    for k, v in UNIVERSE.items():
        print(f"  {k:<18}{len(v):>4}")
