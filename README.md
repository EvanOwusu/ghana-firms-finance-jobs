# Finance, Firms and Jobs in Ghana

What holds back Ghana's formal private firms, who is excluded from credit, and does credit go with job creation? This repo answers those questions with the **World Bank Enterprise Survey, Ghana 2023** (713 establishments, fieldwork 2023–24). All estimates use the survey weights (`wmedian`) and the stratified design (`strata`).

## Key findings

| # | Finding | Estimate (95% CI) |
|---|---|---|
| 1 | Access to finance is the most common **biggest obstacle**, ahead of tax rates (25%) | 39% (34–45%) |
| 2 | About half of firms **need** external credit, but only 14% **applied** in the last year | 49% vs 14% |
| 3 | Of the firms that need credit, most are **discouraged** and never apply | 72% (65–80%) |
| 4 | Those who do apply are usually **approved**, so rejection is not the main barrier | 90% (80–100%) |
| 5 | **Unfavourable interest rates** are the main reason discouraged firms stay away; collateral is cited by only 8% | 64% (55–74%) |
| 6 | **Small firms** are far less likely to hold a loan or credit line than large firms | 18% vs 41% |
| 7 | Firms with credit grew employment faster (12.0% vs 8.8% a year), but the gap is **not statistically significant** after controls | +1.7 pp (−2.9 to +6.3) |
| 8 | No significant **gender gap** in credit access among formal firms; women are under-represented as top managers | 20% of firms |

**Policy reading:** in 2023 the binding finance constraint looks like the *cost* of credit, not collateral or rejection. That points toward instruments that lower the price of SME credit (refinancing lines, interest-rate risk sharing) rather than partial credit guarantees alone. The survey coincided with Ghana's 2022–23 macroeconomic crisis, so part of this may be cyclical. The jobs result is a correlation; establishing a causal effect would need an impact evaluation of a credit programme.

## Repository structure

```
python/survey.py      Design-based estimation (stratified Taylor linearisation, lonely-PSU "adjust")
python/analysis.py    Main pipeline: cleaning, estimates, models, charts
R/analysis.R          R translation using the `survey` package
verify_match.py       Checks the Python and R results agree
output/               Aggregate tables (CSV), charts (PNG), results JSON
```

## How to run

1. Register at the [Enterprise Surveys portal](https://www.enterprisesurveys.org/en/survey-datasets) and download `Ghana-2023-full-data.dta` into `data/`. (The portal file may arrive as a zip with a `.dta` name. Unzip it first.)
2. Python (pandas, numpy, scipy, matplotlib):
   `python python/analysis.py data/Ghana-2023-full-data.dta`
3. R (haven, survey, jsonlite):
   `Rscript R/analysis.R data/Ghana-2023-full-data.dta`
4. `python verify_match.py`

## Methods notes

- **Firm size** comes from permanent full-time employees: small 5–19, medium 20–99, large 100+.
- **Needs credit** means the firm applied, or didn't apply for any reason other than "no need, sufficient capital". **Discouraged** means a firm that needs credit but did not apply.
- **Employment growth** is the annualised mid-point rate over three years: (L₁ − L₀) / ((L₁ + L₀)/2) / 3. It's bounded and defined for firms that started from zero.
- **Models:** survey-weighted logit for holding credit, and survey-weighted OLS for employment growth. Both include sector and region fixed effects. Standard errors are design-based.
- Negative WBES codes (don't know, refused, does not apply) are treated as missing.

## AI-assisted workflow

I designed the analysis and built it in Python, using Claude (Anthropic) as a coding assistant. I then used Claude to translate the pipeline into R. `verify_match.py` checks that both versions reproduce the same weighted estimates and standard errors.

## Data use

The firm-level data is provided under the Enterprise Surveys confidentiality agreement. It is **not** included in this repository and must not be redistributed. Only aggregate results are reported, and no establishment is identified.

*Evans K. Owusu, PhD · owusukojoevans@gmail.com*
