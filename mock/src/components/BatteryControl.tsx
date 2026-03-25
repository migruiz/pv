interface Props {
  soc: number;
  power: number;
  charging: boolean;
  forcedMode: number;
  onSocChange: (v: number) => void;
  onPowerChange: (v: number) => void;
  onDirectionChange: (charging: boolean) => void;
}

export function BatteryControl({
  soc,
  power,
  charging,
  forcedMode,
  onSocChange,
  onPowerChange,
  onDirectionChange,
}: Props) {
  const modeLabel =
    forcedMode === 1
      ? "FORCED CHARGE"
      : forcedMode === 2
        ? "FORCED DISCHARGE"
        : null;

  return (
    <div className="control-group">
      <label>
        Battery SOC <span className="value">{soc.toFixed(1)}%</span>
      </label>
      <input
        type="range"
        min={0}
        max={100}
        step={0.1}
        value={soc}
        onChange={(e) => onSocChange(parseFloat(e.target.value))}
      />
      <div className="range-labels">
        <span>0%</span>
        <span>100%</span>
      </div>

      <label>
        Battery Power <span className="value">{power.toFixed(2)} kW</span>
      </label>
      <input
        type="range"
        min={0}
        max={2.5}
        step={0.01}
        value={power}
        onChange={(e) => onPowerChange(parseFloat(e.target.value))}
      />
      <div className="range-labels">
        <span>0</span>
        <span>2.5 kW</span>
      </div>

      <div className="direction-toggle">
        <button
          className={charging ? "active" : ""}
          onClick={() => onDirectionChange(true)}
        >
          Charging
        </button>
        <button
          className={!charging ? "active" : ""}
          onClick={() => onDirectionChange(false)}
        >
          Discharging
        </button>
      </div>

      {modeLabel && <div className="forced-badge">{modeLabel}</div>}
    </div>
  );
}
