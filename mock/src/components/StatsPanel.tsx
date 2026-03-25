interface Props {
  energyToday: number;
  dischargedToday: number;
  totalEnergy: number;
  onChange: (field: string, value: number) => void;
}

export function StatsPanel({
  energyToday,
  dischargedToday,
  totalEnergy,
  onChange,
}: Props) {
  return (
    <div className="stats-panel">
      <h3>Cumulative Stats</h3>
      <div className="stat-row">
        <label>Generated today (kWh)</label>
        <input
          type="number"
          step={0.1}
          value={energyToday}
          onChange={(e) =>
            onChange("energy_today_kwh", parseFloat(e.target.value) || 0)
          }
        />
      </div>
      <div className="stat-row">
        <label>Discharged today (kWh)</label>
        <input
          type="number"
          step={0.1}
          value={dischargedToday}
          onChange={(e) =>
            onChange("discharged_today_kwh", parseFloat(e.target.value) || 0)
          }
        />
      </div>
      <div className="stat-row">
        <label>Total yield (kWh)</label>
        <input
          type="number"
          step={1}
          value={totalEnergy}
          onChange={(e) =>
            onChange("total_energy_kwh", parseFloat(e.target.value) || 0)
          }
        />
      </div>
    </div>
  );
}
