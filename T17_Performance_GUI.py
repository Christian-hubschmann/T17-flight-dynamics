"""
T-17 Saab Supporter — Performance Analyse
==========================================
Standalone desktop-applikation.
Start: dobbeltklik på denne fil, eller kør: python T17_Performance_GUI.py
"""

import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install",
                       "matplotlib", "numpy", "scipy"],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.interpolate import interp1d
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading

# ══════════════════════════════════════════════════════════════════════════════
#  FARVER OG FONTE  (matcher Vaegt & Balance GUI)
# ══════════════════════════════════════════════════════════════════════════════
BG        = "#f0f0f0"
HDR       = "#1a3a5c"
SECT      = "#dce8f5"
FONT      = ("Segoe UI", 11)
FONT_MONO = ("Courier New", 10)

# ══════════════════════════════════════════════════════════════════════════════
#  FLY- OG ATMOSFAEREKONSTANTER
# ══════════════════════════════════════════════════════════════════════════════
AR   = 6.58
S    = 11.9
D    = 1.88
CD0  = 0.0492
e    = 0.74
eps  = 1.0 / (np.pi * AR * e)

V_stall_max_Weight_kn = 65

ft_to_m   = 1.0 / 3.28084
m_to_ft   = 3.28084
HP_to_W   = 745.69987
kn_to_ms  = 0.514444
ms_to_fpm = 196.8504

T0   = 288.15
p0   = 101325.0
rho0 = 1.225
L    = 0.0065
g    = 9.80665
R    = 287.05287

# Standard eta_p(J) – NASA-korrigeret
_J_STD   = [0.2,  0.3,  0.35, 0.4,  0.45, 0.48, 0.5,  0.55,
            0.6,  0.65, 0.7,  0.75, 0.8,  0.85, 0.9,  0.95, 1.0, 1.05]
_ETA_STD = [0.31, 0.45, 0.52, 0.57, 0.61, 0.64, 0.65, 0.68,
            0.71, 0.74, 0.77, 0.79, 0.80, 0.77, 0.73, 0.62, 0.42, 0.0]

# RPM-tabeller: {power_pct: RPM} – bruges til linjaer interpolation
RPM_LYCOM_PTS = {55: 2250, 65: 2350, 75: 2450, 100: 2700}
RPM_DELTA_PTS = {55: 1900, 65: 2000, 80: 2200, 100: 2600}

# Foruddefinerede motorer
MOTORER = {
    "Lycoming IO-360 (200 hp)":    {"P_rated": 200, "turbo": False, "h_crit_ft": 0,     "max_rpm": 2700},
    "DeltaHawk DHK235A4 (235 hp)": {"P_rated": 235, "turbo": True,  "h_crit_ft": 17500, "max_rpm": 2600},
    "Brugerdefineret...":           None,
}


# ══════════════════════════════════════════════════════════════════════════════
#  FYSISKE BEREGNINGSFUNKTIONER
# ══════════════════════════════════════════════════════════════════════════════

def isa_atmosphere(h_m, delta_T_isa=0.0):
    h_m   = min(float(h_m), 10999.0)
    T_sl  = T0 + delta_T_isa
    T     = T_sl - L * h_m
    T_std = T0   - L * h_m
    p     = p0 * (T_std / T0) ** (g / (R * L))
    rho   = p / (R * T)
    h_da  = (T0 / L) * (1.0 - (rho / rho0) ** ((R * L) / (g - R * L)))
    return T, p, rho, h_da


def eta_p_from_J(J, J_data=None, eta_data=None):
    if J_data is None:
        J_data, eta_data = _J_STD, _ETA_STD
    f = interp1d(J_data, eta_data, kind='linear', bounds_error=False, fill_value=0.0)
    return float(f(J))


def eta_p_at_speed(V_ms, n_rps, J_data=None, eta_data=None):
    return eta_p_from_J(V_ms / (n_rps * D), J_data, eta_data)


def engine_power_avail_hp(P_rated_hp, h_m, turbocharged=True, h_crit_ft=17500,
                          delta_T_isa=0.0):
    rho = isa_atmosphere(h_m, delta_T_isa)[2]
    if turbocharged:
        h_crit   = h_crit_ft * ft_to_m
        rho_crit = isa_atmosphere(h_crit, delta_T_isa)[2]
        if h_m <= h_crit:
            return P_rated_hp, 1.0
        sigma = rho / rho_crit
        return P_rated_hp * sigma, sigma
    sigma = rho / rho0
    return P_rated_hp * sigma, sigma


def rpm_fra_pct(pct, rpm_pts: dict) -> int:
    pts  = sorted(rpm_pts.items())
    pcts = [p for p, _ in pts]
    rpms = [r for _, r in pts]
    f    = interp1d(pcts, rpms, kind='linear', fill_value='extrapolate')
    return int(round(float(f(pct))))


def rate_of_climb(V_ms, m_kg, P_hp, h_m, n_revs, gamma,
                  turbo=False, h_crit_ft=17500, J_data=None, eta_data=None,
                  delta_T_isa=0.0):
    eta_p = eta_p_at_speed(V_ms, n_revs, J_data, eta_data)
    W_N   = m_kg * g
    P_W   = engine_power_avail_hp(P_hp, h_m, turbo, h_crit_ft, delta_T_isa)[0] * HP_to_W * eta_p
    rho   = isa_atmosphere(h_m, delta_T_isa)[2]
    return (P_W / W_N
            - (CD0 * rho * V_ms**3) / (2 * (W_N / S))
            - (2 * eps * (W_N / S) * np.cos(gamma)**2) / (rho * V_ms))


def numeric_V_y(m_kg, P_hp, n_revs, h_m,
                turbo=False, h_crit_ft=17500, J_data=None, eta_data=None,
                delta_T_isa=0.0):
    gamma = 0.0
    res   = minimize_scalar(lambda V: -rate_of_climb(V, m_kg, P_hp, h_m, n_revs, gamma, 
                                                     turbo, h_crit_ft, J_data, eta_data, delta_T_isa),
                                                     bounds=(15, 75), method="bounded")
    V_y = res.x
    for _ in range(20):
        RC    = rate_of_climb(V_y, m_kg, P_hp, h_m, n_revs,
                              gamma, turbo, h_crit_ft, J_data, eta_data,
                              delta_T_isa)
        g_new = np.arcsin(np.clip(RC / V_y, -1.0, 1.0))
        if abs(g_new - gamma) < 1e-6:
            break
        gamma = g_new
    RC_max = rate_of_climb(V_y, m_kg, P_hp, h_m, n_revs,
                            gamma, turbo, h_crit_ft, J_data, eta_data,
                            delta_T_isa)
    return V_y, RC_max, gamma


def power_required(V_ms, m_kg, h_m, delta_T_isa=0.0):
    rho = isa_atmosphere(h_m, delta_T_isa)[2]
    W_N = m_kg * g
    return (CD0 * 0.5 * rho * V_ms**3 * S
            + eps * (2 * W_N**2) / (rho * V_ms * S))


def power_available_cruise(V_ms, h_m, P_rated_hp, n_rps, pct,
                            turbo, h_crit_ft=17500, J_data=None, eta_data=None,
                            delta_T_isa=0.0):
    P_avail_hp  = engine_power_avail_hp(P_rated_hp, h_m, turbo, h_crit_ft, delta_T_isa)[0]
    P_cruise_hp = min((pct / 100.0) * P_rated_hp, P_avail_hp)
    return eta_p_at_speed(V_ms, n_rps, J_data, eta_data) * P_cruise_hp * HP_to_W


def find_V_cruise_bounds(m_kg, h_m, P_rated_hp, n_rps, pct,
                          turbo, h_crit_ft=17500, J_data=None, eta_data=None,
                          n_pts=500, delta_T_isa=0.0):
    V_grid  = np.linspace(V_stall_max_Weight_kn * kn_to_ms, 160 * kn_to_ms, n_pts)
    P_avail = np.array([power_available_cruise(V, h_m, P_rated_hp, n_rps, pct,
                                               turbo, h_crit_ft, J_data, eta_data,
                                               delta_T_isa)
                        for V in V_grid])
    P_req   = np.array([power_required(V, m_kg, h_m, delta_T_isa) for V in V_grid])
    excess  = P_avail - P_req
    sc      = np.where(np.diff(np.sign(excess)))[0]
    if len(sc) == 0:
        return None, None

    def cross(i, ex=excess):
        return (V_grid[i] + (V_grid[i+1] - V_grid[i])
                * (-ex[i] / (ex[i+1] - ex[i])))

    filt = [sc[0]]
    for idx in sc[1:]:
        if abs(cross(idx) - cross(filt[-1])) > 5 * kn_to_ms:
            filt.append(idx)
    sc = filt
    if len(sc) == 1:
        return V_stall_max_Weight_kn * kn_to_ms, cross(sc[0])
    return cross(sc[0]), cross(sc[-1])


def find_best_cruise_speed(m_kg, h_m, P_rated_hp, n_rps, pct,
                            turbo, h_crit_ft=17500, J_data=None, eta_data=None,
                            delta_T_isa=0.0):
    # Max cruise = højeste V hvor P_avail >= P_req, dvs. V_max fra cruise bounds
    _, V_max = find_V_cruise_bounds(m_kg, h_m, P_rated_hp, n_rps, pct,
                                     turbo, h_crit_ft, J_data, eta_data,
                                     delta_T_isa=delta_T_isa)
    return V_max / kn_to_ms if V_max is not None else None


# ══════════════════════════════════════════════════════════════════════════════
#  GRAFER
# ══════════════════════════════════════════════════════════════════════════════

def plot_climb(m_kg, P_rated_hp, n_rps, turbo, h_crit_ft,
               J_data, eta_data, motor_navn, delta_T_isa=0.0):
    h_ft_arr = np.linspace(0, (35000 if turbo else 20000), 120)
    h_m_arr  = h_ft_arr * ft_to_m

    fig, ax = plt.subplots(figsize=(6, 9))
    fig.patch.set_facecolor("#F5F0E8")
    ax.set_facecolor("#F5F0E8")

    rc_list = []
    for h_m in h_m_arr:
        try:
            _, RC, _ = numeric_V_y(m_kg, P_rated_hp, n_rps, h_m,
                                    turbo, h_crit_ft, J_data, eta_data,
                                    delta_T_isa)
            rc_list.append(RC * ms_to_fpm)
        except Exception:
            rc_list.append(0.0)
    rc_arr = np.array(rc_list)
    valid  = rc_arr >= 100
    sign = "+" if delta_T_isa >= 0 else ""
    dT_lbl = f"ISA{sign}{delta_T_isa:.0f}°C" if delta_T_isa != 0 else "ISA"
    ax.plot(rc_arr[valid], h_ft_arr[valid],
            color=HDR, linestyle="-", linewidth=1.8, label=dT_lbl)

    ax.set_xlabel("R/C [fpm]", fontsize=10)
    ax.set_ylabel("Pressure Altitude [ft]", fontsize=10)
    ax.set_xlim(left=0)
    ax.set_ylim(0, 35000 if turbo else 20000)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(200))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(5000))
    ax.grid(True, color="gray", linewidth=0.4, alpha=0.7)
    ax.legend(fontsize=9)
    ax.set_title(f"Climb Performance — {motor_navn}\n"
                 f"{m_kg:.0f} kg AUW, {int(n_rps*60)} RPM, full throttle, {dT_lbl}",
                 fontsize=10, pad=8)
    plt.tight_layout()
    plt.show()


def plot_cruise(m_kg, h_m, P_rated_hp, pct, n_rps, turbo, h_crit_ft,
                J_data, eta_data, motor_navn, delta_T_isa=0.0):
    V_grid  = np.linspace(50 * kn_to_ms, 160 * kn_to_ms, 500)
    P_avail = np.array([power_available_cruise(V, h_m, P_rated_hp, n_rps, pct,
                                               turbo, h_crit_ft, J_data, eta_data,
                                               delta_T_isa)
                        for V in V_grid])
    P_req   = np.array([power_required(V, m_kg, h_m, delta_T_isa) for V in V_grid])
    Vn, Vx  = find_V_cruise_bounds(m_kg, h_m, P_rated_hp, n_rps, pct,
                                    turbo, h_crit_ft, J_data, eta_data,
                                    delta_T_isa=delta_T_isa)
    h_da_ft = isa_atmosphere(h_m, delta_T_isa)[3] * m_to_ft
    sign = "+" if delta_T_isa >= 0 else ""
    dT_lbl = f"ISA{sign}{delta_T_isa:.0f}°C" if delta_T_isa != 0 else "ISA"

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.patch.set_facecolor("#F5F0E8")
    ax.set_facecolor("#F5F0E8")
    ax.plot(V_grid / kn_to_ms, P_avail / HP_to_W, color=HDR,       lw=1.8, label="$P_{avail}$")
    ax.plot(V_grid / kn_to_ms, P_req   / HP_to_W, color="#c0392b", lw=1.8, label="$P_{req}$")
    if Vx:
        ax.axvline(Vx / kn_to_ms, color="#27ae60", ls="--", lw=1.4,
                   label=f"$V_{{max}}$ = {Vx/kn_to_ms:.1f} kt")
    if Vn:
        ax.axvline(Vn / kn_to_ms, color="#e67e22", ls="--", lw=1.4,
                   label=f"$V_{{min}}$ = {Vn/kn_to_ms:.1f} kt")
    ax.axvline(V_stall_max_Weight_kn, color="#7f8c8d", ls=":", lw=1.2,
               label=f"$V_{{stall}}$ = {V_stall_max_Weight_kn} kt")
    ax.set_xlabel("TAS [kt]", fontsize=10)
    ax.set_ylabel("Power [hp]", fontsize=10)
    ax.set_title(f"Cruise — {motor_navn}  |  {m_kg:.0f} kg, {pct}% power, "
                 f"DA {h_da_ft:.0f} ft, {dT_lbl}", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, color="gray", linewidth=0.4, alpha=0.5)
    plt.tight_layout()
    plt.show()


# ══════════════════════════════════════════════════════════════════════════════
#  HJÆLPEFUNKTIONER
# ══════════════════════════════════════════════════════════════════════════════

def parse_eta_data(j_txt: str, eta_txt: str):
    try:
        J   = [float(x.strip()) for x in j_txt.split(",") if x.strip()]
        eta = [float(x.strip()) for x in eta_txt.split(",") if x.strip()]
    except ValueError:
        raise ValueError("Kunne ikke fortolke tal — brug kommaseparerede decimaltal")
    if len(J) != len(eta):
        raise ValueError(f"Antal J ({len(J)}) != antal eta ({len(eta)})")
    if len(J) < 2:
        raise ValueError("Mindst 2 datapunkter er nodvendige")
    return J, eta


# ══════════════════════════════════════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════════════════════════════════════

class PerformanceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("T-17  Performance Analyse")
        self.resizable(True, True)
        self.configure(bg=BG)
        self.geometry("800x850")

        style = ttk.Style(self)
        style.theme_use("clam")
        for w in ("TFrame", "TLabel", "TCheckbutton",
                  "TLabelframe", "TLabelframe.Label"):
            style.configure(w, background=BG, font=FONT)
        style.configure("TCombobox", font=FONT)
        style.configure("Accent.TButton",
                        font=("Segoe UI", 12, "bold"),
                        foreground="white", background=HDR, padding=8)
        style.map("Accent.TButton", background=[("active", "#2563a8")])
        style.configure("ToggleOn.TButton",
                        font=("Segoe UI", 11, "bold"),
                        foreground="white", background="#1a3a5c", padding=6)
        style.configure("ToggleOff.TButton",
                        font=("Segoe UI", 11, "bold"),
                        foreground="#555", background="#c8d8e8", padding=6)
        style.map("ToggleOn.TButton",  background=[("active", "#2563a8")])
        style.map("ToggleOff.TButton", background=[("active", "#aabccc")])

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=HDR, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="T-17 Saab Supporter",
                 font=("Segoe UI", 17, "bold"), bg=HDR, fg="white").pack()
        tk.Label(hdr, text="Performance Analyse",
                 font=("Segoe UI", 11), bg=HDR, fg="#a8c8f0").pack()

        # ── Scrollbart indhold ────────────────────────────────────────────────
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        sb     = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner  = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win_id, width=e.width))
        self.bind_all("<MouseWheel>",
                      lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        LEFT  = ttk.Frame(inner, padding=12)
        LEFT.grid(row=0, column=0, sticky="n", padx=(0, 8))
        RIGHT = ttk.Frame(inner, padding=12)
        RIGHT.grid(row=0, column=1, sticky="n")

        # ══════════════════════════════════
        # VENSTRE KOLONNE
        # ══════════════════════════════════

        # ── Climb / Cruise toggle ─────────────────────────────────────────────
        self._sekt(LEFT, "Flyvefase", row=0)
        tog_f = ttk.Frame(LEFT, padding=(8, 4, 8, 8))
        tog_f.grid(row=1, column=0, sticky="ew")
        self._mode = tk.StringVar(value="climb")
        self._btn_climb  = ttk.Button(tog_f, text="  CLIMB",
                                      command=lambda: self._sæt_mode("climb"))
        self._btn_cruise = ttk.Button(tog_f, text="  CRUISE",
                                      command=lambda: self._sæt_mode("cruise"))
        self._btn_climb.grid( row=0, column=0, padx=(0, 4), sticky="ew")
        self._btn_cruise.grid(row=0, column=1, padx=(4, 0), sticky="ew")
        tog_f.columnconfigure(0, weight=1)
        tog_f.columnconfigure(1, weight=1)

        # ── Motor ─────────────────────────────────────────────────────────────
        self._sekt(LEFT, "Motor", row=2)
        mot_f = ttk.Frame(LEFT, padding=(8, 4, 8, 8))
        mot_f.grid(row=3, column=0, sticky="ew")

        self.motor_var = tk.StringVar(value="DeltaHawk DHK235A4 (235 hp)")
        self.motor_cb  = ttk.Combobox(mot_f,
            values=list(MOTORER.keys()),
            textvariable=self.motor_var, state="readonly", width=30, font=FONT)
        self.motor_cb.grid(row=0, column=0, columnspan=2, pady=(0, 6), sticky="ew")
        self.motor_cb.bind("<<ComboboxSelected>>", self._opdater_motor)

        # ── Brugerdefineret motor (skjult som standard) ───────────────────────
        self._custom_mot_frame = ttk.Frame(mot_f, padding=(0, 4, 0, 0))
        self._custom_mot_frame.grid(row=1, column=0, columnspan=2, sticky="ew")

        tk.Label(self._custom_mot_frame, text="P_rated [hp]:",
                 font=FONT, bg=BG).grid(row=0, column=0, sticky="w", pady=3)
        self.custom_P_var = tk.DoubleVar(value=200.0)
        self.custom_P_var.trace_add("write", self._opdater_motor_info_custom)
        ttk.Spinbox(self._custom_mot_frame, from_=50, to=1000,
                    textvariable=self.custom_P_var, width=8,
                    font=FONT).grid(row=0, column=1, padx=(8, 0), pady=3, sticky="w")

        tk.Label(self._custom_mot_frame, text="Max RPM:",
                 font=FONT, bg=BG).grid(row=1, column=0, sticky="w", pady=3)
        self.custom_maxrpm_var = tk.IntVar(value=2700)
        self.custom_maxrpm_var.trace_add("write", self._opdater_motor_info_custom)
        ttk.Spinbox(self._custom_mot_frame, from_=500, to=5000,
                    textvariable=self.custom_maxrpm_var,
                    increment=100, width=8, font=FONT).grid(
                    row=1, column=1, padx=(8, 0), pady=3, sticky="w")

        tk.Label(self._custom_mot_frame, text="Turbocharget:",
                 font=FONT, bg=BG).grid(row=2, column=0, sticky="w", pady=3)
        self._turbo_cb = ttk.Combobox(self._custom_mot_frame,
            values=["Nej (naturlig aspiration)", "Ja (turbocharged)"],
            state="readonly", width=24, font=FONT)
        self._turbo_cb.current(0)
        self._turbo_cb.grid(row=2, column=1, padx=(8, 0), pady=3, sticky="w")
        self._turbo_cb.bind("<<ComboboxSelected>>", self._toggle_hcrit)

        self._hcrit_lbl  = tk.Label(self._custom_mot_frame, text="Kritisk hojde [ft]:",
                                     font=FONT, bg=BG)
        self.custom_hcrit_var = tk.IntVar(value=17500)
        self._hcrit_spin = ttk.Spinbox(self._custom_mot_frame, from_=1000, to=40000,
                                        textvariable=self.custom_hcrit_var,
                                        width=8, font=FONT)
        self._hcrit_lbl.grid( row=3, column=0, sticky="w", pady=3)
        self._hcrit_spin.grid(row=3, column=1, padx=(8, 0), pady=3, sticky="w")
        self._hcrit_lbl.grid_remove()
        self._hcrit_spin.grid_remove()
        self._custom_mot_frame.grid_remove()

        # ── Power setting (kun synlig i cruise-mode) ──────────────────────────
        self._sekt(LEFT, "Power setting & RPM", row=4)
        self._pwr_outer = ttk.Frame(LEFT, padding=(8, 4, 8, 8))
        self._pwr_outer.grid(row=5, column=0, sticky="ew")

        # -- Cruise-panel --
        self._pwr_cruise_f = ttk.Frame(self._pwr_outer)
        self._pwr_cruise_f.pack(fill="x")

        tk.Label(self._pwr_cruise_f, text="Power setting [%]:",
                 font=FONT, bg=BG).grid(row=0, column=0, sticky="w", pady=3)
        self.pct_var = tk.IntVar(value=80)
        self.pct_spin = ttk.Spinbox(self._pwr_cruise_f, from_=30, to=100,
                                     textvariable=self.pct_var,
                                     increment=5, width=8, font=FONT,
                                     command=self._auto_rpm)
        self.pct_spin.grid(row=0, column=1, padx=(8, 0), pady=3, sticky="w")
        self.pct_spin.bind("<FocusOut>", lambda e: self._auto_rpm())
        self.pct_spin.bind("<Return>",   lambda e: self._auto_rpm())

        tk.Label(self._pwr_cruise_f, text="RPM (forslag):",
                 font=FONT, bg=BG).grid(row=1, column=0, sticky="w", pady=3)
        self.rpm_var = tk.IntVar(value=2500)
        ttk.Spinbox(self._pwr_cruise_f, from_=1000, to=3500,
                    textvariable=self.rpm_var, width=8,
                    font=FONT).grid(row=1, column=1, padx=(8, 0), pady=3, sticky="w")
        tk.Label(self._pwr_cruise_f, text="(kan tilpasses manuelt)",
                 font=("Segoe UI", 9), bg=BG, fg="#888").grid(
                 row=2, column=0, columnspan=2, sticky="w")

        # -- Climb-panel (kun info) --
        self._pwr_climb_f = ttk.Frame(self._pwr_outer)
        tk.Label(self._pwr_climb_f,
                 text="Power: 100%  (FT, effekt aftager med højde jf. motormodel)",
                 font=("Segoe UI", 10), bg=BG, fg="#555",
                 wraplength=290, justify="left").pack(anchor="w")
        tk.Label(self._pwr_climb_f, text="RPM: max (fast ud fra motor)",
                 font=("Segoe UI", 10), bg=BG, fg="#555").pack(anchor="w")

        # ── AUW og Altitude ───────────────────────────────────────────────────
        self._sekt(LEFT, "Flyvekonfiguration", row=6)
        fly_f = ttk.Frame(LEFT, padding=(8, 4, 8, 8))
        fly_f.grid(row=7, column=0, sticky="ew")

        tk.Label(fly_f, text="AUW [kg]:",
                 font=FONT, bg=BG).grid(row=0, column=0, sticky="w", pady=3)
        self.auw_var = tk.DoubleVar(value=1000.0)
        ttk.Spinbox(fly_f, from_=600, to=1200, textvariable=self.auw_var,
                    increment=10, width=9, font=FONT).grid(
                    row=0, column=1, padx=(8, 0), pady=3, sticky="w")

        self._alt_lbl = tk.Label(fly_f, text="Pressure Altitude [ft]:",
                                  font=FONT, bg=BG)
        self._alt_lbl.grid(row=1, column=0, sticky="w", pady=3)
        self.alt_var = tk.IntVar(value=5000)
        ttk.Spinbox(fly_f, from_=0, to=35000, textvariable=self.alt_var,
                    increment=500, width=9, font=FONT).grid(
                    row=1, column=1, padx=(8, 0), pady=3, sticky="w")

        tk.Label(fly_f, text="\u0394T ISA [\u00b0C]:",
                 font=FONT, bg=BG).grid(row=2, column=0, sticky="w", pady=3)
        self.dT_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(fly_f, from_=-30, to=50, textvariable=self.dT_var,
                    increment=1, width=9, font=FONT).grid(
                    row=2, column=1, padx=(8, 0), pady=3, sticky="w")

        # ══════════════════════════════════
        # HØJRE KOLONNE
        # ══════════════════════════════════

        # ── eta_p(J) ──────────────────────────────────────────────────────────
        self._sekt(RIGHT, "Propeleffektivitet eta_p(J)", row=0)
        eta_f = ttk.Frame(RIGHT, padding=(8, 4, 8, 8))
        eta_f.grid(row=1, column=0, sticky="ew")

        self.eta_kilde_var = tk.StringVar(value="Standard (NASA-korrigeret)")
        eta_cb = ttk.Combobox(eta_f,
            values=["Standard (NASA-korrigeret)", "Brugerdefineret (indsæt nedenfor)"],
            textvariable=self.eta_kilde_var, state="readonly", width=32, font=FONT)
        eta_cb.grid(row=0, column=0, columnspan=2, pady=(0, 6), sticky="w")
        eta_cb.bind("<<ComboboxSelected>>", self._toggle_eta_input)

        tk.Label(eta_f, text="J-værdier:", font=FONT, bg=BG).grid(
            row=1, column=0, sticky="w", pady=2)
        self.j_var   = tk.StringVar(value="0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0")
        self.j_entry = ttk.Entry(eta_f, textvariable=self.j_var, width=28, font=FONT)
        self.j_entry.grid(row=1, column=1, padx=(8, 0), pady=2, sticky="w")

        tk.Label(eta_f, text="eta_p-værdier:", font=FONT, bg=BG).grid(
            row=2, column=0, sticky="w", pady=2)
        self.eta_var   = tk.StringVar(value="0.31, 0.45, 0.57, 0.65, 0.71, 0.77, 0.80, 0.73, 0.42")
        self.eta_entry = ttk.Entry(eta_f, textvariable=self.eta_var, width=28, font=FONT)
        self.eta_entry.grid(row=2, column=1, padx=(8, 0), pady=2, sticky="w")
        self.j_entry.config(state="disabled")
        self.eta_entry.config(state="disabled")

        # ── Grafer ────────────────────────────────────────────────────────────
        self._sekt(RIGHT, "Grafer (valgfri)", row=2)
        graf_f = ttk.Frame(RIGHT, padding=(8, 4, 8, 8))
        graf_f.grid(row=3, column=0, sticky="ew")
        self.vis_climb_var  = tk.BooleanVar(value=False)
        self.vis_cruise_var = tk.BooleanVar(value=False)
        self._chk_climb  = ttk.Checkbutton(graf_f, text="Vis climb-performance graf",
                                            variable=self.vis_climb_var)
        self._chk_cruise = ttk.Checkbutton(graf_f, text="Vis cruise P_avail vs P_req graf",
                                            variable=self.vis_cruise_var)
        self._chk_climb.grid( row=0, column=0, sticky="w", pady=2)
        self._chk_cruise.grid(row=1, column=0, sticky="w", pady=2)

        # ── Motorspecifikationer ──────────────────────────────────────────────
        self._sekt(RIGHT, "Motorspecifikationer", row=4)
        info_f = ttk.Frame(RIGHT, padding=(8, 4, 8, 8))
        info_f.grid(row=5, column=0, sticky="ew")
        self.info_lbl = tk.Label(info_f, font=FONT_MONO, bg=BG, fg="#555",
                                  justify="left", anchor="w")
        self.info_lbl.pack(anchor="w")

        # ── ISA note ──────────────────────────────────────────────────────────
        self._sekt(RIGHT, "Atmosfaeremodel", row=6)
        isa_f = ttk.Frame(RIGHT, padding=(8, 4, 8, 8))
        isa_f.grid(row=7, column=0, sticky="ew")
        tk.Label(isa_f,
                 text="Atmosfærebetingelser sættes via \u0394T ISA-input.\n"
                      "\u0394T = 0 svarer til standard ISA.",
                 font=("Segoe UI", 10), bg=BG, fg="#555",
                 justify="left").pack(anchor="w")

        # ── Beregn-knap ───────────────────────────────────────────────────────
        btn_f = ttk.Frame(inner, padding=(12, 8, 12, 4))
        btn_f.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.beregn_btn = ttk.Button(btn_f, text="Beregn  ▶",
                                     style="Accent.TButton",
                                     command=self._start_beregning)
        self.beregn_btn.pack(fill="x")

        self.status_var = tk.StringVar(value="")
        self.status_lbl = tk.Label(inner, textvariable=self.status_var,
                                   font=("Segoe UI", 11), bg=BG,
                                   justify="left", anchor="w", padx=12)
        self.status_lbl.grid(row=2, column=0, columnspan=2,
                             sticky="ew", pady=(0, 4))

        self._sekt_wide(inner, "Beregningsresultater", row=3)
        self.tabel = scrolledtext.ScrolledText(
            inner, font=FONT_MONO, height=18, width=90,
            state="disabled", bg="#fafafa", relief="groove", bd=1)
        self.tabel.grid(row=4, column=0, columnspan=2,
                        sticky="ew", padx=12, pady=(0, 16))

        # ── Initialiser tilstand ──────────────────────────────────────────────
        self._sæt_mode("climb")
        self._opdater_motor()

    # ══════════════════════════════════════════════════════════════════════════
    #  HJÆLPEMETODER
    # ══════════════════════════════════════════════════════════════════════════

    def _sekt(self, parent, tekst, row):
        f = tk.Frame(parent, bg=SECT, pady=4, padx=8)
        f.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        tk.Label(f, text=tekst, font=("Segoe UI", 10, "bold"), bg=SECT).pack(anchor="w")

    def _sekt_wide(self, parent, tekst, row):
        f = tk.Frame(parent, bg=SECT, pady=4, padx=8)
        f.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 0))
        tk.Label(f, text=tekst, font=("Segoe UI", 10, "bold"), bg=SECT).pack(anchor="w")

    # ── Climb / Cruise toggle ─────────────────────────────────────────────────
    def _sæt_mode(self, mode: str):
        self._mode.set(mode)
        if mode == "climb":
            self._btn_climb.config( style="ToggleOn.TButton")
            self._btn_cruise.config(style="ToggleOff.TButton")
            self._pwr_cruise_f.pack_forget()
            self._pwr_climb_f.pack(fill="x")
            self._alt_lbl.config(text="Pressure Altitude [ft]:")
            self.vis_cruise_var.set(False)
            self._chk_cruise.config(state="disabled")
            self._chk_climb.config(state="normal")
        else:
            self._btn_climb.config( style="ToggleOff.TButton")
            self._btn_cruise.config(style="ToggleOn.TButton")
            self._pwr_climb_f.pack_forget()
            self._pwr_cruise_f.pack(fill="x")
            self._alt_lbl.config(text="Density Altitude [ft]:")
            self.vis_climb_var.set(False)
            self._chk_climb.config(state="disabled")
            self._chk_cruise.config(state="normal")

    # ── Motor ─────────────────────────────────────────────────────────────────
    def _opdater_motor(self, event=None):
        if self.motor_var.get() == "Brugerdefineret...":
            self._custom_mot_frame.grid()
            self._opdater_motor_info_custom()
        else:
            self._custom_mot_frame.grid_remove()
            specs = MOTORER[self.motor_var.get()]
            self._vis_motor_info(specs["P_rated"], specs["turbo"],
                                 specs["h_crit_ft"], specs.get("max_rpm"))
        self._auto_rpm()

    def _vis_motor_info(self, P_rated, turbo, h_crit_ft, max_rpm=None):
        rpm_str = f"{max_rpm:,} RPM" if max_rpm else "–"
        if turbo:
            info = (f"P_rated:   {P_rated} hp\n"
                    f"Max RPM:   {rpm_str}\n"
                    f"Turbo:     Ja (compound boost)\n"
                    f"Kritisk h: {h_crit_ft:,} ft\n"
                    f"           (fuld effekt herunder)")
        else:
            info = (f"P_rated:   {P_rated} hp\n"
                    f"Max RPM:   {rpm_str}\n"
                    f"Turbo:     Nej\n"
                    f"Effekt:    P_rated * sigma\n"
                    f"           (sigma = rho/rho0)")
        self.info_lbl.config(text=info)

    def _opdater_motor_info_custom(self, *_):
        turbo   = "Ja" in self._turbo_cb.get()
        P       = float(self.custom_P_var.get())
        h_crit  = int(self.custom_hcrit_var.get()) if turbo else None
        try:
            max_rpm = int(self.custom_maxrpm_var.get())
        except Exception:
            max_rpm = 0
        if turbo:
            info = (f"P_rated:   {P:.0f} hp\n"
                    f"Max RPM:   {max_rpm:,} RPM\n"
                    f"Turbo:     Ja\n"
                    f"Kritisk h: {h_crit:,} ft\n"
                    f"           (fuld effekt herunder)")
        else:
            info = (f"P_rated:   {P:.0f} hp\n"
                    f"Max RPM:   {max_rpm:,} RPM\n"
                    f"Turbo:     Nej\n"
                    f"Effekt:    P_rated * sigma\n"
                    f"           (sigma = rho/rho0)")
        self.info_lbl.config(text=info)

    def _toggle_hcrit(self, event=None):
        turbo = "Ja" in self._turbo_cb.get()
        if turbo:
            self._hcrit_lbl.grid()
            self._hcrit_spin.grid()
        else:
            self._hcrit_lbl.grid_remove()
            self._hcrit_spin.grid_remove()
        self._opdater_motor_info_custom()

    # ── RPM auto-forslag ─────────────────────────────────────────────────────
    def _auto_rpm(self, *_):
        try:
            pct = int(self.pct_var.get())
        except Exception:
            return
        valg = self.motor_var.get()
        if valg == "Brugerdefineret...":
            rpm_pts = RPM_DELTA_PTS if "Ja" in self._turbo_cb.get() else RPM_LYCOM_PTS
        elif "DeltaHawk" in valg:
            rpm_pts = RPM_DELTA_PTS
        else:
            rpm_pts = RPM_LYCOM_PTS
        self.rpm_var.set(rpm_fra_pct(pct, rpm_pts))

    # ── eta_p ────────────────────────────────────────────────────────────────
    def _toggle_eta_input(self, event=None):
        state = "normal" if "Brugerdefineret" in self.eta_kilde_var.get() else "disabled"
        self.j_entry.config(state=state)
        self.eta_entry.config(state=state)

    def _hent_eta_data(self):
        if "Brugerdefineret" in self.eta_kilde_var.get():
            return parse_eta_data(self.j_var.get(), self.eta_var.get())
        return None, None

    # ── Motorparametre ────────────────────────────────────────────────────────
    def _hent_motor(self):
        valg = self.motor_var.get()
        if valg == "Brugerdefineret...":
            P_rated  = float(self.custom_P_var.get())
            turbo    = "Ja" in self._turbo_cb.get()
            h_crit   = int(self.custom_hcrit_var.get()) if turbo else 0
            navn     = f"Custom {P_rated:.0f} hp {'turbo' if turbo else 'NA'}"
        else:
            specs   = MOTORER[valg]
            P_rated = specs["P_rated"]
            turbo   = specs["turbo"]
            h_crit  = specs["h_crit_ft"]
            navn    = valg.split(" (")[0]
        return P_rated, turbo, h_crit, navn

    def _hent_max_rpm(self):
        valg = self.motor_var.get()
        if valg == "Brugerdefineret...":
            max_rpm = int(self.custom_maxrpm_var.get())
            # Byg en simpel rpm_pts-tabel skaleret til custom max RPM,
            # ved at skalere de relative procentsatser fra DeltaHawk/Lycoming
            base_pts = RPM_DELTA_PTS if "Ja" in self._turbo_cb.get() else RPM_LYCOM_PTS
            base_max = max(base_pts.values())
            scale    = max_rpm / base_max
            rpm_pts  = {pct: int(round(rpm * scale)) for pct, rpm in base_pts.items()}
            rpm_pts[100] = max_rpm   # sikrer at 100% = præcis max_rpm
            return max_rpm, rpm_pts
        elif "DeltaHawk" in valg:
            rpm_pts = RPM_DELTA_PTS
        else:
            rpm_pts = RPM_LYCOM_PTS
        return max(rpm_pts.values()), rpm_pts

    # ══════════════════════════════════════════════════════════════════════════
    #  BEREGNING
    # ══════════════════════════════════════════════════════════════════════════

    def _start_beregning(self):
        self.beregn_btn.config(state="disabled")
        self.status_var.set("Beregner ...")
        self.status_lbl.config(fg="#1a3a5c")
        threading.Thread(target=self._beregn, daemon=True).start()

    def _beregn(self):
        try:
            mode                        = self._mode.get()
            m_kg                        = float(self.auw_var.get())
            h_ft                        = float(self.alt_var.get())
            delta_T                     = float(self.dT_var.get())
            P_rated, turbo, h_crit, mn  = self._hent_motor()
            J_data, eta_data            = self._hent_eta_data()
            h_m                         = h_ft * ft_to_m

            T, p, rho, h_da = isa_atmosphere(h_m, delta_T)
            sigma = rho / rho0
            dT_lbl = f"ISA+{delta_T:.0f}\u00b0C" if delta_T != 0 else "ISA"

            # ── CLIMB ─────────────────────────────────────────────────────────
            if mode == "climb":
                rpm_max, rpm_pts = self._hent_max_rpm()
                n_rps            = rpm_max / 60.0
                P_avail          = engine_power_avail_hp(
                    P_rated, h_m, turbo, h_crit, delta_T)[0]
                P_avail_pct      = P_avail / P_rated * 100.0

                V_y_ms, RC_ms, gamma_rad = numeric_V_y(
                    m_kg, P_rated, n_rps, h_m, turbo, h_crit, J_data, eta_data,
                    delta_T)

                RC_fpm     = RC_ms * ms_to_fpm
                V_y_TAS_kn = V_y_ms / kn_to_ms
                V_y_IAS_kn = V_y_TAS_kn * np.sqrt(sigma)
                gamma_deg  = np.degrees(gamma_rad)

                # Power used = P_avail (climb bruger 100% tilgængelig effekt)
                P_used     = P_avail
                P_used_pct  = P_used / P_avail * 100.0

                W = 66
                lines = [
                    "=" * W,
                    f"  CLIMB PERFORMANCE  \u2014  {mn}  [{dT_lbl}]",
                    "=" * W,
                    f"  Power avail.:      {P_avail:.0f} hp  ({P_avail_pct:.0f}% af {P_rated} hp rated)",
                    f"  Power used:        {P_used:.0f} hp  ({P_used_pct:.0f}% af {P_avail:.0f} hp avail.)",
                    f"  RPM:               {rpm_max}  (max)",
                    f"  \u03c1 / \u03c3:              {rho:.4f} kg/m\u00b3  /  {sigma:.4f}",
                    "-" * W,
                    f"  Best climb V_y:    {V_y_TAS_kn:.1f} kt TAS   /   {V_y_IAS_kn:.1f} kt IAS",
                    f"  Max R/C:           {RC_fpm:.0f} fpm   ({RC_ms:.2f} m/s)",
                    f"  Flight path \u03b3:     {gamma_deg:.2f}\u00b0",
                ]
                if RC_fpm < 100:
                    lines.append("  \u26a0  R/C < 100 fpm \u2014 under service ceiling-gr\u00e6nsen")
                lines.append("=" * W)

                if self.vis_climb_var.get():
                    self.after(50, lambda: plot_climb(
                        m_kg, P_rated, n_rps, turbo, h_crit,
                        J_data, eta_data, mn, delta_T))

            # ── CRUISE ────────────────────────────────────────────────────────
            else:
                pct     = int(self.pct_var.get())
                n_rps   = float(self.rpm_var.get()) / 60.0
                P_avail = engine_power_avail_hp(
                    P_rated, h_m, turbo, h_crit, delta_T)[0]
                P_avail_pct = P_avail / P_rated * 100.0
                # Power used er minimum af ønsket og tilgængeligt
                P_used      = min((pct / 100.0) * P_rated, P_avail)
                P_used_pct  = P_used / P_avail * 100.0

                Vn, Vx  = find_V_cruise_bounds(
                    m_kg, h_m, P_rated, n_rps, pct, turbo, h_crit,
                    J_data, eta_data, delta_T_isa=delta_T)
                V_max_kn = find_best_cruise_speed(
                    m_kg, h_m, P_rated, n_rps, pct, turbo, h_crit,
                    J_data, eta_data, delta_T_isa=delta_T)

                W = 66
                lines = [
                    "=" * W,
                    f"  CRUISE PERFORMANCE  \u2014  {mn}  [{dT_lbl}]",
                    "=" * W,
                    f"  Power avail.:      {P_avail:.0f} hp  ({P_avail_pct:.0f}% af {P_rated} hp rated)",
                    f"  Power used:        {P_used:.0f} hp  ({P_used_pct:.0f}% af {P_avail:.0f} hp avail.)",
                    f"  RPM:               {int(n_rps*60)}",
                    f"  \u03c1 / \u03c3:              {rho:.4f} kg/m\u00b3  /  {sigma:.4f}",
                    f"  Density altitude:  {h_da*m_to_ft:.0f} ft",
                    "-" * W,
                ]
                if Vx is not None:
                    V_max_IAS = V_max_kn * np.sqrt(sigma)
                    V_min_IAS = Vn / kn_to_ms * np.sqrt(sigma)
                    lines += [
                        f"  Max cruise speed:  {V_max_kn:.1f} kt TAS   /   {V_max_IAS:.1f} kt IAS",
                        f"  Cruise interval:   {Vn/kn_to_ms:.1f} \u2014 {V_max_kn:.1f} kt TAS",
                        f"                     {V_min_IAS:.1f} \u2014 {V_max_IAS:.1f} kt IAS",
                    ]
                else:
                    lines += [
                        "  \u26a0  Motoren kan IKKE opretholde niveau flight",
                        "     ved denne konfiguration og h\u00f8jde.",
                    ]
                lines.append("=" * W)

                if self.vis_cruise_var.get():
                    self.after(50, lambda: plot_cruise(
                        m_kg, h_m, P_rated, pct, n_rps, turbo, h_crit,
                        J_data, eta_data, mn, delta_T))

            self.after(0, lambda: self._vis_resultat("\n".join(lines), "OK"))

        except Exception as ex:
            _ex = str(ex)   # gem beskeden FØR ex slettes
            self.after(0, lambda: self._vis_resultat(_ex, "FEJL"))

    def _vis_resultat(self, tekst, status):
        if status == "OK":
            self.status_var.set("Beregning gennemfort")
            self.status_lbl.config(fg="#27ae60")
        else:
            self.status_var.set(f"Fejl: {tekst}")
            self.status_lbl.config(fg="#c0392b")
        self.tabel.config(state="normal")
        self.tabel.delete("1.0", "end")
        self.tabel.insert("end", tekst)
        self.tabel.config(state="disabled")
        self.beregn_btn.config(state="normal")


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = PerformanceApp()
    app.mainloop()
