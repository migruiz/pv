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

  // Inverter settings (set by Python API or UI)
  operation_mode: number; // 2=Max self-consumption, 5=TOU
  charge_from_ac: number; // 0=Disabled, 1=Enabled
  max_charge_power: number; // 200-2500 W

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
  operation_mode: 5,
  charge_from_ac: 1,
  max_charge_power: 2500,
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

/** Readings in the inverter's register names and units, as the Python API's InverterReader expects. */
export function registers(): Record<string, number> {
  const meterW = (state.grid_importing ? -state.grid_kw : state.grid_kw) * 1000;
  return {
    input_power: state.pv_kw * 1000,
    // The meter sits at the grid connection: inverter output = home + export (- import)
    active_power: state.home_kw * 1000 + meterW,
    power_meter_active_power: meterW, // positive = exporting
    storage_charge_discharge_power: (state.battery_charging ? 1 : -1) * state.battery_power_kw * 1000, // positive = charging
    storage_state_of_capacity: state.battery_soc,
    daily_yield_energy: state.energy_today_kwh,
    storage_current_day_discharge_capacity: state.discharged_today_kwh,
    storage_working_mode_settings: state.operation_mode,
    storage_charge_from_grid_function: state.charge_from_ac,
    storage_maximum_charging_power: state.max_charge_power,
    accumulated_yield_energy: state.total_energy_kwh,
  };
}

/** Register writes from the Python API: the forced charge/discharge settings and command. */
export function writeRegisters(values: Record<string, number>) {
  for (const [name, value] of Object.entries(values)) {
    switch (name) {
      case "storage_forcible_discharge_power":
      case "storage_forcible_charge_power":
        state.forced_power_kw = value / 1000;
        break;
      case "storage_forced_charging_and_discharging_period":
        state.forced_duration_min = value;
        break;
      case "storage_forcible_charge_discharge_setting_mode": // time or SOC target: not simulated
        break;
      case "forcible_charge_discharge_write": // 0=Stop, 1=Charge, 2=Discharge
        applyForcedCommand(value);
        break;
      default:
        throw new Error(`Unknown register ${name}`);
    }
  }
}

function applyForcedCommand(mode: number) {
  state.forced_mode = mode;
  if (mode === 0) {
    state.battery_power_kw = 0;
    stopSocSimulation();
  } else {
    state.battery_power_kw = state.forced_power_kw;
    state.battery_charging = mode === 1;
    startSocSimulation();
  }
  recalculateGrid();

  state.command_log.push({
    timestamp: new Date().toISOString(),
    signals: {
      charge_discharge_mode: String(mode),
      ...(mode === 0 ? {} : { forced_power_kw: state.forced_power_kw.toFixed(3), period_min: String(state.forced_duration_min) }),
    },
  });
  // Keep last 50 entries
  if (state.command_log.length > 50) {
    state.command_log = state.command_log.slice(-50);
  }
}
