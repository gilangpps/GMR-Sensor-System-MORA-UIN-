# -*- coding: utf-8 -*-
"""
Training + Evaluation untuk dataset GMR:
- Dataset utama: GMR_DataProcessing_24092025.xlsx
- Model: Random Forest (utama, dipakai di GUI), Linear Regression, SVR
- Output: 
  * rf_model.joblib (final model)
  * linreg_model.joblib, svr_model.joblib (model pembanding)
  * rf_metrics.csv (per fold + ringkasan evaluasi)
  * berbagai visualisasi (parity, residuals, barplot, calibration curve)
"""

from __future__ import annotations
from pathlib import Path
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split, KFold, cross_val_score
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.linear_model import LinearRegression
from sklearn.svm import SVR
from sklearn.ensemble import RandomForestRegressor
import joblib

# ------------------ Konfigurasi ------------------
DATASET  = "GMR_DataProcessing_10102025.xlsx"
SHEET    = 0
OUTDIR   = Path("10102025gmr_rf_out")
TESTSIZE = 0.20
RANDOM   = 42
KFOLD    = 5
# -------------------------------------------------

# ————— Utilitas parsing label konsentrasi —————
CONC_PAT = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*(?:mg/?mL|mg\s*/\s*mL|mgmL)", re.I)

def parse_concentration(label: str) -> float | None:
    if label is None:
        return None
    m = CONC_PAT.search(str(label))
    if not m:
        return None
    val = m.group(1).replace(",", ".")
    try:
        return float(val)
    except ValueError:
        return None

def detect_columns(df: pd.DataFrame) -> tuple[str, dict[float, list[str]]]:
    cols = list(df.columns)
    time_col = cols[0]
    for c in cols[:3]:
        if re.search(r"time|waktu", str(c), re.I):
            time_col = c
            break

    conc_map: dict[float, list[str]] = {}
    for c in cols:
        if c == time_col:
            continue
        conc = parse_concentration(str(c))
        if conc is not None:
            conc_map.setdefault(conc, []).append(c)

    if not conc_map:
        raise ValueError("Tidak menemukan kolom konsentrasi dengan pola '<angka> mg/mL'.")
    return time_col, conc_map

# ————— Load & reshape ke long-format —————
def load_long_dataframe(xlsx_path: Path, sheet=0) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, sheet_name=sheet)
    time_col, conc_map = detect_columns(df)

    if df[time_col].dtype == object:
        df[time_col] = pd.to_numeric(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col])

    long_rows = []
    for conc, cols in conc_map.items():
        sub = df[cols].copy()
        for c in cols:
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
        v_mean = sub.mean(axis=1, skipna=True)
        tmp = pd.DataFrame({
            "time_s": df[time_col].values,
            "signal_V": v_mean.values,
            "concentration_mg_per_mL": conc,
        }).dropna(subset=["signal_V"])
        long_rows.append(tmp)

    return pd.concat(long_rows, ignore_index=True)

# ————— Training, evaluasi & plotting —————
def train_and_evaluate(long_df: pd.DataFrame, outdir: Path) -> pd.DataFrame:
    outdir.mkdir(parents=True, exist_ok=True)

    X = long_df[["signal_V"]].values
    y = long_df["concentration_mg_per_mL"].values

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=TESTSIZE, random_state=RANDOM, shuffle=True
    )

    models = {
        "LinearRegression": LinearRegression(),
        "SVR(RBF)": SVR(kernel="rbf", C=10.0, epsilon=1e-3, gamma="scale"),
        "RandomForest": RandomForestRegressor(n_estimators=300, random_state=RANDOM),
    }

    kf = KFold(n_splits=KFOLD, shuffle=True, random_state=RANDOM)
    metrics_rows = {}
    preds = {}

    for name, mdl in models.items():
        mdl.fit(X_tr, y_tr)
        y_pred = mdl.predict(X_te)

        # evaluasi holdout
        r2  = r2_score(y_te, y_pred)
        mse = mean_squared_error(y_te, y_pred)
        mae = mean_absolute_error(y_te, y_pred)

        # evaluasi CV
        cv_r2 = cross_val_score(mdl, X, y, cv=kf, scoring="r2")

        metrics_rows[name] = {
            "Holdout_R2": r2,
            "Holdout_MSE": mse,
            "Holdout_MAE": mae,
            "CV5_R2_mean": cv_r2.mean(),
            "CV5_R2_std":  cv_r2.std(),
        }
        preds[name] = (y_te, y_pred)

        # simpan model
        fname = outdir / f"{name.replace('(','_').replace(')','')}_model.joblib"
        joblib.dump(mdl, fname)

    # buat dataframe metrik
    metrics_df = pd.DataFrame(metrics_rows).T.reset_index().rename(columns={"index": "Model"})
    metrics_df.to_csv(outdir / "rf_metrics.csv", index=False)

    # print ke console
    print("=== Evaluasi Model (Holdout + 5-fold CV) ===")
    for name, row in metrics_rows.items():
        print(f"[{name}] R²={row['Holdout_R2']:.4f}, MSE={row['Holdout_MSE']:.6f}, MAE={row['Holdout_MAE']:.6f}, CV_R²={row['CV5_R2_mean']:.4f}±{row['CV5_R2_std']:.4f}")
    print(f"\nArtefak tersimpan di: {outdir.resolve()}")

    # --- Plot perbandingan (barplot) + labels ---
    for metric, label, fname in [
        ("Holdout_R2", "Holdout R²", "cmp_R2.png"),
        ("Holdout_MSE", "Holdout MSE", "cmp_MSE.png"),
        ("Holdout_MAE", "Holdout MAE", "cmp_MAE.png"),
    ]:
        plt.figure(figsize=(7,5))
        vals = metrics_df[metric].values
        plt.bar(metrics_df["Model"], vals)
        for i, v in enumerate(vals):
            plt.text(i, v, f"{v:.4f}", ha="center", va="bottom", fontsize=9)
        plt.ylabel(label)
        plt.title(f"Model Comparison – {label}")
        plt.grid(True, axis="y", ls="--", alpha=0.4)
        plt.tight_layout(); plt.savefig(outdir / fname, dpi=200); plt.close()

    # --- Parity & residual plot per model ---
    for name, (yt, yp) in preds.items():
        # parity
        plt.figure(figsize=(6,6))
        lims = [min(yt.min(), yp.min()), max(yt.max(), yp.max())]
        plt.scatter(yt, yp, alpha=0.8)
        for xi, yi in zip(yt, yp):
            plt.text(xi, yi, f"{yi:.2f}", fontsize=8, alpha=0.6)
        plt.plot(lims, lims, "k--", lw=1, label="Ideal (y=x)")
        plt.xlabel("True Conc. (mg/mL)")
        plt.ylabel("Predicted (mg/mL)")
        plt.title(f"Parity Plot – {name}")
        plt.legend()
        plt.grid(True, ls="--", alpha=0.5)
        plt.tight_layout(); plt.savefig(outdir / f"parity_{name}.png", dpi=200); plt.close()

        # residuals
        res = yt - yp
        plt.figure(figsize=(7,5))
        plt.scatter(yp, res, alpha=0.8)
        for xi, yi in zip(yp, res):
            plt.text(xi, yi, f"{yi:.2f}", fontsize=8, alpha=0.6)
        plt.axhline(0, color="k", lw=1)
        plt.xlabel("Predicted (mg/mL)")
        plt.ylabel("Residual (y_true - y_pred)")
        plt.title(f"Residuals – {name}")
        plt.grid(True, ls="--", alpha=0.5)
        plt.tight_layout(); plt.savefig(outdir / f"residuals_{name}.png", dpi=200); plt.close()

    # --- Calibration curve (mean signal per concentration) ---
    summary = (
        long_df.groupby("concentration_mg_per_mL")["signal_V"]
        .agg(["mean", "std", "count"]).reset_index()
        .sort_values("concentration_mg_per_mL")
    )
    lin = LinearRegression().fit(summary[["mean"]], summary["concentration_mg_per_mL"])
    xs = summary["mean"].values
    x_line = np.linspace(xs.min()*0.99, xs.max()*1.01, 200).reshape(-1,1)
    y_line = lin.predict(x_line)

    plt.figure(figsize=(8,5))
    plt.scatter(summary["mean"], summary["concentration_mg_per_mL"], s=60, label="Mean per conc.")
    for xi, yi in zip(summary["mean"], summary["concentration_mg_per_mL"]):
        plt.text(xi, yi, f"{yi:.2f}", fontsize=8, alpha=0.7)
    plt.plot(x_line, y_line, label=f"C = {lin.intercept_:.4f} + {lin.coef_[0]:.4f} * V_mean")
    plt.xlabel("Mean Signal V (V)")
    plt.ylabel("Concentration (mg/mL)")
    plt.title("Calibration Curve")
    plt.legend(); plt.grid(True, ls="--", alpha=0.5)
    plt.tight_layout(); plt.savefig(outdir / "calibration_curve.png", dpi=200); plt.close()

    return metrics_df

# ————— Main —————
def main():
    xlsx = Path(DATASET)
    if not xlsx.exists():
        raise FileNotFoundError(f"Tidak menemukan file: {xlsx.resolve()}")
    long_df = load_long_dataframe(xlsx, sheet=SHEET)
    metrics_df = train_and_evaluate(long_df, OUTDIR)

if __name__ == "__main__":
    main()
