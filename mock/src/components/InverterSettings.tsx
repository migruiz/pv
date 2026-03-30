interface Props {
  operationMode: number;
  chargeFromAc: number;
  maxChargePower: number;
  onOperationModeChange: (v: number) => void;
  onChargeFromAcChange: (v: number) => void;
  onMaxChargePowerChange: (v: number) => void;
}

export function InverterSettings({
  operationMode,
  chargeFromAc,
  maxChargePower,
  onOperationModeChange,
  onChargeFromAcChange,
  onMaxChargePowerChange,
}: Props) {
  return (
    <div className="control-group">
      <h3>Inverter Settings</h3>

      <label>Operation Mode</label>
      <div className="direction-toggle">
        <button
          className={operationMode === 5 ? "active" : ""}
          onClick={() => onOperationModeChange(5)}
        >
          TOU
        </button>
        <button
          className={operationMode === 2 ? "active" : ""}
          onClick={() => onOperationModeChange(2)}
        >
          Self-consumption
        </button>
      </div>

      <label>Charge from AC</label>
      <div className="direction-toggle">
        <button
          className={chargeFromAc === 1 ? "active" : ""}
          onClick={() => onChargeFromAcChange(1)}
        >
          Enabled
        </button>
        <button
          className={chargeFromAc === 0 ? "active" : ""}
          onClick={() => onChargeFromAcChange(0)}
        >
          Disabled
        </button>
      </div>

      <label>
        Max Charge Power <span className="value">{maxChargePower}W</span>
      </label>
      <input
        type="range"
        min={200}
        max={2500}
        step={100}
        value={maxChargePower}
        onChange={(e) => onMaxChargePowerChange(parseInt(e.target.value))}
      />
      <div className="range-labels">
        <span>200W</span>
        <span>2500W</span>
      </div>
    </div>
  );
}
