import sys
from pathlib import Path
import numpy as np, pandas as pd, requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


URL = "https://api.morpho.org/graphql"
MARKET = sys.argv[1] if len(sys.argv) > 1 else "PASTE_MARKET_ID"
CHAIN = int(sys.argv[2]) if len(sys.argv) > 2 else 1
FEE = 0.0
START_TS = 1746316800
SECONDS_PER_YEAR = 31_536_000

def gql(q, v=None):
    r = requests.post(URL, json={"query": q, "variables": v or {}}).json()
    if "errors" in r: raise SystemExit(r["errors"])
    return r["data"]

def fetch_meta():
    q = """query($id: String!, $c: Int!) {marketById(marketId: $id, chainId: $c) {
    loanAsset { symbol decimals } collateralAsset { symbol } lltv }}"""
    m = gql(q, {"id": MARKET, "c": CHAIN})["marketById"]
    return {"dec": int(m["loanAsset"]["decimals"]), "lltv": int(m["lltv"]) / 1e18,
            "loan": m["loanAsset"]["symbol"], "coll": m["collateralAsset"]["symbol"]}

def fetch():
    t = gql('{__type(name: "Market"){fields{name type{name ofType{name}}}}}')["__type"]["fields"]
    ht = next(f for f in t if f["name"] == "historicalState")["type"]
    hname = ht["name"] or ht["ofType"]["name"]
    have = {f["name"] for f in gql(f'{{__type(name:"{hname}") {{fields{{name}}}}}}')["__type"]["fields"]}
    want = ["supplyAssets", "borrowAssets", "supplyApy", 
            "borrowApy", "rateAtTarget", 
            "collateralAssetsUsd", "borrowAssetsUsd"]
    use = [w for w in want if w in have]
    print("available:", use, "| missing:", [w for w in want if w not in have], file=sys.stderr)
    body = "\n".join(f"{f}(options: $o){{ x y }}" for f in use)
    q = f"""query($id: String!, $c: Int!, $o: TimeseriesOptions) {{
    marketById(marketId: $id, chainId: $c) {{ historicalState {{ {body} }} }} }}"""
    o = {"startTimestamp": START_TS, "endTimestamp": int(pd.Timestamp.now().timestamp()),
         "interval": "DAY"}
    h = gql(q, {"id": MARKET, "c": CHAIN, "o": o})["marketById"]["historicalState"]
    cols = {f: pd.DataFrame(h[f]).assign(x=lambda d: 
                                         pd.to_datetime(d.x, unit="s")).set_index("x")["y"].astype(float) for f in use}
    return pd.concat(cols, axis=1).sort_index()

def irm(u, r_t, k=4, tgt=0.9):
    err = np.where(u > tgt, (u - tgt) / (1 - tgt), (u - tgt) / tgt)
    return r_t * np.where(err > 0, (k - 1) * err + 1, (1 - 1 / k) * err + 1)

def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)

def pct(x, n=2):
    return "n/a" if pd.isna(x) else f"{x:.{n}%}"

def shade_stress(ax, d):
    for _, g in d[d["stress"]].groupby("ep"):
        ax.axvspan(g["date"].min() - pd.Timedelta(hours=12), g["date"].max() + pd.Timedelta(hours=12),
                   color="red", alpha=0.12, lw=0)

def make_chart(d, meta, path):
    has_apy, has_hf = "supplyApy" in d, "agg_hf" in d
    n = 2 + has_apy + has_hf
    fig, axes = plt.subplots(n, 1, figsize=(11, 2.8 * n + 1), sharex=True)
    axes = iter(axes)

    a = next(axes)
    a.plot(d["date"], d["util"] * 100, lw=1.4)
    a.axhline(90, color="red", ls="--", lw=1, label="IRM target (90%)")
    a.set_ylabel("Utilization (%)"); a.set_ylim(0, 105); a.legend(loc="lower left")

    a = next(axes)
    top = max(d["supply"].max(), d["borrow"].max())
    div, unit = (1e6, "millions") if top >= 1e6 else (1e3, "thousands") if top >= 1e3 else (1, "units")
    a.plot(d["date"], d["supply"] / div, lw=1.4, label="Supply")
    a.plot(d["date"], d["borrow"] / div, lw=1.4, label="Borrow")
    a.set_ylabel(f"{meta['loan']} ({unit})"); a.legend(loc="upper left")

    if has_apy:
        a = next(axes)
        a.plot(d["date"], d["supplyApy"] * 100, lw=1.4, label="Supply APY")
        if "borrowApy" in d:
            a.plot(d["date"], d["borrowApy"] * 100, lw=1.2, alpha=0.7, label="Borrow APY")
        a.set_ylabel("APY (%)"); a.legend(loc="upper left")

    if has_hf:
        a = next(axes)
        a.plot(d["date"], d["agg_hf"], lw=1.4, label="Aggregate HF")
        a.axhline(1.0, color="black", ls=":", lw=1, label="Liquidation (HF = 1)")
        a.set_ylabel("Aggregate HF"); a.legend(loc="upper left")

    for ax in fig.axes:
        shade_stress(ax, d)
        ax.grid(alpha=0.3)
    fig.suptitle(f"{meta['coll']}/{meta['loan']} ({meta['lltv']:.0%} LLTV): market history, stress periods shaded")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def analyse(df, meta):
    dec, lltv = meta["dec"], meta["lltv"]
    pair = f"{meta['coll']}/{meta['loan']}"
    df = df.copy()
    df["supply"], df["borrow"] = df["supplyAssets"] / 10**dec, df["borrowAssets"] / 10**dec
    df = df[df["supply"] > 0.01 * df["supply"].max()]          # drop dust-era rows
    df["util"] = df["borrow"] / df["supply"]
    df["liquidity"] = df["supply"] - df["borrow"]
    if "collateralAssetsUsd" in df and "borrowAssetsUsd" in df:
        df["agg_hf"] = df["collateralAssetsUsd"] * lltv / df["borrowAssetsUsd"].replace(0, np.nan)
    if "rateAtTarget" in df:
        df["rate_target_apr"] = df["rateAtTarget"] * SECONDS_PER_YEAR / 1e18
    df["stress"] = df["util"] >= 0.9
    df["ep"] = (df["stress"] != df["stress"].shift()).cumsum()
    d = df.reset_index().rename(columns={df.index.name or "index": "date"})
    st, ok = d[d["stress"]], d[~d["stress"]]

    out = Path("outputs/reports")
    out.mkdir(parents=True, exist_ok=True)  # parents=True creates 'outputs' and 'reports' together
    stem = f"{meta['coll']}_{meta['loan']}_{MARKET[:10]}_{pd.Timestamp.now():%Y%m%d}"
    chart_path = out / f"{stem}_chart.png"
    make_chart(d, meta, chart_path)

    L = []

    L.append(f"# Morpho Blue market report: {pair} ({lltv:.0%} LLTV)")
    L.append(f"Market `{MARKET}` | chain {CHAIN} | data {d['date'].min():%Y-%m-%d} to {d['date'].max():%Y-%m-%d} "
             f"({len(d)} days) | generated {pd.Timestamp.now():%Y-%m-%d}\n")
    L += [f"![{pair} market history]({chart_path.name})\n"]

    if st.empty:
        L.append("No days at or above 90% utilization in this window.")
    else:
        agg = dict(start=("date", "min"), end=("date", "max"), days=("date", "count"),
                   mean_util=("util", "mean"), max_util=("util", "max"), min_liq=("liquidity", "min"),
                   peak_supply=("supply", "max"), peak_borrow=("borrow", "max"))
        if "agg_hf" in d:
            agg["min_hf"] = ("agg_hf", "min")
        ep = st.groupby("ep").agg(**agg).sort_values("start")

        last = d.iloc[-1]
        S = [["Latest supply / borrow (" + meta["loan"] + ")", f"{last['supply']:,.0f} / {last['borrow']:,.0f}"],
             ["Latest utilization", pct(last["util"], 1)],
             ["Days >= 90% utilization", f"{len(st)} of {len(d)} ({len(st) / len(d):.1%})"],
             ["Stress episodes / median duration", f"{len(ep)} / {ep['days'].median():.0f} d"],
             ["Mean utilization in stress", pct(st["util"].mean(), 1)],
             ["Lowest free liquidity in stress", f"{ep['min_liq'].min():,.0f} {meta['loan']}"]]
        if "supplyApy" in d:
            S.append(["Mean supply APY, stress vs normal", f"{pct(st['supplyApy'].mean())} vs {pct(ok['supplyApy'].mean())}"])
        if "agg_hf" in d:
            S.append(["Aggregate HF, min / stress median", f"{d['agg_hf'].min():.2f} / {st['agg_hf'].median():.2f}"])
        if "rate_target_apr" in d:
            S.append(["Implied rate_at_target (stress mean)", pct(st["rate_target_apr"].mean())])
        L += ["## Summary", md_table(["Metric", "Value"], S), ""]

        hdr = ["Start", "End", "Days", "Mean util", "Max util", "Min free liq", "Peak supply", "Peak borrow"]
        if "min_hf" in ep:
            hdr.append("Min agg HF")
        rows = []
        for r in ep.itertuples(index=False):
            row = [f"{r.start:%Y-%m-%d}", f"{r.end:%Y-%m-%d}", r.days, pct(r.mean_util, 1), pct(r.max_util, 1),
                   f"{r.min_liq:,.0f}", f"{r.peak_supply:,.0f}", f"{r.peak_borrow:,.0f}"]
            if "min_hf" in ep:
                row.append(f"{r.min_hf:.2f}")
            rows.append(row)
        L += [f"## Stress episodes (utilization >= 90%, amounts in {meta['loan']})", md_table(hdr, rows), ""]

        metrics = [("Utilization", "util", pct), ("Supply APY", "supplyApy", pct), ("Borrow APY", "borrowApy", pct),
                   ("rate_at_target (APR)", "rate_target_apr", pct), ("Aggregate HF", "agg_hf", lambda x: f"{x:.2f}")]
        rows = []
        for name, c, f in metrics:
            if c in d:
                rows.append([name] + [f(g[c].agg(a)) if a != "p90" else f(g[c].quantile(.9))
                                      for g in (ok, st) for a in ("mean", "median", "p90")])
        L += ["## Stress vs normal", md_table(["Metric", "Normal mean", "Normal median", "Normal p90",
                                                "Stress mean", "Stress median", "Stress p90"], rows), ""]

        L += ["## Theoretical supply APY by utilization (AdaptiveCurveIRM shape, fixed rate_at_target)",
              md_table(["rate_at_target", "U=90%", "U=93%", "U=96%", "U=100%"],
                       [[f"{rt:.0%}"] + [pct(irm(u, rt) * u * (1 - FEE), 1) for u in (0.90, 0.93, 0.96, 1.0)]
                        for rt in (0.02, 0.04, 0.08)]), ""]

        u = st["util"].values
        rows = [[f"{rt:.0%}", pct((irm(u, rt) * u * (1 - FEE)).mean())] for rt in (0.02, 0.04, 0.08)]
        if "supplyApy" in d:
            rows.append(["realized", pct(st["supplyApy"].mean())])
        L += ["## Expected supply APY on stress days", md_table(["rate_at_target", "E[supply APY]"], rows), ""]

        L += ["## Notes",
              "- Theoretical rows hold rate_at_target fixed; the real curve adapts over time, so use the realized row.",
              "- Aggregate HF = collateral USD x LLTV / borrow USD. It averages across borrowers and hides weak positions.",
              "- Daily samples; intraday spikes in utilization are not captured."]

    text = "\n".join(L)
    print(text)
    path = out / f"{stem}.md"
    path.write_text(text + "\n")
    print(f"\nSaved: {path} (+ {chart_path.name})", file=sys.stderr)


if __name__ == "__main__":
    analyse(fetch(), fetch_meta())