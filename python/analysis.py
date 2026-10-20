"""
Finance, Firms and Jobs in Ghana
World Bank Enterprise Survey, Ghana 2023 (713 formal private establishments)

Author: Evans K. Owusu, PhD
Workflow: analysis designed and built in Python with Claude as a coding assistant;
translated to R (../R/analysis.R) and cross-checked with ../verify_match.py.

Usage (from the repo root):
    python python/analysis.py data/Ghana-2023-full-data.dta
Outputs go to output/  (CSV tables, PNG charts, results_python.json)

The raw .dta file is covered by the Enterprise Surveys confidentiality agreement
and must not be committed or shared. Only aggregate results are reported.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from survey import StratifiedDesign  # noqa: E402

DATA = Path(sys.argv[1] if len(sys.argv) > 1 else "data/Ghana-2023-full-data.dta")
OUT = Path("output")
OUT.mkdir(exist_ok=True)

# =============================================================================
# 1. Load and clean
# =============================================================================
raw = pd.read_stata(DATA, convert_categoricals=False)


def clean(s):
    """WBES codes non-response as negatives (-9 don't know, -7 n/a, -6 in process...)."""
    s = pd.to_numeric(s, errors="coerce").astype(float)
    return s.where(s >= 0)


def yes_no(s):
    s = clean(s)
    return s.map({1: 1.0, 2: 0.0})


df = pd.DataFrame(index=raw.index)
df["wmedian"] = raw["wmedian"].astype(float)
df["strata"] = raw["strata"]

# --- Firm characteristics -----------------------------------------------------
l1, l2 = clean(raw["l1"]), clean(raw["l2"])
df["size"] = pd.cut(l1, [0, 19, 99, np.inf], labels=["Small", "Medium", "Large"]).astype(object)
df["size_medium"] = (df["size"] == "Medium").astype(float)
df["size_large"] = (df["size"] == "Large").astype(float)

sector_map = {1: "Food & beverages", 2: "Other manufacturing", 3: "Retail",
              4: "Hotels & restaurants", 5: "Other services"}
df["sector"] = raw["a4a"].map(sector_map)
for code, name in [(2, "othmfg"), (3, "retail"), (4, "hotels"), (5, "othserv")]:
    df[f"sector_{name}"] = (raw["a4a"] == code).astype(float)          # ref: food & bev

region_map = {1: "Greater Accra, Eastern, Volta, Oti", 2: "Ashanti & Bono regions",
              3: "Western & Central regions", 4: "Northern regions"}
df["region"] = raw["a2"].map(region_map)
for code, name in [(2, "ashanti"), (3, "western"), (4, "northern")]:
    df[f"region_{name}"] = (raw["a2"] == code).astype(float)           # ref: Greater Accra

age = raw["a14y"].astype(float) - clean(raw["b5"])
df["firm_age"] = age.where(age >= 0)
df["log_age"] = np.log1p(df["firm_age"])
df["young_firm"] = (df["firm_age"] <= 5).astype(float).where(df["firm_age"].notna())

df["female_mgr"] = yes_no(raw["b7a"])
df["female_own"] = yes_no(raw["b4"])
exp_share = clean(raw["d3b"]).fillna(0) + clean(raw["d3c"]).fillna(0)
df["exporter"] = (exp_share >= 10).astype(float).where(clean(raw["d3b"]).notna() | clean(raw["d3c"]).notna())
df["audited"] = yes_no(raw["k21"])
df["website"] = yes_no(raw["c22b"])
df["innovator"] = ((yes_no(raw["h1"]) == 1) | (yes_no(raw["h5"]) == 1)).astype(float)
df.loc[yes_no(raw["h1"]).isna() & yes_no(raw["h5"]).isna(), "innovator"] = np.nan

# --- Finance outcomes ---------------------------------------------------------
k30 = clean(raw["k30"])
df["finance_major"] = (k30 >= 3).astype(float).where(k30.notna())
m1a = clean(raw["m1a"])
obstacle_map = {1: "Access to finance", 2: "Access to land", 3: "Licensing & permits",
                4: "Corruption", 5: "Courts", 6: "Crime & theft", 7: "Customs & trade",
                8: "Electricity", 9: "Skills shortage", 10: "Labour regulations",
                11: "Political instability", 12: "Informal competitors",
                13: "Tax administration", 14: "Tax rates", 15: "Transport"}
df["biggest_obstacle"] = m1a.map(obstacle_map)

df["has_account"] = yes_no(raw["k6"])
k82 = clean(raw["k82"])
df["has_credit"] = k82.map({1: 1.0, 2: 1.0, 3: 1.0, 4: 0.0})
k162 = clean(raw["k162"])
df["applied"] = k162.map({1: 1.0, 2: 1.0, 3: 1.0, 4: 0.0})
k17 = clean(raw["k17"])
reason_map = {1: "No need (enough capital)", 2: "Complex procedures",
              3: "Unfavourable interest rates", 4: "Collateral too high",
              5: "Loan size/maturity too small", 6: "Did not expect approval", 7: "Other"}
df["reason_not_applying"] = k17.map(reason_map)

# Credit need: applied, or did not apply for a reason other than "no need"
df["needs_credit"] = np.select(
    [df["applied"] == 1, (df["applied"] == 0) & k17.between(2, 7), (df["applied"] == 0) & (k17 == 1)],
    [1.0, 1.0, 0.0], default=np.nan)
df["discouraged"] = np.where(df["needs_credit"] == 1, 1.0 - df["applied"], np.nan)

k20 = clean(raw["k20a1"])
approved = k20.map({1: 1.0, 2: 1.0, 3: 0.0, 4: 0.0})
df["applied_approved"] = np.select(
    [df["applied"] == 0, (df["applied"] == 1) & approved.notna()],
    [0.0, approved], default=np.nan)
df["approved_if_applied"] = np.where(df["applied"] == 1, approved, np.nan)

# --- Infrastructure -------------------------------------------------------------
df["outages"] = yes_no(raw["c6"])
df["generator"] = yes_no(raw["c10"])

# --- Jobs: annualised employment growth over 3 years (DHS mid-point rate, %) ----
# Bounded, symmetric and defined when a firm grew from zero.
valid = l1.notna() & l2.notna() & ((l1 + l2) > 0)
df["emp_growth"] = np.where(valid, (l1 - l2) / ((l1 + l2) / 2) / 3 * 100, np.nan)
df["base_size_medium"] = np.where(l2.notna(), ((l2 >= 20) & (l2 < 100)).astype(float), np.nan)
df["base_size_large"] = np.where(l2.notna(), (l2 >= 100).astype(float), np.nan)

df.to_csv(OUT / "_analysis_vars_DO_NOT_SHARE.csv", index=False)   # firm-level: keep private

des = StratifiedDesign(df, "wmedian", "strata")
results = {}
print(f"Firms: {des.n}  strata: {des.n_strata}  weighted population: {df.wmedian.sum():,.0f}")

# =============================================================================
# 2. Headline indicators
# =============================================================================
headline_vars = {
    "finance_biggest_obstacle": (df["biggest_obstacle"] == "Access to finance").astype(float).where(df["biggest_obstacle"].notna()),
    "finance_major_obstacle": df["finance_major"],
    "has_account": df["has_account"],
    "needs_credit": df["needs_credit"],
    "applied": df["applied"],
    "applied_and_approved": df["applied_approved"],
    "has_credit": df["has_credit"],
    "discouraged_of_needing": df["discouraged"],
    "approved_if_applied": df["approved_if_applied"],
    "outages": df["outages"],
    "generator": df["generator"],
    "female_top_manager": df["female_mgr"],
    "female_ownership": df["female_own"],
}
head = []
for k, v in headline_vars.items():
    r = des.mean(v)
    head.append({"indicator": k, **r})
    results[f"mean.{k}"] = r["est"]
    results[f"se.{k}"] = r["se"]
head = pd.DataFrame(head)
head.to_csv(OUT / "01_headline_indicators.csv", index=False)
print(head.round(3).to_string(index=False))

# =============================================================================
# 3. PART 1 - What binds? Biggest obstacle, overall and by size
# =============================================================================
obs = des.shares(df["biggest_obstacle"])
obs.to_csv(OUT / "02_biggest_obstacle.csv", index=False)
for _, r in obs.iterrows():
    results[f"obstacle.{r['category']}"] = r["est"]
fin_top = headline_vars["finance_biggest_obstacle"]
by_size_top = des.mean_by(fin_top, df["size"])
by_size_top.to_csv(OUT / "02b_finance_top_by_size.csv", index=False)

# =============================================================================
# 4. PART 2 - The credit funnel and why firms don't borrow
# =============================================================================
funnel = pd.DataFrame([
    {"stage": "All firms", "est": 1.0},
    {"stage": "Have a bank account", "est": results["mean.has_account"]},
    {"stage": "Need external credit", "est": results["mean.needs_credit"]},
    {"stage": "Applied for credit", "est": results["mean.applied"]},
    {"stage": "Approved (full or part)", "est": results["mean.applied_and_approved"]},
])
funnel.to_csv(OUT / "03_credit_funnel.csv", index=False)

reasons_disc = des.shares(df["reason_not_applying"], domain=(df["discouraged"] == 1).to_numpy())
reasons_disc.to_csv(OUT / "04_reasons_discouraged.csv", index=False)
reasons_all = des.shares(df["reason_not_applying"], domain=(df["applied"] == 0).to_numpy())
reasons_all.to_csv(OUT / "04b_reasons_all_nonapplicants.csv", index=False)
for _, r in reasons_disc.iterrows():
    results[f"reason_disc.{r['category']}"] = r["est"]

# =============================================================================
# 5. PART 4 - Who is excluded? Size, women, young firms
# =============================================================================
groupings = {
    "Firm size": df["size"],
    "Top manager": df["female_mgr"].map({1.0: "Female", 0.0: "Male"}),
    "Ownership": df["female_own"].map({1.0: "Any female owner", 0.0: "No female owner"}),
    "Firm age": df["young_firm"].map({1.0: "Young (0-5 yrs)", 0.0: "Established (6+ yrs)"}),
}
gap_rows = []
for outcome in ["has_credit", "discouraged", "finance_major", "applied"]:
    for gname, g in groupings.items():
        t = des.mean_by(df[outcome], g)
        t.insert(0, "dimension", gname)
        t.insert(0, "outcome", outcome)
        gap_rows.append(t)
        for _, r in t.iterrows():
            results[f"by.{outcome}.{gname}.{r['group']}"] = r["est"]
gaps = pd.concat(gap_rows, ignore_index=True)
gaps.to_csv(OUT / "05_gaps_by_group.csv", index=False)

# =============================================================================
# 6. Models
# =============================================================================
const = pd.Series(1.0, index=df.index, name="(Intercept)")
fe = ["sector_othmfg", "sector_retail", "sector_hotels", "sector_othserv",
      "region_ashanti", "region_western", "region_northern"]

# M1: what predicts holding a loan or credit line?  (PART 5: capabilities)
x1 = ["size_medium", "size_large"] + fe + ["female_mgr", "young_firm", "exporter",
                                           "audited", "website", "innovator"]
X1 = pd.concat([const, df[x1]], axis=1)
m1 = des.glm("has_credit", X1, family="logit")
m1.to_csv(OUT / "06_model_has_credit_logit.csv", index=False)
print("\nM1 has_credit logit (n=%d)\n" % m1.attrs["n_used"],
      m1[["term", "odds_ratio", "or_lo", "or_hi", "p_value"]].round(3).to_string(index=False))

# M2: is credit associated with faster job growth?  (PART 3: jobs)
x2 = ["has_credit", "base_size_medium", "base_size_large"] + fe + ["female_mgr", "exporter", "log_age"]
X2 = pd.concat([const, df[x2]], axis=1)
m2 = des.glm("emp_growth", X2, family="linear")
m2.to_csv(OUT / "07_model_emp_growth_ols.csv", index=False)
print("\nM2 employment growth OLS (n=%d)\n" % m2.attrs["n_used"],
      m2[["term", "estimate", "lo", "hi", "p_value"]].round(3).to_string(index=False))

emp_by_credit = des.mean_by(df["emp_growth"], df["has_credit"].map({1.0: "Has loan/credit line", 0.0: "No loan/credit line"}))
emp_by_credit.to_csv(OUT / "07b_emp_growth_by_credit.csv", index=False)
results["mean.emp_growth"] = des.mean(df["emp_growth"])["est"]
for _, r in emp_by_credit.iterrows():
    results[f"emp_growth.{r['group']}"] = r["est"]

for name, m in [("m1", m1), ("m2", m2)]:
    for _, r in m.iterrows():
        results[f"{name}.coef.{r['term']}"] = r["estimate"]
        results[f"{name}.se.{r['term']}"] = r["se"]
    results[f"{name}.n"] = m.attrs["n_used"]

(OUT / "results_python.json").write_text(json.dumps(results, indent=2, default=float))

# =============================================================================
# 7. Charts  (static, for the note and slides)
# =============================================================================
BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#c9c8c2"
INK, INK2 = "#0b0b0b", "#52514e"
SRC = "Source: World Bank Enterprise Survey, Ghana 2023 (n = 713). Weighted estimates; author's calculations."
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GREY,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK,
                     "axes.spines.top": False, "axes.spines.right": False})


def finish(fig, ax, title, subtitle, path):
    fig.text(0.01, 0.97, title, fontsize=13, fontweight="bold", color=INK, va="top")
    fig.text(0.01, 0.905, subtitle, fontsize=9.5, color=INK2, va="top")
    fig.text(0.01, 0.015, SRC, fontsize=7.5, color=INK2)
    fig.savefig(path, dpi=300, facecolor="white")
    plt.close(fig)


def hbar(ax, labels, values, colors, err=None):
    y = np.arange(len(labels))[::-1]
    ax.barh(y, values, color=colors, height=0.62, xerr=err,
            error_kw={"ecolor": INK2, "elinewidth": 0.8, "capsize": 0})
    ax.set_yticks(y, labels)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, decimals=0))
    ax.grid(axis="x", color="#ecebe7", lw=0.6)
    ax.set_axisbelow(True)
    return y


# Fig 1 - biggest obstacle
top = obs.head(7)
fig, ax = plt.subplots(figsize=(8, 4.4))
fig.subplots_adjust(left=0.24, right=0.95, top=0.80, bottom=0.12)
cols = [BLUE if c == "Access to finance" else GREY for c in top["category"]]
y = hbar(ax, top["category"], top["est"], cols)
for yi, v in zip(y, top["est"]):
    ax.text(v + 0.01, yi, f"{v:.0%}", va="center", fontsize=9, color=INK)
finish(fig, ax, "Access to finance is Ghanaian firms' top obstacle",
       f"Share of firms naming each as their single biggest obstacle  ·  finance is {obs.iloc[0]['est']/obs.iloc[1]['est']:.1f}× the next",
       OUT / "fig1_biggest_obstacle.png")

# Fig 2 - credit funnel
fig, ax = plt.subplots(figsize=(8, 4.2))
fig.subplots_adjust(left=0.26, right=0.95, top=0.80, bottom=0.12)
cols = [GREY, GREY, BLUE, ORANGE, ORANGE]
y = hbar(ax, funnel["stage"], funnel["est"], cols)
ax.set_xlim(0, 1.12)
for yi, v in zip(y, funnel["est"]):
    ax.text(v + 0.01, yi, f"{v:.0%}", va="center", fontsize=9, color=INK)
gap = results["mean.needs_credit"] - results["mean.applied"]
finish(fig, ax, "Most firms that need credit never apply for it",
       f"Weighted share of all firms at each stage  ·  {gap:.0%} of firms need credit but did not apply",
       OUT / "fig2_credit_funnel.png")

# Fig 3 - reasons among discouraged borrowers
rd = reasons_disc[reasons_disc["category"] != "Other"]
fig, ax = plt.subplots(figsize=(8, 3.8))
fig.subplots_adjust(left=0.30, right=0.95, top=0.78, bottom=0.14)
cols = [ORANGE if c == "Unfavourable interest rates" else GREY for c in rd["category"]]
y = hbar(ax, rd["category"], rd["est"], cols)
for yi, v in zip(y, rd["est"]):
    ax.text(v + 0.01, yi, f"{v:.0%}", va="center", fontsize=9, color=INK)
finish(fig, ax, "The cost of credit, not collateral, keeps firms away",
       "Main reason for not applying, among firms that need credit but did not apply",
       OUT / "fig3_reasons_discouraged.png")

# Fig 4 - who is excluded (dot + CI, two outcomes side by side)
order = [("Firm size", "Small"), ("Firm size", "Medium"), ("Firm size", "Large"),
         ("Top manager", "Male"), ("Top manager", "Female"),
         ("Firm age", "Established (6+ yrs)"), ("Firm age", "Young (0-5 yrs)")]
fig, axes = plt.subplots(1, 2, figsize=(9, 4.6), sharey=True)
fig.subplots_adjust(left=0.22, right=0.97, top=0.78, bottom=0.12, wspace=0.12)
for ax, outcome, title in [(axes[0], "has_credit", "Hold a loan or credit line"),
                           (axes[1], "discouraged", "Discouraged (of firms needing credit)")]:
    sub = gaps[gaps.outcome == outcome].set_index(["dimension", "group"])
    yy = np.arange(len(order))[::-1]
    for yi, key in zip(yy, order):
        r = sub.loc[key]
        ax.plot([r["lo"], r["hi"]], [yi, yi], color=GREY, lw=2, solid_capstyle="round")
        ax.plot(r["est"], yi, "o", color=BLUE, ms=7, mec="white", mew=1.5)
        ax.text(r["est"], yi + 0.28, f"{r['est']:.0%}", ha="center", fontsize=8, color=INK)
    for b in [3.5, 1.5]:
        ax.axhline(b, color="#ecebe7", lw=0.8)
    ax.set_ylim(-0.6, len(order) - 0.2)
    ax.set_yticks(yy, [k[1] for k in order])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1, decimals=0))
    ax.set_title(title, fontsize=10, color=INK, loc="left", pad=10)
finish(fig, axes[0], "Small firms are least likely to hold credit",
       "Weighted share with 95% confidence interval, by firm group",
       OUT / "fig4_who_is_excluded.png")

# Fig 5 - credit and jobs (dot + 95% CI)
fig, ax = plt.subplots(figsize=(8, 3.4))
fig.subplots_adjust(left=0.24, right=0.95, top=0.72, bottom=0.20)
e = emp_by_credit.set_index("group").loc[["Has loan/credit line", "No loan/credit line"]]
yy = np.array([1, 0])
for yi, (g, r) in zip(yy, e.iterrows()):
    ax.plot([r["lo"], r["hi"]], [yi, yi], color=GREY, lw=2.5, solid_capstyle="round")
    ax.plot(r["est"], yi, "o", color=BLUE if yi == 1 else INK2, ms=8, mec="white", mew=1.5)
    ax.text(r["est"], yi + 0.2, f"{r['est']:.1f}%", ha="center", fontsize=9, color=INK)
ax.set_yticks(yy, e.index)
ax.set_ylim(-0.5, 1.6)
ax.set_xlim(0, 20)
ax.tick_params(axis="y", length=0)
ax.spines["left"].set_visible(False)
ax.set_xlabel("Annualised employment growth, last 3 years (%)")
ax.grid(axis="x", color="#ecebe7", lw=0.6)
ax.set_axisbelow(True)
b = m2.set_index("term").loc["has_credit"]
finish(fig, ax, "Credit holders added jobs faster, but the gap is not significant",
       f"Mean annual employment growth with 95% CI  ·  gap after controls: {b['estimate']:+.1f} pp (95% CI {b['lo']:.1f} to {b['hi']:+.1f})",
       OUT / "fig5_credit_and_jobs.png")

print("\nDone. Outputs in", OUT.resolve())
