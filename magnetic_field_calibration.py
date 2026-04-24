#!/usr/bin/env python3
"""
pick_most_efficient_field.py

Load GMR calibration data (Excel or CSV), smooth V(B), compute dV/dB,
find the magnetic field with maximum sensitivity and a sensitive range.

Usage:
    python pick_most_efficient_field.py
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from openpyxl import Workbook
import openpyxl

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    _HAS_TK = True
except Exception:
    _HAS_TK = False

# Optional: use Savitzky-Golay if SciPy is installed
try:
    from scipy.signal import savgol_filter
    _HAS_SAVGOL = True
except Exception:
    _HAS_SAVGOL = False

# ---------- User settings ----------
FILE_PATH = None
SHEET_NAME = None   # set if needed, or None to use first sheet
COL_B = "B"    # column name for magnetic field (adjust if different)
COL_V = "V_chip-avg"  # column name for voltage
SMOOTH_METHOD = "savgol" if _HAS_SAVGOL else "moving_average"
SAVGOL_WINDOW = 5   # must be odd and <= n_points
SAVGOL_POLY = 2
MA_WINDOW = 5       # moving average window (odd recommended)
SENS_THRESH_RATIO = 0.5   # threshold for sensitive range (50% of peak)
PLOT_AND_SAVE = True
OUT_PLOT = "gmr_sensitivity.png"
# -----------------------------------

def _select_input_file(initialdir=None):
    if not _HAS_TK:
        raise RuntimeError("Tkinter is not available for GUI file selection")
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_path = filedialog.askopenfilename(
        title="Select Excel or CSV input file",
        initialdir=initialdir or os.path.expanduser("~"),
        filetypes=[
            ("Excel files", "*.xlsx *.xls"),
            ("CSV files", "*.csv"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()
    return file_path


def _select_output_file(default_name="gmr_sensitivity.png", initialdir=None):
    if not _HAS_TK:
        raise RuntimeError("Tkinter is not available for GUI file selection")
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.asksaveasfilename(
        title="Choose location for output plot and related files",
        initialdir=initialdir or os.path.expanduser("~"),
        initialfile=default_name,
        defaultextension=".png",
        filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
    )
    root.destroy()
    return path


def _read_table(path: str, sheet_name=None):
    """
    Read Excel or CSV robustly.
    If pd.read_excel returns a dict (multiple sheets), pick the requested sheet_name
    or fall back to the first sheet and announce it.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Try Excel first
    try:
        df_or_dict = pd.read_excel(p, sheet_name=sheet_name, engine="openpyxl")
        # If Excel returned a dict of sheets, choose the right one
        if isinstance(df_or_dict, dict):
            if sheet_name is None:
                first_sheet = list(df_or_dict.keys())[0]
                print(f"Note: Excel has multiple sheets — using first sheet: '{first_sheet}'")
                df = df_or_dict[first_sheet]
            else:
                # sheet_name requested; ensure it exists
                if sheet_name in df_or_dict:
                    df = df_or_dict[sheet_name]
                else:
                    # try numeric index
                    try:
                        df = list(df_or_dict.values())[int(sheet_name)]
                        print(f"Using sheet at index {sheet_name}")
                    except Exception:
                        raise KeyError(f"Requested sheet '{sheet_name}' not found in Excel file.")
        else:
            df = df_or_dict
    except Exception as excel_err:
        # fallback: try CSV
        try:
            print("Failed to read as Excel (or openpyxl missing). Trying CSV...")
            df = pd.read_csv(p)
        except Exception as csv_err:
            raise RuntimeError("Failed to read file as Excel or CSV") from excel_err

    return df

def normalize_numeric_column(series: pd.Series):
    """
    Convert column to numeric robustly: handle commas as decimal separators
    and stray spaces. Returns a float numpy array.
    """
    s = series.astype(str).str.strip().str.replace(" ", "")
    # If commas are present and no dots, assume comma decimal separator
    if s.str.contains(",").any() and not s.str.contains(r"\.").any():
        s = s.str.replace(",", ".")
    # remove thousands separators (if any): e.g. '1,234.56' or '1.234,56'
    # this is a best-effort approach; keep it simple
    s = s.str.replace(r"[^\d\.\-eE]", "", regex=True)
    return pd.to_numeric(s, errors="coerce").values

def smooth_signal(x: np.ndarray, method="savgol", window=5, poly=2):
    n = x.size
    if n == 0:
        return x
    if method == "savgol" and _HAS_SAVGOL:
        # ensure window is odd and <= n
        w = int(window)
        if w >= n:
            w = n - (1 - n % 2)  # largest odd < n
            if w < 1: w = 1
        if w % 2 == 0:
            w -= 1
            if w < 1: w = 1
        p = min(int(poly), w - 1) if w > 1 else 0
        if p < 0: p = 0
        if w <= 1:
            return x.copy()
        return savgol_filter(x, window_length=w, polyorder=p, mode="interp")
    else:
        # moving average fallback - centered
        w = int(window)
        if w < 1: w = 1
        if w == 1:
            return x.copy()
        pad = w // 2
        xp = np.pad(x, pad, mode="reflect")
        kernel = np.ones(w) / w
        smooth = np.convolve(xp, kernel, mode="valid")
        return smooth

def find_peak_and_range(B: np.ndarray, V: np.ndarray, smooth_method=SMOOTH_METHOD,
                        savgol_w=SAVGOL_WINDOW, savgol_p=SAVGOL_POLY,
                        ma_w=MA_WINDOW, thresh_ratio=SENS_THRESH_RATIO):
    # sort by B (just in case)
    order = np.argsort(B)
    B = B[order]
    V = V[order]

    # smooth V
    if smooth_method == "savgol" and _HAS_SAVGOL:
        Vsm = smooth_signal(V, method="savgol", window=savgol_w, poly=savgol_p)
    else:
        Vsm = smooth_signal(V, method="ma", window=ma_w)

    # numerical derivative dV/dB
    # guard against zero spacing
    dB = np.gradient(B)
    # If any dB is zero, numpy.gradient may produce inf/nan; handle by small eps
    dB_safe = np.where(np.isclose(dB, 0), 1e-12, dB)
    dVdB = np.gradient(Vsm, B)  # numpy handles gradient with x
    # handle NaN
    dVdB = np.nan_to_num(dVdB, nan=0.0, posinf=0.0, neginf=0.0)

    # find peak sensitivity
    imax = int(np.argmax(dVdB))
    B_peak = float(B[imax])
    V_at_peak = float(Vsm[imax])
    dVdB_peak = float(dVdB[imax])

    threshold = thresh_ratio * dVdB_peak
    indices = np.where(dVdB >= threshold)[0]
    if indices.size > 0:
        B_min = float(B[indices[0]])
        B_max = float(B[indices[-1]])
    else:
        B_min = B_peak
        B_max = B_peak

    return {
        "B_peak_mT": B_peak,
        "V_at_peak_V": V_at_peak,
        "dVdB_peak_V_per_mT": dVdB_peak,
        "sensitive_range_mT": (B_min, B_max),
        "B": B,
        "V": V,
        "V_smooth": Vsm,
        "dVdB": dVdB,
    }

def to_oe(mT):
    # 1 mT ≈ 10 Oe (approx, in air)
    return np.array(mT) * 10.0

def plot_results(res, out_file=None, show=True):
    B = res["B"]
    V = res["V"]
    Vsm = res["V_smooth"]
    dVdB = res["dVdB"]
    B_peak = res["B_peak_mT"]
    dVdB_peak = res["dVdB_peak_V_per_mT"]
    B_min, B_max = res["sensitive_range_mT"]

    fig, ax = plt.subplots(2, 1, figsize=(8, 7), gridspec_kw={"height_ratios": [2, 1]})
    # Top: V vs B
    ax[0].scatter(B, V, label="Raw V", zorder=3)
    ax[0].plot(B, Vsm, label="Smoothed V", linewidth=1.5, zorder=4)
    ax[0].axvline(B_peak, color="C1", linestyle="--", label=f"Peak at {B_peak:.2f} mT")
    ax[0].fill_betweenx([min(Vsm)*0.99, max(Vsm)*1.01], B_min, B_max, color="C1", alpha=0.12,
                        label=f"Sensitive range {B_min:.2f}-{B_max:.2f} mT")
    ax[0].set_xlabel("Magnetic Field B (mT)")
    ax[0].set_ylabel("V_chip_avg (V)")
    ax[0].legend(loc="best")
    ax[0].grid(True, linestyle=":", alpha=0.3)

    # Bottom: derivative
    ax[1].plot(B, dVdB, label="dV/dB")
    ax[1].scatter([B_peak], [dVdB_peak], s=70, zorder=4, label=f"Peak dV/dB={dVdB_peak:.4f} V/mT")
    ax[1].axhline(0.5 * dVdB_peak, linestyle=":", label="50% peak")
    ax[1].set_xlabel("Magnetic Field B (mT)")
    ax[1].set_ylabel("dV/dB (V per mT)")
    ax[1].legend(loc="best")
    ax[1].grid(True, linestyle=":", alpha=0.3)

    plt.tight_layout()
    if out_file:
        fig.savefig(out_file, dpi=300)
        print(f"Saved plot to {out_file}")
    if show:
        plt.show()
    plt.close(fig)

def plot_v_vs_b_with_regression(B, V, out_file=None, show=True):
    """
    Plot V_chip-avg (x) vs B (y) with regression line and equation.
    """
    import matplotlib.pyplot as plt
    from numpy.polynomial.polynomial import Polynomial
    # Linear regression: B = a*V + b
    p = np.polyfit(V, B, 1)
    B_fit = np.polyval(p, V)
    eqn = f"B = {p[0]:.4f}*V + {p[1]:.4f}"
    fig, ax = plt.subplots(figsize=(7,5))
    ax.scatter(V, B, label="Data", color="C0")
    ax.plot(V, B_fit, color="C1", label=f"Fit: {eqn}")
    ax.set_xlabel("V_chip-avg (V)")
    ax.set_ylabel("B (mT)")
    ax.legend(loc="best")
    ax.grid(True, linestyle=":", alpha=0.3)
    # Annotate equation
    ax.text(0.05, 0.95, eqn, transform=ax.transAxes, fontsize=11, va="top", ha="left",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.7))
    plt.tight_layout()
    if out_file:
        fig.savefig(out_file, dpi=300)
        print(f"Saved V_vs_B regression plot to {out_file}")
    if show:
        plt.show()
    plt.close(fig)
    return p, eqn

def main():
    if FILE_PATH is None:
        if not _HAS_TK:
            print("Error: Tkinter GUI is unavailable and no FILE_PATH is configured.")
            sys.exit(1)
        selected = _select_input_file()
        if not selected:
            print("No input file selected. Exiting.")
            sys.exit(0)
        file_path = selected
    else:
        file_path = FILE_PATH

    print("Loading data from:", file_path)
    try:
        df = _read_table(file_path, sheet_name=SHEET_NAME)
    except Exception as e:
        print("Error reading file:", e)
        sys.exit(1)

    # Try to find the right columns; if exact names not found, list candidates
    cols = df.columns.tolist()
    if COL_B not in cols or COL_V not in cols:
        print("Warning: expected column names not present. Attempting auto-detect.")
        # find columns that contain 'mT' or 'B' for B, and 'V' or 'chip' for V
        cand_B = [c for c in cols if ("mT" in str(c) or "B" in str(c) or "Magnetic" in str(c))]
        cand_V = [c for c in cols if ("V" in str(c) or "chip" in str(c) or "Voltage" in str(c))]
        if cand_B:
            col_b = cand_B[0]
        else:
            col_b = cols[0]
        if cand_V:
            col_v = cand_V[0]
        else:
            col_v = cols[-1]
        print("Using columns:", col_b, "for B and", col_v, "for V")
    else:
        col_b = COL_B
        col_v = COL_V

    B = normalize_numeric_column(df[col_b])
    V = normalize_numeric_column(df[col_v])

    # Remove NaN rows
    mask = ~(np.isnan(B) | np.isnan(V))
    B = B[mask]
    V = V[mask]
    if B.size == 0:
        print("No numeric data found in selected columns.")
        sys.exit(1)

    res = find_peak_and_range(B, V,
                              smooth_method=SMOOTH_METHOD,
                              savgol_w=SAVGOL_WINDOW, savgol_p=SAVGOL_POLY,
                              ma_w=MA_WINDOW, thresh_ratio=SENS_THRESH_RATIO)

    # Print results
    print("\n=== Sensitivity result ===")
    print(f"Peak sensitivity at B = {res['B_peak_mT']:.4f} mT  ({to_oe(res['B_peak_mT']):.3f} Oe)")
    print(f"Sensor voltage at peak: {res['V_at_peak_V']:.6f} V")
    print(f"Peak slope (dV/dB): {res['dVdB_peak_V_per_mT']:.6f} V/mT  ({res['dVdB_peak_V_per_mT'] / 10.0:.6f} V/Oe)")
    bmin, bmax = res['sensitive_range_mT']
    print(f"Sensitive range (≥{int(SENS_THRESH_RATIO*100)}% peak): {bmin:.4f} – {bmax:.4f} mT  ({to_oe(bmin):.2f} – {to_oe(bmax):.2f} Oe)")

    if PLOT_AND_SAVE:
        if not _HAS_TK:
            print("Error: Tkinter GUI is unavailable and output save dialog is required.")
            sys.exit(1)
        selected_output = _select_output_file(default_name=OUT_PLOT, initialdir=str(Path(file_path).parent))
        if not selected_output:
            print("No output location selected. Exiting.")
            sys.exit(0)
        output_plot_path = Path(selected_output)
        if output_plot_path.suffix == "":
            output_plot_path = output_plot_path.with_suffix(".png")
        output_dir = output_plot_path.parent
        output_prefix = output_plot_path.stem

        plot_results(res, out_file=str(output_plot_path), show=True)

        # --- Plot V_chip-avg vs B with regression ---
        reg_plot_file = output_dir / f"{output_prefix}_regression.png"
        p, eqn = plot_v_vs_b_with_regression(B, V, out_file=str(reg_plot_file), show=True)

        # --- Save all calibration data to Excel ---
        excel_report = output_dir / f"{output_prefix}_report.xlsx"
        df_report = pd.DataFrame({
            "B_mT": B,
            "V_chip-avg_V": V,
            "V_smooth_V": res["V_smooth"],
            "dVdB_V_per_mT": res["dVdB"]
        })
        # Add regression fit column
        df_report["B_fit_from_V"] = np.polyval(p, V)
        # Save regression coefficients and equation in a separate sheet
        with pd.ExcelWriter(excel_report, engine="openpyxl") as writer:
            df_report.to_excel(writer, index=False, sheet_name="Calibration Data")
            # Regression info
            df_reg = pd.DataFrame({"Regression": [eqn], "Slope": [p[0]], "Intercept": [p[1]]})
            df_reg.to_excel(writer, index=False, sheet_name="Regression Info")
        print(f"Saved calibration data and regression info to {excel_report}")

if __name__ == "__main__":
    main()
