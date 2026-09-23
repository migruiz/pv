/** Express routes for the React UI, and the inverter registers the Python API reads and writes. */

import { Router, json } from "express";
import { getState, updateState, resetState, registers, writeRegisters } from "./state.js";

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
// Routes for the Python API (inverter/simulator.py stands in for the Modbus client)
// ===================================================================

router.get("/mock/registers", (_req, res) => {
  res.json(registers());
});

router.post("/mock/registers", (req, res) => {
  try {
    writeRegisters(req.body);
    res.json({ success: true });
  } catch (err) {
    res.status(400).json({ error: String(err) });
  }
});
