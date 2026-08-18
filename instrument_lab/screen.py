"""What does a weekly covered-call income strategy actually require of an instrument?

The weekly P&L of a short call is   premium  -  max(0, S_T - K).
Under fair pricing the premium equals the RISK-NEUTRAL expectation of that payout
(drift = r). What you actually pay out is the REAL-WORLD expectation (drift = mu).
So, to a first order,

    edge  ~=  vega x (IV - RV)   -   delta x (mu - r) x T
              ^ the variance risk    ^ the drift you hand over on the capped part
                premium you collect

Both terms are measurable. That gives one screening number that needs only price
history: the VRP an instrument must earn for a weekly covered call to break even.
Low required VRP = a good covered-call instrument. SOXL's is enormous.
"""
import os, sys
import numpy as np, pandas as pd
from scipy.optimize import brentq
from scipy.special import ndtr

ROOT = "/home/user/TradingModel"
OUT = os.path.join(ROOT, "instrument_lab/out")
T = 1.0 / 52.0


def bs_call(S, K, T, sig, r=0.0):
    sig = max(sig, 1e-6)
    d1 = (np.log(S / K) + (r + .5 * sig ** 2) * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    return S * ndtr(d1) - K * np.exp(-r * T) * ndtr(d2)


def bs_delta(S, K, T, sig, r=0.0):
    sig = max(sig, 1e-6)
    return ndtr((np.log(S / K) + (r + .5 * sig ** 2) * T) / (sig * np.sqrt(T)))


def strike_for_delta(S, T, sig, tgt=0.20):
    f = lambda k: bs_delta(S, k, T, sig) - tgt
    return brentq(f, S * 1.0001, S * 8.0)


def weekly_from_5min(name):
    df = pd.read_csv(f"{ROOT}/{name}")
    ts = df["Date"].str.replace(" America/New_York", "", regex=False)
    df["ts"] = pd.to_datetime(ts, format="%Y%m%d %H:%M:%S")
    d = df.groupby(df.ts.dt.normalize()).Close.last()
    iso = d.index.isocalendar()
    key = pd.Series(list(zip(iso.year, iso.week)), index=d.index)
    wk = d.groupby(key.values).last()
    order = d.groupby(key.values).apply(lambda s: s.index[-1]).sort_values()
    wk = wk.reindex(order.index)
    wk.index = order.values
    return wk.pct_change().dropna()


def profile(ret, label, delta_tgt=0.20, scale=1.0):
    """ret = weekly simple returns. scale applies synthetic leverage."""
    r = ret * scale
    rv = r.std() * np.sqrt(52)
    S = 100.0
    K = strike_for_delta(S, T, rv, delta_tgt)
    otm = K / S - 1
    prem = bs_call(S, K, T, rv)                       # premium if IV == RV
    cap = np.maximum(0.0, S * (1 + r.values) - K).mean()   # real-world payout
    edge = prem - cap
    # what IV would make the premium cover the real payout?
    try:
        iv_req = brentq(lambda s: bs_call(S, K, T, s) - cap, 1e-4, 10.0)
    except ValueError:
        iv_req = np.nan
    return dict(instrument=label, wk_mean=r.mean(), ann_drift=r.mean() * 52,
                ann_vol=rv, skew=pd.Series(r).skew(), kurt=pd.Series(r).kurtosis(),
                otm_pct=otm, prem_pct=prem / S,
                p_assign=(r > otm).mean(), cap_pct=cap / S,
                edge_pct=edge / S, edge_ann=edge / S * 52,
                iv_req=iv_req, vrp_req=iv_req - rv)


FMT = {"ann_drift": "{:+.1%}".format, "ann_vol": "{:.1%}".format, "skew": "{:+.2f}".format,
       "kurt": "{:.1f}".format, "otm_pct": "{:.2%}".format, "prem_pct": "{:.3%}".format,
       "p_assign": "{:.1%}".format, "cap_pct": "{:.3%}".format, "edge_pct": "{:+.3%}".format,
       "edge_ann": "{:+.1%}".format, "iv_req": "{:.1%}".format, "vrp_req": "{:+.1f}pp".format}
COLS = ["ann_drift", "ann_vol", "skew", "kurt", "otm_pct", "prem_pct", "p_assign",
        "cap_pct", "edge_pct", "edge_ann", "vrp_req"]


def fmt_vrp(v):
    return f"{v*100:+.1f}pp"


if __name__ == "__main__":
    rows = []
    soxl = weekly_from_5min("SOXL_5min_6Years.csv")
    fas = weekly_from_5min("FAS_5min_6Years.csv")
    soxs = weekly_from_5min("SOXS_5min_6Years.csv")
    W = pd.Timestamp("2022-01-01")
    for lab, r, sc in [("SOXL  3x semis", soxl[soxl.index >= W], 1.0),
                       ("SOXS  -3x semis", soxs[soxs.index >= W], 1.0),
                       ("FAS   3x financials", fas[fas.index >= W], 1.0),
                       ("semis index (SOXL/3)", soxl[soxl.index >= W], 1 / 3),
                       ("financials (FAS/3)", fas[fas.index >= W], 1 / 3),
                       ("SOXL full 6y", soxl, 1.0),
                       ("semis index full 6y", soxl, 1 / 3)]:
        rows.append(profile(r, lab, scale=sc))
    d = pd.DataFrame(rows).set_index("instrument")
    d["vrp_req"] = d["vrp_req"].map(fmt_vrp)
    print("=" * 132)
    print("WEEKLY COVERED CALL AT A 20-DELTA STRIKE, premium priced at the instrument's OWN")
    print("realised vol (i.e. assuming ZERO variance risk premium). edge = premium - real payout.")
    print("vrp_req = the implied-minus-realised vol the instrument MUST earn just to break even.")
    print("=" * 132)
    print(d[COLS].to_string(formatters={k: v for k, v in FMT.items() if k != "vrp_req"}))
    d.to_csv(f"{OUT}/instrument_profile.csv")


def delta_sweep(ret, label, scale=1.0, deltas=(0.40, 0.30, 0.20, 0.15, 0.10, 0.05)):
    r = ret * scale
    rv = r.std() * np.sqrt(52)
    S = 100.0
    out = []
    for dl in deltas:
        K = strike_for_delta(S, T, rv, dl)
        prem = bs_call(S, K, T, rv)
        cap = np.maximum(0.0, S * (1 + r.values) - K).mean()
        out.append(dict(instrument=label, delta=dl, otm=K / S - 1, prem=prem / S,
                        cap=cap / S, edge=(prem - cap) / S,
                        edge_ann=(prem - cap) / S * 52, p_assign=(r > K / S - 1).mean()))
    return pd.DataFrame(out)


def counterfactual(ret, label, scale=1.0, delta=0.20):
    """Which property is doing the damage? Rebuild the return series with one
    feature neutralised at a time and re-measure the edge."""
    r = pd.Series(ret.values * scale)
    rv = r.std() * np.sqrt(52); S = 100.0
    K = strike_for_delta(S, T, rv, delta)
    prem = bs_call(S, K, T, rv)
    def edge_of(x):
        return (prem - np.maximum(0.0, S * (1 + np.asarray(x)) - K).mean()) / S * 52
    demeaned = r - r.mean()                       # drift removed
    flipped = -(r - r.mean()) + r.mean()          # skew sign flipped, drift kept
    gauss = np.random.default_rng(0).normal(r.mean(), r.std(), 200_000)  # no fat tails
    return dict(instrument=label, actual=edge_of(r), no_drift=edge_of(demeaned),
                skew_flipped=edge_of(flipped), gaussian=edge_of(gauss))
