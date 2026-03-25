import type { SimulatorState } from "../types";
import { PvSlider } from "./PvSlider";
import { HomeConsumption } from "./HomeConsumption";
import { BatteryControl } from "./BatteryControl";
import { GridDisplay } from "./GridDisplay";
import { StatsPanel } from "./StatsPanel";
import { CommandLog } from "./CommandLog";

interface Props {
  state: SimulatorState;
  onUpdate: (patch: Partial<SimulatorState>) => void;
  onReset: () => void;
}

export function ControlPanel({ state, onUpdate, onReset }: Props) {
  return (
    <div className="panel">
      <header>
        <h1>PV Mock Simulator</h1>
        <button className="reset-btn" onClick={onReset}>
          Reset
        </button>
      </header>

      <div className="layout">
        <div className="controls">
          <PvSlider
            value={state.pv_kw}
            onChange={(v) => onUpdate({ pv_kw: v })}
          />
          <HomeConsumption
            value={state.home_kw}
            onChange={(v) => onUpdate({ home_kw: v })}
          />
          <BatteryControl
            soc={state.battery_soc}
            power={state.battery_power_kw}
            charging={state.battery_charging}
            forcedMode={state.forced_mode}
            onSocChange={(v) => onUpdate({ battery_soc: v })}
            onPowerChange={(v) => onUpdate({ battery_power_kw: v })}
            onDirectionChange={(v) => onUpdate({ battery_charging: v })}
          />
        </div>

        <div className="info">
          <div className="info-section">
            <h3>Grid (auto-calculated)</h3>
            <GridDisplay
              gridKw={state.grid_kw}
              importing={state.grid_importing}
            />
          </div>
          <StatsPanel
            energyToday={state.energy_today_kwh}
            dischargedToday={state.discharged_today_kwh}
            totalEnergy={state.total_energy_kwh}
            onChange={(field, value) => onUpdate({ [field]: value })}
          />
          <CommandLog entries={state.command_log} />
        </div>
      </div>
    </div>
  );
}
