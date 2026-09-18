"""
Physics and formulas (SPEC §4).

Displacement ↔ velocity ↔ acceleration conversions, bearing defect frequencies, running speed.
"""

import math
from dataclasses import dataclass


@dataclass
class MotorSpecs:
    """Motor parameters for physics calculations."""
    poles: int
    rated_hz: float
    rated_kw: float
    rated_current_a: float = 20.0
    slip: float = 0.02
    iso_group: int = 2
    foundation: str = "RIGID"


def d_pp_to_v_rms(d_pp_um: float, f_hz: float) -> float:
    """
    Displacement peak-to-peak (µm) to velocity RMS (mm/s).

    Formula (SPEC §4.1):
    v_rms_mm_s = 2π · f · d_peak_um · 1e-3 / √2  ≈ 2.2214e-3 · f · d_pp

    Args:
        d_pp_um: displacement peak-to-peak (µm)
        f_hz: dominant frequency (Hz)

    Returns:
        velocity RMS (mm/s)
    """
    d_peak_um = d_pp_um / 2
    return (2 * math.pi * f_hz * d_peak_um * 1e-3) / math.sqrt(2)


def v_rms_to_d_pp(v_rms_mm_s: float, f_hz: float) -> float:
    """Inverse: velocity RMS (mm/s) to displacement peak-to-peak (µm)."""
    if f_hz == 0:
        return 0
    d_peak_um = (v_rms_mm_s * math.sqrt(2)) / (2 * math.pi * f_hz * 1e-3)
    return d_peak_um * 2


def v_rms_to_a_rms(v_rms_mm_s: float, f_hz: float) -> float:
    """
    Velocity RMS to acceleration RMS.

    Formula (SPEC §4.1):
    a_rms_mm_s2 = (2π · f)² · d_peak_um · 1e-3 / √2
    """
    if f_hz == 0:
        return 0
    d_peak_um = (v_rms_mm_s * math.sqrt(2)) / (2 * math.pi * f_hz * 1e-3)
    return ((2 * math.pi * f_hz) ** 2 * d_peak_um * 1e-3) / math.sqrt(2)


def running_speed(output_hz: float, specs: MotorSpecs) -> tuple[float, float, int]:
    """
    Calculate synchronous and shaft speeds from VFD output frequency.

    Args:
        output_hz: VFD output frequency (Hz)
        specs: motor specifications

    Returns:
        (f_sync_hz, f_1x_hz, speed_band)

    Formula (SPEC §4.2):
    - f_sync = output_hz · 2 / poles
    - f_1x = f_sync · (1 - slip)
    - speed_band = floor(output_hz / 5)  (default band_width_hz=5)
    """
    f_sync = (output_hz * 2) / specs.poles
    f_1x = f_sync * (1 - specs.slip)
    speed_band = int(output_hz / 5)
    return f_sync, f_1x, speed_band


def load_pct(v_avg: float, i_avg: float, pf: float, rated_kw: float) -> float:
    """
    Load as percentage of rated power.

    Formula (SPEC §4.2b):
    p_kw = √3 · v_avg · i_avg · pf / 1000
    load_pct = p_kw / rated_kw · 100
    """
    p_kw = (math.sqrt(3) * v_avg * i_avg * pf) / 1000
    return (p_kw / rated_kw) * 100


def current_pct(current_lx: float, rated_current_a: float) -> float:
    """Current as percentage of rated current."""
    return (current_lx / rated_current_a) * 100


def voltage_unbalance(v_l1, v_l2, v_l3) -> float:
    """
    Voltage unbalance (NEMA-style, SPEC §4.2c).

    Formula:
    v_avg = mean(V_lx)
    voltage_unbalance_pct = max(|V_lx − v_avg|) / v_avg · 100
    """
    voltages = [v_l1, v_l2, v_l3]
    v_avg = sum(voltages) / len(voltages)
    if v_avg == 0:
        return 0
    return (max(abs(v - v_avg) for v in voltages) / v_avg) * 100


def current_unbalance(i_l1, i_l2, i_l3) -> float:
    """Current unbalance (NEMA-style, SPEC §4.2c)."""
    currents = [i_l1, i_l2, i_l3]
    i_avg = sum(currents) / len(currents)
    if i_avg == 0:
        return 0
    return (max(abs(i - i_avg) for i in currents) / i_avg) * 100


def synchronous_check(f_dominant: float, f_1x: float) -> tuple[bool, int]:
    """
    Check if dominant frequency is synchronous (harmonic of 1x).

    Formula (SPEC §4.3):
    k = f_dominant / f_1x
    synchronous if |k - round(k)| ≤ 0.03 and 1 ≤ round(k) ≤ 4

    Returns:
        (is_synchronous, harmonic_order)
    """
    if f_1x == 0:
        return False, 0
    k = f_dominant / f_1x
    k_round = round(k)
    is_sync = abs(k - k_round) <= 0.03 and 1 <= k_round <= 4
    return is_sync, k_round if is_sync else 0


def bearing_defect_frequencies(f_1x: float, n: int = 8, bd: float = None,
                               pd: float = None, theta: float = None) -> dict[str, float]:
    """
    Bearing defect frequencies (SPEC §4.4).

    With geometry (Bd, Pd, θ):
    - FTF  = fr/2 · (1 − Bd/Pd·cosθ)
    - BPFO = n/2 · fr · (1 − Bd/Pd·cosθ)
    - BPFI = n/2 · fr · (1 + Bd/Pd·cosθ)
    - BSF  = Pd/(2·Bd) · fr · (1 − (Bd/Pd·cosθ)²)

    Without geometry (rule of thumb):
    - FTF ≈ 0.4·fr
    - BPFO ≈ 0.4·n·fr
    - BPFI ≈ 0.6·n·fr

    Args:
        f_1x: shaft speed (Hz)
        n: number of rolling elements (default 8)
        bd: ball diameter (mm, optional)
        pd: pitch diameter (mm, optional)
        theta: contact angle (degrees, optional)

    Returns:
        dict with FTF, BPFO, BPFI, BSF (Hz)
    """
    if f_1x == 0:
        return {"FTF": 0, "BPFO": 0, "BPFI": 0, "BSF": 0}

    if bd is not None and pd is not None and theta is not None:
        theta_rad = math.radians(theta)
        cos_theta = math.cos(theta_rad)
        ratio = bd / pd
        term = ratio * cos_theta

        ftf = (f_1x / 2) * (1 - term)
        bpfo = (n / 2) * f_1x * (1 - term)
        bpfi = (n / 2) * f_1x * (1 + term)
        bsf = (pd / (2 * bd)) * f_1x * (1 - term ** 2)
    else:
        ftf = 0.4 * f_1x
        bpfo = 0.4 * n * f_1x
        bpfi = 0.6 * n * f_1x
        bsf = (pd / (2 * bd)) * f_1x * (1 - ((bd / pd) * math.cos(math.radians(theta))) ** 2) \
              if (bd and pd and theta) else 0.3 * f_1x

    return {"FTF": ftf, "BPFO": bpfo, "BPFI": bpfi, "BSF": bsf}


def dew_point(temp_c: float, rh_pct: float) -> float:
    """
    Dew point (Magnus formula, SPEC §4.5).

    γ = ln(RH/100) + (17.62·T)/(243.12 + T)
    T_dew = 243.12·γ / (17.62 − γ)
    """
    if rh_pct <= 0 or rh_pct > 100:
        return temp_c
    rh_frac = rh_pct / 100
    gamma = math.log(rh_frac) + (17.62 * temp_c) / (243.12 + temp_c)
    if 17.62 - gamma == 0:
        return temp_c
    return (243.12 * gamma) / (17.62 - gamma)


def grease_thermal_aging(hours: float, temp_c: float) -> float:
    """
    Equivalent aging hours (grease thermal aging, SPEC §4.6).

    Grease life halves every 15°C above 70°C.
    h_eq = Σ Δt_h · 2^((T − 70)/15)  for T > 70, else Δt_h
    """
    if temp_c <= 70:
        return hours
    return hours * (2 ** ((temp_c - 70) / 15))
