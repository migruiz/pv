"""Dashboard endpoint — combined energy flow + stats for the Android app."""

from fastapi import APIRouter, Depends, HTTPException

from auth import require_api_key
from config import BATTERY_DN
from dependencies import get_session
from session import SolarSession

router = APIRouter(dependencies=[Depends(require_api_key)])


def _parse_flow(flow_data: dict) -> dict:
    """Extract key power values from the FusionSolar plant flow response."""
    pv_kw = 0.0
    battery_soc = 0.0
    battery_kw = 0.0
    grid_kw = 0.0
    home_kw = 0.0

    data = flow_data.get("data", {})
    flow = data.get("flow", {})
    nodes = flow.get("nodes", [])
    links = flow.get("links", [])

    for node in nodes:
        moc_id = node.get("mocId", 0)
        value = node.get("value")
        tips = node.get("deviceTips", {})
        if moc_id == 20812 and value is not None:   # PV / String
            pv_kw = float(value)
        elif moc_id == 20815:                        # Battery / Energy Store
            if value is not None:
                battery_kw = float(value)
            if "SOC" in tips:
                battery_soc = float(tips["SOC"])
        elif moc_id == 90002 and value is not None:  # Home / Electrical Load
            home_kw = float(value)

    # Grid power and directions from links
    grid_importing = False
    battery_charging = False

    for link in links:
        desc = link.get("description", {})
        label = desc.get("label", "")
        val_str = desc.get("value", "")

        # Grid link: "buy.power" = grid buys from you = exporting
        #            "sell.power" = grid sells to you = importing
        if "buy" in label:
            grid_importing = False
            try:
                grid_kw = float(val_str.replace("kW", "").strip())
            except (ValueError, AttributeError):
                pass
        elif "sell" in label or "input" in label:
            grid_importing = True
            try:
                grid_kw = float(val_str.replace("kW", "").strip())
            except (ValueError, AttributeError):
                pass

        # Battery link (inverter → battery = charging)
        from_node = link.get("fromNode", "")
        to_node = link.get("toNode", "")
        for node in nodes:
            if node.get("mocId") == 20815:
                bat_id = node.get("id", "")
                if to_node == bat_id and link.get("flowing") == "FORWARD":
                    battery_charging = True
                elif from_node == bat_id and link.get("flowing") == "FORWARD":
                    battery_charging = False

    return {
        "pv_kw": pv_kw,
        "battery_soc": battery_soc,
        "battery_kw": battery_kw,
        "grid_kw": grid_kw,
        "home_kw": home_kw,
        "grid_importing": grid_importing,
        "battery_charging": battery_charging,
    }


@router.get("/dashboard")
async def get_dashboard(session: SolarSession = Depends(get_session)):
    """Combined dashboard data for the Android app."""
    try:
        plant_ids = await session.call("get_plant_ids")
        plant_id = plant_ids[0] if plant_ids else None

        ps = await session.call("get_power_status")
        b = await session.call("get_battery_basic_stats", BATTERY_DN)

        flow_values = {}
        if plant_id:
            flow_data = await session.call("get_plant_flow", plant_id)
            flow_values = _parse_flow(flow_data)

        # Inverter settings (operation mode, AC charge, max charge power)
        try:
            inv = await session.get_inverter_settings(BATTERY_DN)
        except Exception:
            inv = {"operation_mode": 5, "charge_from_ac": 1, "max_charge_power": 2500}

        return {
            "pv_kw": flow_values.get("pv_kw", ps.current_power_kw),
            "battery_soc": flow_values.get("battery_soc", b.state_of_charge),
            "battery_charge_discharge_kw": flow_values.get("battery_kw", b.current_charge_discharge_kw),
            "battery_charging": flow_values.get("battery_charging", False),
            "grid_kw": flow_values.get("grid_kw", 0.0),
            "grid_importing": flow_values.get("grid_importing", False),
            "home_kw": flow_values.get("home_kw", 0.0),
            "energy_today_kwh": ps.energy_today_kwh,
            "discharged_today_kwh": b.total_discharged_today_kwh,
            "total_energy_kwh": ps.energy_kwh,
            "operation_mode": inv.get("operation_mode", 5),
            "charge_from_ac": inv.get("charge_from_ac", 1),
            "max_charge_power": inv.get("max_charge_power", 2500),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
