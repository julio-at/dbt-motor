"""
Asset registry and plant layout (SPEC §3.4, §5.2).

PLANT-A: 2 floors, 3 tandems per floor, 4 positions per tandem.
Conveyor motors (group 2, rigid, 4-pole, 60 Hz) + mill drives (group 1, slower).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List
from generator.physics import MotorSpecs


@dataclass
class Asset:
    """Industrial motor asset."""
    asset_id: str
    device_id: str
    asset_type: str  # CONVEYOR_MOTOR | MILL_DRIVE
    plant_id: str
    floor: int
    tandem: int
    order_pos: int
    drive_id: str
    specs: MotorSpecs
    bearing_de: str = "6209"  # drive-end bearing code
    bearing_nde: str = "6209"  # non-drive-end bearing code
    relube_interval_h: float = 2000
    installed_at: datetime = None


def create_plant_a(profile: str) -> List[Asset]:
    """
    Create PLANT-A asset registry for given profile.

    Profile:
    - dev: 12 assets (10 conveyor, 2 mill)
    - demo: 24 assets (20 conveyor, 4 mill)
    - full: 24 assets (20 conveyor, 4 mill)
    """
    assets = []
    asset_idx = 1

    # Conveyor motors (group 2, rigid, 4-pole, 60 Hz nominal)
    n_conveyor = {"dev": 10, "demo": 20, "full": 20}[profile]
    for i in range(n_conveyor):
        floor = (i % 2) + 1
        tandem = ((i // 2) % 3) + 1
        order_pos = ((i // 6) % 4) + 1

        asset = Asset(
            asset_id=f"CNV-{asset_idx:03d}",
            device_id=f"VS-{1000 + asset_idx:05d}",
            asset_type="CONVEYOR_MOTOR",
            plant_id="PLANT-A",
            floor=floor,
            tandem=tandem,
            order_pos=order_pos,
            drive_id=f"VFD-{floor}-{tandem}-{order_pos}",
            specs=MotorSpecs(
                poles=4,
                rated_hz=60,
                rated_kw=5.5,
                rated_current_a=15.0,
                iso_group=2,
                foundation="RIGID",
            ),
            bearing_de="6209",
            bearing_nde="6209",
            relube_interval_h=2000,
            installed_at=datetime(2026, 1, 1),
        )
        assets.append(asset)
        asset_idx += 1

    # Mill drives (group 1, rigid, 6-pole, 50 Hz nominal)
    n_mill = {"dev": 2, "demo": 4, "full": 4}[profile]
    for i in range(n_mill):
        floor = (i % 2) + 1
        tandem = 1  # concentrated in tandem 1
        order_pos = ((i + 1) % 4) + 1

        asset = Asset(
            asset_id=f"MILL-{asset_idx:03d}",
            device_id=f"VS-{2000 + asset_idx:05d}",
            asset_type="MILL_DRIVE",
            plant_id="PLANT-A",
            floor=floor,
            tandem=tandem,
            order_pos=order_pos,
            drive_id=f"VFD-{floor}-{tandem}-MILL",
            specs=MotorSpecs(
                poles=6,
                rated_hz=50,
                rated_kw=22,
                rated_current_a=50.0,
                iso_group=1,
                foundation="RIGID",
            ),
            bearing_de="6309",
            bearing_nde="6309",
            relube_interval_h=3000,
            installed_at=datetime(2026, 1, 1),
        )
        assets.append(asset)
        asset_idx += 1

    return assets


def get_asset_by_id(assets: List[Asset], asset_id: str) -> Asset:
    """Find asset by asset_id."""
    for a in assets:
        if a.asset_id == asset_id:
            return a
    return None


def get_asset_by_device_id(assets: List[Asset], device_id: str) -> Asset:
    """Find asset by device_id."""
    for a in assets:
        if a.device_id == device_id:
            return a
    return None
