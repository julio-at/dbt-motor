"""
Signal model and components (SPEC §5.3, §5.4).

Each axis is a sum of components (f_i, v_rms_i).
Baseline: 1x residual unbalance + load-dependent noise.
Faults: add bearing tones, harmonics, temperature effects.
"""

from dataclasses import dataclass, field
from typing import List, Tuple
import math
import numpy as np
from generator.physics import MotorSpecs, v_rms_to_d_pp, running_speed


@dataclass
class SignalComponent:
    """Sinusoidal component: (frequency, velocity RMS)."""
    frequency_hz: float
    v_rms_mm_s: float

    def amplitude_um_pp(self) -> float:
        """Convert v_rms to displacement peak-to-peak."""
        return v_rms_to_d_pp(self.v_rms_mm_s, self.frequency_hz)


@dataclass
class AxisSignal:
    """Signal on one axis (X, Y, or Z)."""
    components: List[SignalComponent] = field(default_factory=list)
    axis_factor: float = 1.0  # baseline scaling (X=1.0, Y=0.85, Z=0.3)
    noise_pct: float = 5.0  # noise as % of total v_rms

    def dominant_frequency(self) -> float:
        """Frequency of component with max displacement."""
        if not self.components:
            return 0
        return max(self.components, key=lambda c: c.amplitude_um_pp()).frequency_hz

    def total_v_rms(self) -> float:
        """Total velocity RMS (RSS of components)."""
        if not self.components:
            return 0
        return math.sqrt(sum(c.v_rms_mm_s ** 2 for c in self.components))

    def total_amplitude_um_pp(self, rng: np.random.Generator) -> float:
        """Total displacement peak-to-peak with noise."""
        if not self.components:
            return 0
        d_pp_components = [c.amplitude_um_pp() for c in self.components]
        d_pp = math.sqrt(sum(d ** 2 for d in d_pp_components))
        noise = rng.normal(0, d_pp * self.noise_pct / 100)
        return max(0, d_pp + noise)


@dataclass
class MotorSignal:
    """Complete signal: X, Y, Z axes."""
    x_axis: AxisSignal = field(default_factory=AxisSignal)
    y_axis: AxisSignal = field(default_factory=AxisSignal)
    z_axis: AxisSignal = field(default_factory=AxisSignal)


def baseline_signal(output_hz: float, specs: MotorSpecs, rng: np.random.Generator) -> MotorSignal:
    """
    Baseline healthy signal: 1x residual unbalance + speed-dependent scaling.

    SPEC §5.3:
    - Healthy baseline: 1x residual unbalance, velocity 0.6–1.2 mm/s at nominal speed
    - Scaling with speed (VFD): v_rms ∝ output_hz (normalized to nominal)
    - Axis factors: X 1.0, Y 0.85, Z 0.3
    """
    f_sync, f_1x, _ = running_speed(output_hz, specs)
    speed_factor = output_hz / specs.rated_hz

    # 1x unbalance velocity at nominal speed (0.6-1.2 mm/s)
    v_1x_nominal = rng.uniform(0.6, 1.2)
    v_1x = v_1x_nominal * speed_factor

    sig = MotorSignal()
    sig.x_axis.components = [SignalComponent(f_1x, v_1x * 1.0)]
    sig.x_axis.axis_factor = 1.0
    sig.y_axis.components = [SignalComponent(f_1x, v_1x * 0.85)]
    sig.y_axis.axis_factor = 0.85
    sig.z_axis.components = [SignalComponent(f_1x, v_1x * 0.3)]
    sig.z_axis.axis_factor = 0.3

    return sig


def fault_unbalance_growth(base_sig: MotorSignal, progress: float, rng: np.random.Generator) -> MotorSignal:
    """
    UNBALANCE_GROWTH: 1x radial (X, Y) grows ×3 over the period; Z stays low.

    Args:
        base_sig: baseline signal
        progress: 0.0 to 1.0 (start to end of fault window)
        rng: random number generator
    """
    sig = MotorSignal()
    growth_factor = 1 + (3 - 1) * progress

    for comp in base_sig.x_axis.components:
        sig.x_axis.components.append(SignalComponent(comp.frequency_hz, comp.v_rms_mm_s * growth_factor))
    for comp in base_sig.y_axis.components:
        sig.y_axis.components.append(SignalComponent(comp.frequency_hz, comp.v_rms_mm_s * growth_factor))
    for comp in base_sig.z_axis.components:
        sig.z_axis.components.append(SignalComponent(comp.frequency_hz, comp.v_rms_mm_s))

    return sig


def fault_bearing_outer_race(base_sig: MotorSignal, bpfo: float, progress: float,
                             rng: np.random.Generator) -> MotorSignal:
    """
    BEARING_OUTER_RACE: BPFO + harmonics rise exponentially in spectra.
    Late: becomes dominant non-sync, noise floor rises, temperature rises.
    """
    sig = MotorSignal()

    # BPFO grows exponentially
    v_bpfo = 0.01 * math.exp(5 * progress)  # starts small, explodes near end

    for comp in base_sig.x_axis.components:
        sig.x_axis.components.append(comp)
    sig.x_axis.components.append(SignalComponent(bpfo, v_bpfo))
    if progress > 0.7:
        sig.x_axis.components.append(SignalComponent(2 * bpfo, v_bpfo * 0.6))
        sig.x_axis.components.append(SignalComponent(3 * bpfo, v_bpfo * 0.4))

    for comp in base_sig.y_axis.components:
        sig.y_axis.components.append(comp)
    sig.y_axis.components.append(SignalComponent(bpfo, v_bpfo * 0.7))

    for comp in base_sig.z_axis.components:
        sig.z_axis.components.append(comp)

    return sig


def fault_misalignment(base_sig: MotorSignal, f_1x: float, progress: float,
                       rng: np.random.Generator) -> MotorSignal:
    """
    MISALIGNMENT_AFTER_MAINT: step change after maintenance.
    Z rises to ≥ 0.6·max(X,Y), 2x appears.
    """
    sig = MotorSignal()

    # X, Y unchanged
    sig.x_axis.components = list(base_sig.x_axis.components)
    sig.y_axis.components = list(base_sig.y_axis.components)

    max_radial = max(
        max((c.v_rms_mm_s for c in base_sig.x_axis.components), default=0),
        max((c.v_rms_mm_s for c in base_sig.y_axis.components), default=0),
    )

    # Z rises to 0.6*max(X,Y) + add 2x
    v_z = max_radial * 0.6
    sig.z_axis.components = [SignalComponent(f_1x, v_z)]
    sig.z_axis.components.append(SignalComponent(2 * f_1x, v_z * 0.4))

    return sig


def fault_lubrication_loss(base_sig: MotorSignal, progress: float,
                           rng: np.random.Generator) -> Tuple[MotorSignal, float]:
    """
    LUBRICATION_LOSS: temperature ramps +20°C over ~12 h at stable speed.
    Mild bearing-band rise; relube event resets.

    Returns:
        (signal, temp_rise_c)
    """
    sig = MotorSignal()
    sig.x_axis.components = list(base_sig.x_axis.components)
    sig.y_axis.components = list(base_sig.y_axis.components)
    sig.z_axis.components = list(base_sig.z_axis.components)

    # Small bearing band energy rise
    if progress > 0.3:
        sig.x_axis.components.append(SignalComponent(1.2, 0.05 * progress))
        sig.y_axis.components.append(SignalComponent(1.2, 0.03 * progress))

    temp_rise = 20 * progress
    return sig, temp_rise
