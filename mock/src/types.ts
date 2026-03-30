export interface SimulatorState {
  pv_kw: number;
  home_kw: number;
  battery_soc: number;
  battery_power_kw: number;
  battery_charging: boolean;
  energy_today_kwh: number;
  discharged_today_kwh: number;
  total_energy_kwh: number;
  grid_kw: number;
  grid_importing: boolean;
  forced_mode: number;
  forced_power_kw: number;
  forced_duration_min: number;
  operation_mode: number;
  charge_from_ac: number;
  max_charge_power: number;
  command_log: { timestamp: string; signals: Record<string, string> }[];
}
