/** Express routes for both the React UI and the Python MockSession. */

import { Router, json } from "express";
import { getState, updateState, resetState, handleConfigSignals } from "./state.js";

export const router = Router();
router.use(json());

// ===================================================================
// Routes for React UI
// ===================================================================

router.get("/api/state", (_req, res) => {
  res.json(getState());
});

router.patch("/api/state", (req, res) => {
  updateState(req.body);
  res.json(getState());
});

router.post("/api/state/reset", (_req, res) => {
  resetState();
  res.json(getState());
});

// ===================================================================
// Routes for Python MockSession
// ===================================================================

router.get("/mock/session-active", (_req, res) => {
  res.json({ active: true });
});

router.get("/mock/plant-ids", (_req, res) => {
  res.json({ plant_ids: ["NE=239198726"] });
});

router.get("/mock/power-status", (_req, res) => {
  const s = getState();
  res.json({
    current_power_kw: s.pv_kw,
    energy_today_kwh: s.energy_today_kwh,
    energy_kwh: s.total_energy_kwh,
  });
});

router.get("/mock/battery-stats/:dn", (_req, res) => {
  const s = getState();
  res.json({
    state_of_charge: s.battery_soc,
    rated_capacity: 5.0,
    operating_status: "Operating",
    backup_time: "0.0",
    bus_voltage: 600,
    total_charged_today_kwh: 0,
    total_discharged_today_kwh: s.discharged_today_kwh,
    current_charge_discharge_kw: s.battery_power_kw,
  });
});

router.get("/mock/plant-flow/:id", (_req, res) => {
  const s = getState();

  // Build the exact FusionSolar flow JSON structure that _parse_flow() expects
  const nodes = [
    { mocId: 20812, id: "pv_node", value: String(s.pv_kw), deviceTips: {} },
    {
      mocId: 20815,
      id: "bat_node",
      value: String(s.battery_power_kw),
      deviceTips: { SOC: String(s.battery_soc) },
    },
    { mocId: 90002, id: "home_node", value: String(s.home_kw), deviceTips: {} },
  ];

  const links: object[] = [];

  // Grid link
  if (s.grid_importing) {
    links.push({
      description: { label: "sell.power", value: `${s.grid_kw} kW` },
      fromNode: "grid_node",
      toNode: "inverter_node",
      flowing: "FORWARD",
    });
  } else {
    links.push({
      description: { label: "buy.power", value: `${s.grid_kw} kW` },
      fromNode: "inverter_node",
      toNode: "grid_node",
      flowing: "FORWARD",
    });
  }

  // Battery link
  if (s.battery_charging) {
    // Inverter → battery = charging
    links.push({
      description: { label: "battery", value: `${s.battery_power_kw} kW` },
      fromNode: "inverter_node",
      toNode: "bat_node",
      flowing: "FORWARD",
    });
  } else {
    // Battery → inverter = discharging
    links.push({
      description: { label: "battery", value: `${s.battery_power_kw} kW` },
      fromNode: "bat_node",
      toNode: "inverter_node",
      flowing: "FORWARD",
    });
  }

  res.json({ data: { flow: { nodes, links } } });
});

router.get("/mock/inverter-settings", (_req, res) => {
  const s = getState();
  res.json({
    operation_mode: s.operation_mode,
    charge_from_ac: s.charge_from_ac,
    max_charge_power: s.max_charge_power,
  });
});

router.post("/mock/config-signals", (req, res) => {
  const { dn, changeValues } = req.body;
  const result = handleConfigSignals(dn, changeValues);
  res.json(result);
});
