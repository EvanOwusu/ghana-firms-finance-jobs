"""
Design-based estimation for a stratified, single-stage survey (each firm is its own PSU),
following the Taylor-linearisation approach used by R's `survey` package with
options(survey.lonely.psu = "adjust").

Why hand-rolled: the World Bank Enterprise Surveys use a stratified design, so
standard errors must account for strata. This module reproduces R's
svymean / svyglm variance formulas so the Python and R pipelines can be checked
against each other.

Conventions (matching R `survey`):
  * Rows outside a domain, or with missing values, keep their stratum membership
    but contribute zero to the estimating equations (domain estimation).
  * Stratum PSU counts n_h always come from the full sample.
  * Strata with a single PSU ("lonely PSUs") are centred on the grand mean and
    contribute with scale 1.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


class StratifiedDesign:
    def __init__(self, df: pd.DataFrame, weight: str, strata: str):
        self.df = df.reset_index(drop=True)
        self.w = self.df[weight].astype(float).to_numpy()
        self.strata = self.df[strata].to_numpy()
        codes, self._sidx = np.unique(self.strata, return_inverse=True)
        self.n_strata = len(codes)
        self.n_h = np.bincount(self._sidx)                # PSUs per stratum (full sample)
        self.n = len(self.df)
        self.df_resid = self.n - self.n_strata             # design degrees of freedom

    # ---- core variance of a total of influence values ------------------------
    def _var_total(self, z: np.ndarray) -> np.ndarray:
        """Linearised variance of sum(z) under the stratified design.
        z: (n,) or (n, p) array of weighted influence values (0 outside domain)."""
        z = np.atleast_2d(z.T).T if z.ndim == 1 else z
        p = z.shape[1]
        grand = z.mean(axis=0)
        V = np.zeros((p, p))
        sums = np.zeros((self.n_strata, p))
        np.add.at(sums, self._sidx, z)
        means = sums / self.n_h[:, None]
        for h in range(self.n_strata):
            zh = z[self._sidx == h]
            if self.n_h[h] > 1:
                d = zh - means[h]
                V += self.n_h[h] / (self.n_h[h] - 1) * d.T @ d
            else:                                         # lonely PSU: centre on grand mean
                d = zh - grand
                V += d.T @ d
        return V

    # ---- weighted mean (proportion) with 95% CI ---------------------------------
    def mean(self, y: pd.Series | np.ndarray, domain: np.ndarray | None = None) -> dict:
        y = np.asarray(y, dtype=float)
        ok = ~np.isnan(y)
        if domain is not None:
            ok &= np.asarray(domain, dtype=bool)
        w = np.where(ok, self.w, 0.0)
        yv = np.where(ok, y, 0.0)
        W = w.sum()
        est = (w * yv).sum() / W
        z = w * (yv - est) / W
        se = float(np.sqrt(self._var_total(z)[0, 0]))
        q = stats.norm.ppf(0.975)
        return {"est": est, "se": se, "lo": est - q * se, "hi": est + q * se,
                "n": int(ok.sum())}

    def mean_by(self, y, by: pd.Series, domain=None) -> pd.DataFrame:
        rows = []
        for level in sorted(pd.Series(by).dropna().unique()):
            dom = (np.asarray(by) == level)
            if domain is not None:
                dom &= np.asarray(domain, dtype=bool)
            r = self.mean(y, dom)
            r["group"] = level
            rows.append(r)
        return pd.DataFrame(rows)[["group", "est", "se", "lo", "hi", "n"]]

    def shares(self, cat: pd.Series, domain=None) -> pd.DataFrame:
        """Weighted distribution of a categorical variable (like svymean(~factor))."""
        cat = pd.Series(cat).reset_index(drop=True)
        ok = cat.notna().to_numpy().copy()
        if domain is not None:
            ok &= np.asarray(domain, dtype=bool)
        rows = []
        for level in cat[ok].unique():
            ind = np.where(ok, (cat == level).astype(float), np.nan)
            r = self.mean(ind)
            r["category"] = level
            rows.append(r)
        return (pd.DataFrame(rows)[["category", "est", "se", "lo", "hi", "n"]]
                .sort_values("est", ascending=False).reset_index(drop=True))

    # ---- survey-weighted GLM (logit or linear) ---------------------------------
    def glm(self, y: str, X: pd.DataFrame, family: str = "logit") -> pd.DataFrame:
        yv = self.df[y].astype(float).to_numpy()
        Xm = X.astype(float).to_numpy()
        ok = ~np.isnan(yv) & ~np.isnan(Xm).any(axis=1)
        w = np.where(ok, self.w, 0.0)
        yv = np.where(ok, yv, 0.0)
        Xm = np.where(ok[:, None], Xm, 0.0)

        if family == "linear":
            A = Xm.T @ (w[:, None] * Xm)
            beta = np.linalg.solve(A, Xm.T @ (w * yv))
            resid = yv - Xm @ beta
            scores = (w * resid)[:, None] * Xm
        else:                                             # logit via IRLS
            beta = np.zeros(Xm.shape[1])
            for _ in range(100):
                p = 1 / (1 + np.exp(-(Xm @ beta)))
                Wt = w * p * (1 - p)
                A = Xm.T @ (Wt[:, None] * Xm)
                step = np.linalg.solve(A, Xm.T @ (w * (yv - p)))
                beta += step
                if np.max(np.abs(step)) < 1e-10:
                    break
            p = 1 / (1 + np.exp(-(Xm @ beta)))
            A = Xm.T @ ((w * p * (1 - p))[:, None] * Xm)
            scores = (w * (yv - p))[:, None] * Xm

        Ainv = np.linalg.inv(A)
        V = Ainv @ self._var_total(scores) @ Ainv
        se = np.sqrt(np.diag(V))
        dfree = self.df_resid + 1 - Xm.shape[1]
        t = beta / se
        q = stats.t.ppf(0.975, dfree)
        out = pd.DataFrame({"term": X.columns, "estimate": beta, "se": se,
                            "t": t, "p_value": 2 * stats.t.sf(np.abs(t), dfree),
                            "lo": beta - q * se, "hi": beta + q * se})
        if family == "logit":
            out["odds_ratio"] = np.exp(out["estimate"])
            out["or_lo"] = np.exp(out["lo"])
            out["or_hi"] = np.exp(out["hi"])
        out.attrs["n_used"] = int(ok.sum())
        return out


def dummies(s: pd.Series, ref, prefix: str) -> pd.DataFrame:
    """Treatment-coded dummies, NaN-preserving, with `ref` as the omitted level."""
    levels = [l for l in pd.Series(s).dropna().unique() if l != ref]
    levels = sorted(levels, key=lambda v: str(v))
    out = pd.DataFrame({f"{prefix}{l}": (s == l).astype(float) for l in levels})
    out[s.isna().to_numpy()] = np.nan
    return out
