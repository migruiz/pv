interface Props {
  value: number;
  onChange: (v: number) => void;
}

export function HomeConsumption({ value, onChange }: Props) {
  return (
    <div className="control-group">
      <label>
        Home Load <span className="value">{value.toFixed(2)} kW</span>
      </label>
      <input
        type="range"
        min={0}
        max={10}
        step={0.01}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
      <div className="range-labels">
        <span>0</span>
        <span>10 kW</span>
      </div>
    </div>
  );
}
