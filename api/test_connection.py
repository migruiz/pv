"""
FusionSolar Connection Test
Tests connectivity to your Huawei FusionSolar PV installation.

Usage:
    1. Edit .env file with your credentials
    2. python test_connection.py
"""

import os
import sys

from dotenv import load_dotenv
from fusion_solar_py.client import FusionSolarClient

load_dotenv()


HUAWEI_SUBDOMAIN = "uni003eu5"


def main():
    username = os.environ.get("FUSIONSOLAR_USER")
    password = os.environ.get("FUSIONSOLAR_PASS")

    if not username or not password:
        print("ERROR: Set environment variables FUSIONSOLAR_USER and FUSIONSOLAR_PASS")
        print("  e.g.:  set FUSIONSOLAR_USER=soniablanco")
        print("         set FUSIONSOLAR_PASS=YourPassword")
        sys.exit(1)

    print(f"[1/6] Connecting to FusionSolar ({HUAWEI_SUBDOMAIN}.fusionsolar.huawei.com)...")
    try:
        client = FusionSolarClient(
            username=username,
            password=password,
            huawei_subdomain=HUAWEI_SUBDOMAIN,
        )
        print("  -> Login successful!\n")
    except Exception as e:
        print(f"  -> Login FAILED: {e}")
        sys.exit(1)

    # --- Power Status (aggregate) ---
    print("[2/6] Fetching power status (aggregate across all plants)...")
    try:
        status = client.get_power_status()
        print(f"  Current power:  {status.current_power_kw} kW")
        print(f"  Energy today:   {status.energy_today_kwh} kWh")
        print(f"  Total energy:   {status.energy_kwh} kWh\n")
    except Exception as e:
        print(f"  -> Failed: {e}\n")

    # --- Station List ---
    print("[3/6] Fetching station list...")
    try:
        stations = client.get_station_list()
        print(f"  Found {len(stations)} station(s):")
        for s in stations:
            name = s.get("stationName", s.get("dn", "unknown"))
            capacity = s.get("installedCapacity", "?")
            print(f"    - {name}  (capacity: {capacity} kWp)")
        print()
    except Exception as e:
        print(f"  -> Failed: {e}\n")

    # --- Plant IDs & Current Plant Data ---
    print("[4/6] Fetching plant IDs and real-time plant data...")
    plant_ids = []
    try:
        plant_ids = client.get_plant_ids()
        print(f"  Plant IDs: {plant_ids}")
        for pid in plant_ids:
            data = client.get_current_plant_data(pid)
            print(f"  Plant {pid}:")
            if isinstance(data, dict):
                for key in ("realTimePower", "cumulativeEnergy", "dailyEnergy",
                            "monthEnergy", "yearEnergy"):
                    if key in data:
                        print(f"    {key}: {data[key]}")
        print()
    except Exception as e:
        print(f"  -> Failed: {e}\n")

    # --- Device List ---
    print("[5/6] Fetching devices...")
    try:
        devices = client.get_device_ids()
        print(f"  Found {len(devices)} device(s):")
        for d in devices:
            dev_type = d.get("type", d.get("devTypeId", "?"))
            dev_dn = d.get("deviceDn", d.get("dn", "?"))
            dev_name = d.get("name", d.get("devName", dev_dn))
            print(f"    - [{dev_type}] {dev_name}  (dn: {dev_dn})")
        print()
    except Exception as e:
        print(f"  -> Failed: {e}\n")

    # --- Battery Info (if available) ---
    print("[6/6] Checking battery status...")
    if plant_ids:
        try:
            battery_ids = client.get_battery_ids(plant_ids[0])
            if battery_ids:
                print(f"  Battery IDs: {battery_ids}")
                for bid in battery_ids:
                    batt = client.get_battery_basic_stats(bid)
                    print(f"  Battery {bid}:")
                    print(f"    SOC:              {batt.state_of_charge}%")
                    print(f"    Rated capacity:   {batt.rated_capacity}")
                    print(f"    Status:           {batt.operating_status}")
                    print(f"    Charged today:    {batt.total_charged_today_kwh} kWh")
                    print(f"    Discharged today: {batt.total_discharged_today_kwh} kWh")
                    print(f"    Current power:    {batt.current_charge_discharge_kw} kW")
            else:
                print("  No batteries found.")
            print()
        except Exception as e:
            print(f"  -> Failed: {e}\n")
    else:
        print("  Skipped (no plant IDs).\n")

    # --- Cleanup ---
    try:
        client.log_out()
        print("Session closed. All tests complete!")
    except Exception:
        print("All tests complete!")


if __name__ == "__main__":
    main()
