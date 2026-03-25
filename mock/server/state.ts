/** In-memory solar system simulator state with energy balance and SOC simulation. */

export interface CommandEntry {
  timestamp: string;
  signals: Record<string, string>;
}

export interface SimulatorState {
  // User-controllable
  pv_kw: number;
  home_kw: number;
  battery_soc: number;
  battery_power_kw: number;
  battery_charging: boolean;

  // Cumulative stats
  energy_today_kwh: number;
  discharged_today_kwh: number;
  total_energy_kwh: number;

  // Auto-calculated
  grid_kw: number;
  grid_importing: boolean;

  // Forced command state (set by Python API)
  forced_mode: number; // 0=Stop, 1=Charge, 2=Discharge
  forced_power_kw: number;
  forced_duration_min: number;

  // Command log
  command_log: CommandEntry[];
}

const BATTERY_CAPACITY_KWH = 4.8;
const SOC_TICK_INTERVAL_MS = 10_000; // 10 seconds

const DEFAULT_STATE: Omit<SimulatorState, "grid_kw" | "grid_importing"> = {
  pv_kw: 1.5,
  home_kw: 0.3,
  battery_soc: 80,
  battery_power_kw: 0,
  battery_charging: false,
  energy_today_kwh: 20,
  discharged_today_kwh: 3,
  total_energy_kwh: 600,
  forced_mode: 0,
  forced_power_kw: 0,
  forced_duration_min: 0,
  command_log: [],
};

let state: SimulatorState = { ...DEFAULT_STATE, grid_kw: 0, grid_importing: false };
recalculateGrid();

let socTimer: ReturnType<typeof setInterval> | null = null;

// ---------------------------------------------------------------------------
// Energy balance
// ---------------------------------------------------------------------------

function recalculateGrid() {
  const batteryNet = state.battery_charging
    ? -state.battery_power_kw // charging consumes from PV/grid
    : state.battery_power_kw; // discharging adds to supply

  const net = state.pv_kw + batteryNet - state.home_kw;

  if (net >= 0) {
    state.grid_kw = net;
    state.grid_importing = false; // exporting
  } else {
    state.grid_kw = Math.abs(net);
    state.grid_importing = true; // importing
  }
}

// ---------------------------------------------------------------------------
// SOC simulation tick
// ---------------------------------------------------------------------------

function startSocSimulation() {
  stopSocSimulation();
  socTimer = setInterval(() => {
    if (state.forced_mode === 0) {
      stopSocSimulation();
      return;
    }

    const hoursElapsed = SOC_TICK_INTERVAL_MS / 1000 / 3600;
    const energyDelta = state.forced_power_kw * hoursElapsed; // kWh
    const socDelta = (energyDelta / BATTERY_CAPACITY_KWH) * 100;

    if (state.forced_mode === 2) {
      // Discharging
      state.battery_soc = Math.max(0, state.battery_soc - socDelta);
      state.battery_power_kw = state.forced_power_kw;
      state.battery_charging = false;
      state.discharged_today_kwh += energyDelta;
    } else if (state.forced_mode === 1) {
      // Charging
      state.battery_soc = Math.min(100, state.battery_soc + socDelta);
      state.battery_power_kw = state.forced_power_kw;
      state.battery_charging = true;
    }

    recalculateGrid();

    // Stop if SOC hits limits
    if (
      (state.forced_mode === 2 && state.battery_soc <= 0) ||
      (state.forced_mode === 1 && state.battery_soc >= 100)
    ) {
      state.forced_mode = 0;
      state.battery_power_kw = 0;
      stopSocSimulation();
    }
  }, SOC_TICK_INTERVAL_MS);
}

function stopSocSimulation() {
  if (socTimer) {
    clearInterval(socTimer);
    socTimer = null;
  }
}

// ---------------------------------------------------------------------------
// Signal IDs → human-readable names
// ---------------------------------------------------------------------------

const SIGNAL_NAMES: Record<string, string> = {
  "230320245": "charge_discharge_mode",
  "230320259": "forced_power_kw",
  "230320257": "setting_mode",
  "230320281": "forced_period_min",
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function getState(): SimulatorState {
  return { ...state, command_log: [...state.command_log] };
}

export function updateState(patch: Partial<SimulatorState>) {
  const { grid_kw, grid_importing, command_log, ...allowed } = patch;
  Object.assign(state, allowed);
  recalculateGrid();
}

export function resetState() {
  stopSocSimulation();
  state = { ...DEFAULT_STATE, command_log: [], grid_kw: 0, grid_importing: false };
  recalculateGrid();
}

export function handleConfigSignals(
  dn: string,
  changeValues: { id: string; value: string }[]
) {
  // Log the command
  const decoded: Record<string, string> = {};
  for (const { id, value } of changeValues) {
    decoded[SIGNAL_NAMES[id] || id] = value;
  }
  state.command_log.push({
    timestamp: new Date().toISOString(),
    signals: decoded,
  });
  // Keep last 50 entries
  if (state.command_log.length > 50) {
    state.command_log = state.command_log.slice(-50);
  }

  // Apply signal values
  for (const { id, value } of changeValues) {
    switch (id) {
      case "230320245": // charge_discharge_mode
        state.forced_mode = parseInt(value);
        if (state.forced_mode === 0) {
          state.battery_power_kw = 0;
          stopSocSimulation();
        } else {
          startSocSimulation();
        }
        break;
      case "230320259": // forced_power_kw
        state.forced_power_kw = parseFloat(value);
        break;
      case "230320257": // setting_mode (ignored for simulation)
        break;
      case "230320281": // forced_period_min
        state.forced_duration_min = parseInt(value);
        break;
    }
  }

  recalculateGrid();
  return { success: true, failCode: 0 };
}
