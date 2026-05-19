"""
T-17 Saab Supporter — Vægt & Balance
=====================================
Standalone desktop-applikation til brug af FLSK.
Start: dobbeltklik på denne fil, eller kør: python T17_VaegtoBalance.py
"""

# Relevante pakker
import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib", "numpy", "Pillow"])
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import matplotlib.patches as mpatches
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import numpy as np
from PIL import Image
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import unicodedata, os


#  MAC definition og CG-envelope grænser (Fig. V.2)

# MAC-konstanter
MAC_LE_CM     = 195.0   # MAC leading edge, cm fra datum
MAC_TR_CM     = 331.0   # MAC trailing edge, cm fra datum
MAC_LENGTH_CM = 136.0  # MAC-længde, cm

# ── AFT CG-grænser i %MAC ────────────────────────────────
CG_LIMIT_AFT_NORMAL_PCT  = 30.0   # Normal kategori (≤ 1200 kg)
CG_LIMIT_AFT_UTILITY_PCT = 27.5   # Utility I, II og Aerobatic
 
# Ét lineært segment definerer hældningen (aflæst fra CG-envelope, Fig. V.2):
# 825 kg → 15% MAC,  1000 kg → 20% MAC
# Samme hældning ekstrapoleres til 1200 kg (og fastholdet på 15% MAC under 825 kg)
FRONT_KG1, FRONT_PCT1 = 825.0, 15.0
FRONT_KG2, FRONT_PCT2 = 1000.0, 20.0
FRONT_SLOPE = (FRONT_PCT2 - FRONT_PCT1) / (FRONT_KG2 - FRONT_KG1)  # %MAC per kg

def front_cg_limit(vaegt_kg: float) -> float:
    """
    Beregn den vægtspecifikke front CG-grænse i %MAC.
    Lineær ekstrapolation fra det ene aflæste segment i CG-envelope
    (Figure V.2, T-17-1 Flight Manual).
    Under 825 kg fastholdes 15% MAC (konservativt).
    """
    if vaegt_kg <= FRONT_KG1:
        return FRONT_PCT1
    return FRONT_PCT1 + FRONT_SLOPE * (vaegt_kg - FRONT_KG1)

def beregn_cg(zfw_kg: float, zfw_cg_cm: float, ændringer: list) -> tuple:
    """
    Beregn ny CG efter tilføjelse/ændring af masser.
    Parametre:
        zfw_kg     : Zero Fuel Weight [kg]
        zfw_cg_cm  : ZFW CG-position [cm fra datum]
        ændringer  : liste af (beskrivelse, delta_masse_kg, arm_cm)
    Returnerer:
        (ny_vægt_kg, ny_cg_cm, cg_pct_mac)
    Enheder: kg og cm (momenter i kg·cm, konverteres til kg·m i output)
    """

    # ── ZFW moment ──
    total_moment = zfw_kg * zfw_cg_cm
    total_masse  = zfw_kg
    moment_ændring = 0
    

    print("\n" + "="*90)
    print("T-17  Vægt & Balance — CG-beregning")
    print("="*90)
    print(f"{'Komponent':<28} {'Masse [kg]':>12} {'Arm fra ZFW CG [cm]':>22} {'Moment ændring [kg·m]':>26}")
    print("-"*90)
    print(f"{'ZFW':<28} {zfw_kg:>10.1f} {'(= 0)':>20} {'(= 0)':>20}")

    for beskrivelse, dm_kg, arm_cm in ændringer:
        moment = dm_kg * arm_cm
        total_moment += moment
        total_masse  += dm_kg
        arm_fra_cg = arm_cm - zfw_cg_cm
        moment_fra_cg = dm_kg * arm_fra_cg
        moment_ændring += moment_fra_cg
        print(f"  {beskrivelse:<26} {dm_kg:>+10.1f} {arm_fra_cg:>+20.1f} {moment_fra_cg/100:>+20.1f}")

    if total_masse > 1200.0:
        print("-"*90)
        print(f"  ✗  TOTALVÆGT {total_masse:.1f} kg OVERSKRIDER MAKS. TAKEOFF WEIGHT (1200.0 kg) — BEREGNING AFBRUDT")
        print("="*90)
        return None, None, None
    
    print("-"*90)
    ny_cg_cm    = total_moment / total_masse
    ny_cg_pct   = (ny_cg_cm - MAC_LE_CM) / MAC_LENGTH_CM * 100.0

    print(f"{'NY TOTAL':<28} {total_masse:>9.1f} kg {'':>20} {moment_ændring/100:>16.1f} kg·m")
    print(f"\n  ➤  Ny CG:   {ny_cg_cm:.2f} cm fra datum")
    print(f"  ➤  CG %MAC: {ny_cg_pct:.2f}%")

    # ── CG-grænse-check ──
    fwd_limit = front_cg_limit(total_masse)
    print(f"  ➤  Fwd CG-limit ved {total_masse:.1f} kg: {fwd_limit:.2f}% MAC")
    if total_masse >= 1125.0:
        aft_limit = CG_LIMIT_AFT_NORMAL_PCT
    else:
        aft_limit = CG_LIMIT_AFT_UTILITY_PCT
    print(f"  ➤  Aft CG-limit ved {total_masse:.1f} kg: {aft_limit:.2f}% MAC")
 
    front_limit_check = ny_cg_pct < fwd_limit
    back_normal_check  = ny_cg_pct > CG_LIMIT_AFT_NORMAL_PCT
    back_utility_check = ny_cg_pct > CG_LIMIT_AFT_UTILITY_PCT
 
    if ny_cg_pct < 0:
        print(f"  ✗  CG ER FORAN MAC LEADING EDGE — UGYLDIG KONFIGURATION!")
    elif front_limit_check:
        margin = fwd_limit - ny_cg_pct
        print(f"  ⚠  CG er foran fwd-limit ({fwd_limit:.2f}% MAC) for {total_masse:.1f}kg med {margin:.2f}%MAC")
    elif back_normal_check and total_masse>=1125.0 or ny_cg_pct > CG_LIMIT_AFT_NORMAL_PCT:
        margin = ny_cg_pct - CG_LIMIT_AFT_NORMAL_PCT
        print(f"  ✗  CG OVERSKRIDER AFT LIMIT ({CG_LIMIT_AFT_NORMAL_PCT}% MAC) med {margin:.2f}%MAC")
    elif back_utility_check and total_masse<1125.0:
        margin = ny_cg_pct - CG_LIMIT_AFT_UTILITY_PCT
        print(f"  ⚠  CG er bag Utility/Aerobatic aft-limit ({CG_LIMIT_AFT_UTILITY_PCT}% MAC) med {margin:.2f}%MAC - Kan kun føres i Normal ({CG_LIMIT_AFT_NORMAL_PCT}%MAC) kategori")
    else:
        if total_masse >= 1125.0:
            margin_aft  = CG_LIMIT_AFT_NORMAL_PCT - ny_cg_pct
        else:
            margin_aft  = CG_LIMIT_AFT_UTILITY_PCT - ny_cg_pct
        margin_fwd  = ny_cg_pct - fwd_limit
        print(f"  ✓  CG er indenfor CG envelope for den beregnede totalvægt (AUW)")
        print(f"     Margin til aft-limit: {margin_aft:.2f}%MAC  |  "
              f"Margin til fwd-limit: {margin_fwd:.2f}%MAC")

    print("="*90)
    return total_masse, ny_cg_cm, ny_cg_pct



# Billede-kalibrering (pixel-analyse af T-17_tegning_med_MAC.png)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
def res(navn):
    return os.path.join(BASE_DIR, navn)

# Indlæs billeder (konverteret til ægte PNG ved første kørsel)
fly_img   = mpimg.imread(res('T-17 tegning med MAC.png'))
cg_raw    = Image.open(res('CG symbol.png')).convert("RGBA")

DATUM_PX     = 16     # x-pixel for Reference Datum (lodrette stiplede linje)
IMG_WIDTH_PX = 649    # total billedbredde i pixels
SCALE_CM     = 710.0  # cm fra datum til højre billedkant
PX_PER_CM    = (IMG_WIDTH_PX - DATUM_PX) / SCALE_CM   # ≈ 0.893 px/cm

CENTERLINE_Y_PX = 192   # y-pixel for vandret stiplede centerline (fuselage)

def cm_to_px(cm: float) -> float:
    """Konverter arm (cm fra datum) til x-pixel i billedet."""
    return DATUM_PX + cm * PX_PER_CM



def visualiser_cg(ny_vaegt_kg: float, ny_cg_cm: float, ny_cg_pct: float,
                  load_case_navn: str = "Load Case"):
    """
    Tegner CG-symbolet på flyets sideprofil ved den beregnede CG-position.
    fly_img og cg_raw skal være indlæst som globale variable inden kald.
    """

    img_h, img_w = fly_img.shape[:2]

    # ── Figur-opsætning ───────────────────────────────────────────────────────
    fig_width  = 14
    fig_height = fig_width * (img_h + 110 + 180) / img_w * 1.08
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    top_margin   = 70  # ekstra pixels over flyillustrationen til info-boks
    ax.set_xlim(0, img_w)
    ax.set_ylim(0, img_h + 110 + top_margin)
    ax.set_aspect('equal')
    ax.axis('off')

    y_offset         = 100
    y_img_bottom     = y_offset
    y_img_top        = y_offset + img_h
    centerline_y_fig = y_img_top - CENTERLINE_Y_PX

    ax.imshow(fly_img,
              extent=[0, img_w, y_img_bottom, y_img_top],
              origin='upper')

    # ── Skala i bunden ────────────────────────────────────────────────────────
    scale_y  = 70
    tick_h   = 12
    major_cm = np.arange(0, SCALE_CM + 1, 100)
    minor_cm = np.arange(0, SCALE_CM + 1,  50)

    ax.hlines(scale_y, DATUM_PX, IMG_WIDTH_PX, color='#333333', lw=1.5)

    for cm in major_cm:
        px = cm_to_px(cm)
        ax.vlines(px, scale_y - tick_h/2, scale_y + tick_h/2,
                  color='#333333', lw=2.0)
        ax.text(px, scale_y - tick_h - 4, f'{int(cm)}',
                ha='center', va='top', fontsize=16, color='#333333')

    for cm in minor_cm:
        if cm % 100 != 0:
            px = cm_to_px(cm)
            ax.vlines(px, scale_y - tick_h/4, scale_y + tick_h/4,
                      color='#333333', lw=0.8)

    ax.text(img_w / 2, scale_y - tick_h - 18,
            'Arm fra Reference Datum [cm]',
            ha='center', va='top', fontsize=16, color='#333333', style='italic')

    ax.text(DATUM_PX, scale_y + tick_h,
            'Ref.\nDatum', ha='center', va='bottom', fontsize=8, color='#555555')

    # ── MAC-markering ─────────────────────────────────────────────────────────
    mac_le_px = cm_to_px(MAC_LE_CM)
    mac_te_px = cm_to_px(MAC_TR_CM)
    mac_y     = scale_y + 32

    ax.hlines(mac_y, mac_le_px, mac_te_px, color='steelblue', lw=3.0)
    ax.annotate('', xy=(mac_te_px, mac_y), xytext=(mac_le_px, mac_y),
                arrowprops=dict(arrowstyle='<->', color='steelblue', lw=1.5))
    ax.text((mac_le_px + mac_te_px) / 2, mac_y - 20,
            'MAC', ha='center', va='bottom', fontsize=14, color='steelblue')

    # ── Grænser for den aktuelle AUW ──────────────────────────────────────────
    fwd_limit_pct = front_cg_limit(ny_vaegt_kg)
    aft_limit_pct = CG_LIMIT_AFT_NORMAL_PCT if ny_vaegt_kg >= 1125.0 or ny_cg_pct > CG_LIMIT_AFT_NORMAL_PCT else CG_LIMIT_AFT_UTILITY_PCT

    fwd_limit_cm = MAC_LE_CM + fwd_limit_pct / 100.0 * MAC_LENGTH_CM
    aft_limit_cm = MAC_LE_CM + aft_limit_pct / 100.0 * MAC_LENGTH_CM
    fwd_limit_px = cm_to_px(fwd_limit_cm)
    aft_limit_px = cm_to_px(aft_limit_cm)

    label_y = mac_y + 18   # lige over MAC-linjen

    # Fwd limit — blå stiplet, label til VENSTRE
    ax.vlines(fwd_limit_px, scale_y, y_img_top,
              color='#2980b9', lw=1.4, linestyle='--', alpha=0.85)
    ax.text(fwd_limit_px - 6, label_y,
            f'Fwd: {fwd_limit_pct:.1f}%',
            ha='right', va='bottom', fontsize=12, color='#2980b9',
            bbox=dict(fc='white', ec='none', pad=1))

    # Aft limit — rød stiplet, label til HØJRE
    ax.vlines(aft_limit_px, scale_y, y_img_top,
              color='#c0392b', lw=1.4, linestyle='--', alpha=0.85)
    ax.text(aft_limit_px + 6, label_y,
            f'Aft: {aft_limit_pct:.1f}%',
            ha='left', va='bottom', fontsize=12, color='#c0392b',
            bbox=dict(fc='white', ec='none', pad=1))

    # ── Lower Edge of Firewall ved 120 cm ─────────────────────────────────────
    firewall_px = cm_to_px(120.0)
    ax.vlines(firewall_px, scale_y, y_img_top,
              color='#7f8c8d', lw=1.2, linestyle='--', alpha=0.75)
    ax.text(firewall_px - 4, scale_y + tick_h + 4,
            'Lower Edge\nof Firewall\n(120cm)',
            ha='right', va='bottom', fontsize=12, color='#7f8c8d',
            bbox=dict(fc='white', ec='none', pad=1))

    # ── Ny CG ─────────────────────────────────────────────────────────────────
    ny_cg_px = cm_to_px(ny_cg_cm)

    foran      = ny_cg_pct < fwd_limit_pct
    bag_normal = ny_cg_pct > CG_LIMIT_AFT_NORMAL_PCT
    bag_util   = ny_cg_pct > CG_LIMIT_AFT_UTILITY_PCT and ny_vaegt_kg < 1125.0

    cg_color = '#c0392b' if (foran or bag_normal or bag_util or ny_cg_pct < 0) else '#27ae60'

    ax.vlines(ny_cg_px, scale_y, centerline_y_fig,
              color=cg_color, lw=2.0, linestyle='-', alpha=0.9)
    ax.plot(ny_cg_px, centerline_y_fig, 'D',
            color=cg_color, markersize=6, zorder=5)

    # ── CG-symbol ─────────────────────────────────────────────────────────────
    symbol_size_px_fig = 24 * PX_PER_CM * (fig_width / img_w) * 72
    cg_zoom = symbol_size_px_fig / cg_raw.size[0] * 0.55
    ab = AnnotationBbox(OffsetImage(np.array(cg_raw), zoom=cg_zoom),
                        (ny_cg_px, centerline_y_fig),
                        frameon=False, zorder=6)
    ax.add_artist(ab)

    # ── Tekst-output boks ─────────────────────────────────────────────────────
    margin_fwd = ny_cg_pct - fwd_limit_pct
    margin_aft = aft_limit_pct - ny_cg_pct

    if ny_cg_pct < 0:
        status = "✗ FORAN MAC LEADING EDGE — UGYLDIG"
    elif foran:
        status = f"✗ FORAN FWD LIMIT ({fwd_limit_pct:.1f}%MAC) - UGYLDIG"
    elif bag_normal:
        status = f"✗ BAG AFT LIMIT ({CG_LIMIT_AFT_NORMAL_PCT}%MAC) — UGYLDIG"
    elif bag_util:
        status = (f"⚠ Bag Utility/Aerobatic aft limit ({CG_LIMIT_AFT_UTILITY_PCT}%MAC)\n"
              f"              Kan kun føres i Normal ({CG_LIMIT_AFT_NORMAL_PCT}%MAC) kategori")
    else:
        status = f"✓ OK  (fwd margin: {margin_fwd:.2f}%  aft margin: {margin_aft:.2f}%)"
    

    info_text = (
        f"{load_case_navn}\n"
        f"AUW:          {ny_vaegt_kg:.1f} kg\n"
        f"CG:           {ny_cg_cm:.2f} cm fra datum\n"
        f"CG (%MAC):    {ny_cg_pct:.2f}%\n"
        f"Fwd limit:    {fwd_limit_pct:.2f}% MAC\n"             
        f"Aft limit:    {aft_limit_pct:.2f}% MAC\n"
        f"Status:       {status}"
    )
    ax.text(0.01, 0.99, info_text,
            transform=ax.transAxes, va='top', ha='left',
            fontsize=12, fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.5', fc='white', ec='#cccccc', alpha=0.92))

    # ── Legende ───────────────────────────────────────────────────────────────
    plt.title(f"T-17 Vægt & Balance — {load_case_navn}", fontsize=16, pad=8)
    plt.tight_layout(rect=[0, 0, 0.88, 0.94])
    plt.show()


# ═════════════════════════════════════════════════════════
#  ▼▼▼  BRUGERINPUT  ▼▼▼
# ═════════════════════════════════════════════════════════

# ZFW-konfiguration (aflæst fra Matins vægt & balance-dokument og RDAF T-17 Flight Manual)
ZFW_KG     = 733.0    # kg (inkluderer 10L "unusable" brændstof i hver vinge og 8 quarts olie)
ZFW_CG_CM  = 227.0    # cm fra datum
ZFW_CG_PCT = 23.53    # % MAC

# Standard arm-positioner (cm fra datum)
ARM_propel          = 25.0  # cm fra datum (antaget propel CG)
ARM_motor           = 72.0  # cm fra datum (antaget motor CG)
ARM_pilot_sæde      = 218.0 # cm fra datum (pilot sæder)
ARM_bagsæde         = 278.0 # cm fra datum (passager sæde)
ARM_cargo           = 278.0 # cm fra datum (cargo)
ARM_fuel            = 269.0 # cm fra datum (brændstof CG)
ARM_IFF             = 300.0 # cm fra datum (antaget IFF system i avionics compartment)
ARM_batteri         = 379.0 # cm fra datum (hovedbatteri i avionics compartment)
ARM_LINDA_C         = 546.0 # cm fra datum (LINDA-C i haleparti)

# Standard vægt
Bagsæde_kg      = 5.0   # kg (vægt for bagsædet)
Batteri_kg      = 13.3  # kg (vægt for hovedbatteri)
IFF_kg          = 7.0   # kg (vægt for IFF system)
DeltaHawk_dm_kg = 1.0   # kg (Vægtforskel for DeltaHawk motor vs. original Lycoming)
Propel_dm_kg    = -6.8  # kg (Vægtforskel for tre-bladet propel vs. original to-bladet)

# Omregning af brændstofvægt
F18_densitet = 0.7211  # kg/L for Avgas 100LL
F34_densitet = 0.805   # kg/L for Jet-A1 / JP-8


# ══════════════════════════════════════════════════════════════════════════════
#  GUI kode
# ══════════════════════════════════════════════════════════════════════════════
 
BG   = "#f0f0f0"
HDR  = "#1a3a5c"
SECT = "#dce8f5"
FONT      = ("Segoe UI", 11)
FONT_MONO = ("Courier New", 10)
 
 
def _byg_ændringer(inputs: dict) -> list:
    """Oversæt UI-inputs til ændringsliste til beregn_cg()."""
    æ = []
    for label, kg, arm in [
        ("Pilot venstre sæde", inputs["pilot_v"],  ARM_pilot_sæde),
        ("Pilot højre sæde",   inputs["pilot_h"],  ARM_pilot_sæde),
        ("Passager / cargo",   inputs["passager"], ARM_bagsæde),
    ]:
        if kg != 0:
            æ.append((label, kg, arm))
 
    bf_l    = inputs["brændstof_l"]
    bf_dens = inputs["brændstof_dens"]
    bf_type = inputs["brændstof_type"]
    if inputs["deltahawk"]:
        æ.append(("DeltaHawk motor Δm",  DeltaHawk_dm_kg,       ARM_motor))
        æ.append(("Unusable F-18 (20L) ud",       -20 * F18_densitet, ARM_fuel))
        æ.append(("Unusable F-34 (20L) ind",       20 * F34_densitet, ARM_fuel))
    if "F-18" in bf_type:
        æ.append((f"F-18 Avgas ({bf_l:.0f} L)", bf_l * bf_dens, ARM_fuel))
    elif "Tilpasset" in bf_type:
        bf_navn = inputs.get("brændstof_navn", "").strip() or "Tilpasset brændstof"
        æ.append((f"{bf_navn} ({bf_l:.0f} L)", bf_l * bf_dens, ARM_fuel))
    else:
        æ.append((f"F-34 Jet A-1 ({bf_l:.0f} L)", bf_l * bf_dens, ARM_fuel))
    if inputs["propel"]:
        æ.append(("Tre-bladet propel Δm",  Propel_dm_kg, ARM_propel))
    if inputs["fjern_iff"]:
        æ.append(("Afmonteret IFF system",        -IFF_kg,      ARM_IFF))
    if inputs["fjern_bagsæde"]:
        æ.append(("Afmonteret bagsæde",           -Bagsæde_kg,  ARM_bagsæde))
    if inputs["flyt_batteri"]:
        æ.append(("Batteri afmonteret foran",     -Batteri_kg,  ARM_batteri))
        æ.append(("Batteri monteret agter",       +Batteri_kg,  ARM_LINDA_C))
 
    for navn, dm, arm in inputs["custom"]:
        if navn and dm != 0:
            æ.append((navn, dm, arm))
 
    return æ
 
 
def _byg_tabel_str(auw, cg_cm, cg_pct, ændringer):
    """Returnerer beregningsresultater som formateret streng."""
    W = 90
    fwd_limit = front_cg_limit(auw)
    aft_limit = CG_LIMIT_AFT_NORMAL_PCT if auw >= 1125.0 else CG_LIMIT_AFT_UTILITY_PCT
    lines = []
    lines.append("=" * W)
    lines.append("T-17  Vægt & Balance — CG-beregning")
    lines.append("=" * W)
    lines.append(f"{'Komponent':<28} {'Masse [kg]':>10} "
                 f"{'Arm fra ZFW CG [cm]':>22} {'Moment ændring [kg·m]':>14}")
    lines.append("-" * W)
    lines.append(f"{'ZFW':<28} {ZFW_KG:>10.1f} {'(= 0)':>16} {'(= 0)':>14}")
    moment_sum = 0.0
    for navn, dm, arm in ændringer:
        arm_rel = arm - ZFW_CG_CM
        dm_x    = dm * arm_rel
        moment_sum += dm_x
        lines.append(f"  {navn:<26} {dm:>+10.1f} {arm_rel:>+16.1f} {dm_x/100:>+14.1f}")
    lines.append("-" * W)
    lines.append(f"{'NY TOTAL (AUW)':<28} {auw:>10.1f} {'':>22} {moment_sum/100:>+14.2f}")
    lines.append("")
    lines.append(f"  ➤  Ny CG:        {cg_cm:.2f} cm fra datum")
    lines.append(f"  ➤  CG (%MAC):    {cg_pct:.2f}%")
    lines.append(f"  ➤  Fwd limit:    {fwd_limit:.2f}% MAC  @ {auw:.1f} kg")
    lines.append(f"  ➤  Aft limit:    {aft_limit:.2f}% MAC  @ {auw:.1f} kg")
    foran = cg_pct < fwd_limit
    bag_n = cg_pct > CG_LIMIT_AFT_NORMAL_PCT
    bag_u = cg_pct > CG_LIMIT_AFT_UTILITY_PCT and auw < 1125.0
    mfwd  = cg_pct - fwd_limit
    maft  = aft_limit - cg_pct
    if cg_pct < 0:
        lines.append("  ✗  CG ER FORAN MAC LEADING EDGE — UGYLDIG!")
    elif foran:
        lines.append(f"  ⚠  CG er foran fwd-limit med {fwd_limit - cg_pct:.2f}%MAC — UGYLDIG!")
    elif bag_n:
        lines.append(f"  ✗  CG OVERSKRIDER AFT LIMIT ({CG_LIMIT_AFT_NORMAL_PCT}%MAC) — UGYLDIG!")
    elif bag_u:
        lines.append(f"  ⚠  CG bag Utility aft-limit — kun Normal kategori tilladt")
    else:
        lines.append(f"  ✓  CG er indenfor CG envelope for AUW")
        lines.append(f"     Margin til fwd-limit: {mfwd:.2f}%MAC  |  Margin til aft-limit: {maft:.2f}%MAC")
    lines.append("=" * W)
    return "\n".join(lines)
 
 
class VaegtoBalanceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("T-17  Vægt & Balance")
        self.resizable(True, True)
        self.configure(bg=BG)
        self.geometry("800x800")
 
        style = ttk.Style(self)
        style.theme_use("clam")
        for w in ("TFrame","TLabel","TCheckbutton","TLabelframe","TLabelframe.Label"):
            style.configure(w, background=BG, font=FONT)
        style.configure("TCombobox", font=FONT)
        style.configure("Accent.TButton", font=("Segoe UI", 12, "bold"),
                        foreground="white", background=HDR, padding=8)
        style.map("Accent.TButton", background=[("active", "#2563a8")])
 
        # Header
        hdr = tk.Frame(self, bg=HDR, pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="T-17 Saab Supporter",
                 font=("Segoe UI", 17, "bold"), bg=HDR, fg="white").pack()
        tk.Label(hdr, text="Vægt & Balance Beregner",
                 font=("Segoe UI", 11), bg=HDR, fg="#a8c8f0").pack()
 
        # Scrollbart indhold
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        sb     = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner  = ttk.Frame(canvas)
        win_id = canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win_id, width=e.width))
        self.bind_all("<MouseWheel>",
                      lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
 
        LEFT  = ttk.Frame(inner, padding=12);  LEFT.grid( row=0, column=0, sticky="n", padx=(0,8))
        RIGHT = ttk.Frame(inner, padding=12);  RIGHT.grid(row=0, column=1, sticky="n")
 
        # ─── VENSTRE ──────────────────────────────────────────────────────
        self._sekt(LEFT, "👤  Besætning & Last", row=0)
        crew = ttk.Frame(LEFT, padding=(8,4,8,8));  crew.grid(row=1, column=0, sticky="ew")
        ttk.Label(crew, text="Pilot venstre sæde [kg]:").grid(row=0, column=0, sticky="w", pady=3)
        self.pilot_v   = self._spin(crew, -200, 200, 85, r=0, c=1)
        ttk.Label(crew, text="Pilot højre sæde [kg]:").grid(row=1, column=0, sticky="w", pady=3)
        self.pilot_h   = self._spin(crew, -200, 200, 85, r=1, c=1)
        ttk.Label(crew, text="Passager / cargo [kg]",
                  justify="left").grid(row=2, column=0, sticky="w", pady=3)
        self.passager  = self._spin(crew, -200, 200, 0, r=2, c=1)
 
        self._sekt(LEFT, "⛽  Brændstof", row=2)
        fuel = ttk.Frame(LEFT, padding=(8,4,8,8));  fuel.grid(row=3, column=0, sticky="ew")
        ttk.Label(fuel, text="Type:").grid(row=0, column=0, sticky="w", pady=3)
        self.bf_type = ttk.Combobox(fuel,
            values=["F-18 (Avgas 100LL)", "F-34 (Jet A-1 / JP-8)", "Tilpasset..."],
            state="readonly", width=22, font=FONT)
        self.bf_type.current(1)
        self.bf_type.grid(row=0, column=1, padx=(8,0), pady=3, sticky="w")
        self.bf_type.bind("<<ComboboxSelected>>", self._opdater_densitet)
        self.bf_navn_label = ttk.Label(fuel, text="Brændstofnavn:")
        self.bf_navn_var   = tk.StringVar(value="")
        self.bf_navn_entry = ttk.Entry(fuel, textvariable=self.bf_navn_var,
                                       width=22, font=FONT)
        ttk.Label(fuel, text="Mængde [liter]:").grid(row=2, column=0, sticky="w", pady=3)
        self.bf_l = self._spin(fuel, 0, 158, 110, r=2, c=1)
        ttk.Label(fuel, text="Densitet [kg/L]:").grid(row=3, column=0, sticky="w", pady=3)
        self.bf_dens_var = tk.DoubleVar(value=F34_densitet)
        dens_f = ttk.Frame(fuel);  dens_f.grid(row=3, column=1, padx=(8,0), sticky="w")
        ttk.Spinbox(dens_f, from_=0.600, to=0.900, textvariable=self.bf_dens_var,
                    increment=0.001, width=8, format="%.3f",
                    font=FONT).pack(side="left")
        self.bf_dens_hint = tk.Label(dens_f, text=f"(std: {F34_densitet:.3f})",
                                     font=("Segoe UI",9), bg=BG, fg="#888")
        self.bf_dens_hint.pack(side="left", padx=(6,0))
 
        self._sekt(LEFT, "ℹ️  ZFW reference", row=4)
        zfw_f = ttk.Frame(LEFT, padding=(8,4,8,8));  zfw_f.grid(row=5, column=0, sticky="ew")
        tk.Label(zfw_f, text=f"ZFW:     {ZFW_KG:.0f} kg",
                 font=FONT_MONO, bg=BG, fg="#555").pack(anchor="w")
        tk.Label(zfw_f, text=f"ZFW CG:  {ZFW_CG_CM:.0f} cm fra datum",
                 font=FONT_MONO, bg=BG, fg="#555").pack(anchor="w")
        tk.Label(zfw_f, text=f"ZFW CG (%):  {ZFW_CG_PCT:.2f} % MAC",
                 font=FONT_MONO, bg=BG, fg="#555").pack(anchor="w")
 
        # ─── HØJRE ────────────────────────────────────────────────────────
        self._sekt(RIGHT, "⚙️  Konfiguration", row=0)
        cfg = ttk.Frame(RIGHT, padding=(8,4,8,8));  cfg.grid(row=1, column=0, sticky="ew")
        self.deltahawk     = self._chk(cfg, "DeltaHawk motor DHK235A4",               True,  r=0)
        self.propel        = self._chk(cfg, "Tre-bladet propel MTV-12-B-C/C188-59",   True,  r=1)
        self.fjern_iff     = self._chk(cfg, "Afmonteret IFF system",                  True,  r=2)
        self.fjern_bagsæde = self._chk(cfg, "Afmonteret bagsæde",                     True,  r=3)
        self.flyt_batteri  = self._chk(cfg, "Batteri rykket til halesektion",         False, r=4)
 
        self._sekt(RIGHT, "➕  Brugerdefinerede ændringer", row=2)
        self.custom_frame    = ttk.Frame(RIGHT, padding=(8,4,8,8))
        self.custom_frame.grid(row=3, column=0, sticky="ew")
        for col, txt in [(0,"Navn / beskrivelse"),(1,"Δm [kg]"),(2,"Arm [cm]")]:
            tk.Label(self.custom_frame, text=txt,
                     font=("Segoe UI",10,"bold"), bg=BG).grid(
                     row=0, column=col, padx=(0,6), pady=(0,2), sticky="w")
        self.custom_rows    = []
        self.custom_next_row = 1
        self._tilfoej_custom_row()
        ttk.Button(self.custom_frame, text="+ Tilføj række",
                   command=self._tilfoej_custom_row).grid(
                   row=99, column=0, columnspan=3, sticky="w", pady=(6,0))
 
        self._sekt(RIGHT, "📋  Load Case navn", row=4)
        navn_f = ttk.Frame(RIGHT, padding=(8,4,8,8));  navn_f.grid(row=5, column=0, sticky="ew")
        self.load_case = tk.StringVar(value="DeltaHawk typisk FLSK konfiguration")
        ttk.Entry(navn_f, textvariable=self.load_case, width=38, font=FONT).pack(fill="x")
 
        # ─── Knap + status + tabel ────────────────────────────────────────
        btn_f = ttk.Frame(inner, padding=(12,8,12,4))
        btn_f.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Button(btn_f, text="Beregn & Vis figur  ▶",
                   style="Accent.TButton", command=self.kør).pack(fill="x")
        self.vis_figur = tk.BooleanVar(value=True)
        ttk.Checkbutton(btn_f, text="Vis figur ved beregning",
                        variable=self.vis_figur).pack(anchor="w", pady=(6,0))
 
        self.status_var = tk.StringVar(value="")
        self.status_lbl = tk.Label(inner, textvariable=self.status_var,
                                   font=("Segoe UI", 11), bg=BG,
                                   justify="left", anchor="w", padx=12)
        self.status_lbl.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0,4))
 
        self._sekt_wide(inner, "📊  Beregningsresultater", row=3)
        self.tabel = scrolledtext.ScrolledText(inner, font=FONT_MONO,
                                               height=18, width=95,
                                               state="disabled", bg="#fafafa",
                                               relief="groove", bd=1)
        self.tabel.grid(row=4, column=0, columnspan=2,
                        sticky="ew", padx=12, pady=(0,16))
 
    # ── Hjælpemetoder ──────────────────────────────────────────────────────
    def _sekt(self, parent, tekst, row):
        f = tk.Frame(parent, bg=SECT, pady=4, padx=8)
        f.grid(row=row, column=0, sticky="ew", pady=(10,0))
        tk.Label(f, text=tekst, font=("Segoe UI",10,"bold"), bg=SECT).pack(anchor="w")
 
    def _sekt_wide(self, parent, tekst, row):
        f = tk.Frame(parent, bg=SECT, pady=4, padx=8)
        f.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=(10,0))
        tk.Label(f, text=tekst, font=("Segoe UI",10,"bold"), bg=SECT).pack(anchor="w")
 
    def _spin(self, parent, fra, til, start, r, c):
        var = tk.DoubleVar(value=start)
        ttk.Spinbox(parent, from_=fra, to=til, textvariable=var,
                    width=9, font=FONT).grid(row=r, column=c, padx=(8,0), pady=3, sticky="w")
        return var
 
    def _chk(self, parent, tekst, default, r):
        var = tk.BooleanVar(value=default)
        ttk.Checkbutton(parent, text=tekst, variable=var).grid(
            row=r, column=0, sticky="w", pady=2)
        return var
 
    def _tilfoej_custom_row(self):
        r = self.custom_next_row
        navn_var = tk.StringVar(value="")
        dm_var   = tk.DoubleVar(value=0.0)
        arm_var  = tk.DoubleVar(value=0.0)
        ttk.Entry(self.custom_frame, textvariable=navn_var,
                  width=20, font=FONT).grid(row=r, column=0, padx=(0,6), pady=2, sticky="w")
        ttk.Spinbox(self.custom_frame, from_=-9999, to=9999, textvariable=dm_var,
                    width=8, font=FONT).grid(row=r, column=1, padx=(0,6), pady=2)
        ttk.Spinbox(self.custom_frame, from_=0, to=9999, textvariable=arm_var,
                    width=8, font=FONT).grid(row=r, column=2, pady=2)
        self.custom_rows.append((navn_var, dm_var, arm_var))
        self.custom_next_row += 1
 
    def _opdater_densitet(self, event=None):
        sel = self.bf_type.get()
        if "Tilpasset" in sel:
            self.bf_navn_label.grid(row=1, column=0, sticky="w", pady=3)
            self.bf_navn_entry.grid(row=1, column=1, padx=(8,0), pady=3, sticky="w")
            return
        self.bf_navn_label.grid_remove()
        self.bf_navn_entry.grid_remove()
        std = F18_densitet if "F-18" in sel else F34_densitet
        self.bf_dens_var.set(std)
        self.bf_dens_hint.config(text=f"(std: {std:.3f})")
 
    # ── Kør ────────────────────────────────────────────────────────────────
    def kør(self):
        custom = [(n.get().strip(), d.get(), a.get())
                  for n, d, a in self.custom_rows
                  if n.get().strip() and d.get() != 0]
 
        inputs = {
            "pilot_v":        self.pilot_v.get(),
            "pilot_h":        self.pilot_h.get(),
            "passager":       self.passager.get(),
            "brændstof_type": self.bf_type.get(),
            "brændstof_navn": self.bf_navn_var.get(),
            "brændstof_l":    self.bf_l.get(),
            "brændstof_dens": self.bf_dens_var.get(),
            "deltahawk":      self.deltahawk.get(),
            "propel":         self.propel.get(),
            "fjern_iff":      self.fjern_iff.get(),
            "fjern_bagsæde":  self.fjern_bagsæde.get(),
            "flyt_batteri":   self.flyt_batteri.get(),
            "custom":         custom,
        }
 
        ændringer = _byg_ændringer(inputs)
 
        # ── Kald dine egne funktioner fra notebooken ──────────────────────
        auw, cg_cm, cg_pct = beregn_cg(ZFW_KG, ZFW_CG_CM, ændringer)
 
        if auw is None:
            self.status_var.set(f"✗  OVERSKRIDER MTOW (1200 kg)")
            self.status_lbl.config(fg="#c0392b")
            messagebox.showerror("MTOW overskredet",
                                 "Totalvægt overskrider maksimal startvægt (1200 kg).\n"
                                 "Reducer last eller brændstof.")
            return
 
        # Tabel
        self.tabel.config(state="normal")
        self.tabel.delete("1.0", "end")
        self.tabel.insert("end", _byg_tabel_str(auw, cg_cm, cg_pct, ændringer))
        self.tabel.config(state="disabled")
 
        # Figur — kalder din eksisterende visualiser_cg()
        if self.vis_figur.get():
            visualiser_cg(auw, cg_cm, cg_pct, self.load_case.get())
 
 
# Start GUI
app = VaegtoBalanceApp()
app.mainloop()