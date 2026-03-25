interface CommandEntry {
  timestamp: string;
  signals: Record<string, string>;
}

interface Props {
  entries: CommandEntry[];
}

const MODE_LABELS: Record<string, string> = {
  "0": "Stop",
  "1": "Charge",
  "2": "Discharge",
};

export function CommandLog({ entries }: Props) {
  return (
    <div className="command-log">
      <h3>Command Log</h3>
      <div className="log-entries">
        {entries.length === 0 && (
          <div className="log-empty">No commands received yet</div>
        )}
        {[...entries].reverse().map((entry, i) => {
          const time = new Date(entry.timestamp).toLocaleTimeString();
          const mode = entry.signals.charge_discharge_mode;
          const power = entry.signals.forced_power_kw;
          const summary = mode
            ? `${MODE_LABELS[mode] || mode}${power ? ` @ ${power} kW` : ""}`
            : JSON.stringify(entry.signals);

          return (
            <div key={i} className="log-entry">
              <span className="log-time">{time}</span>
              <span className="log-summary">{summary}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
