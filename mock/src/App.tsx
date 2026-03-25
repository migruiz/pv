import { useSimState } from "./hooks/useSimState";
import { ControlPanel } from "./components/ControlPanel";

export default function App() {
  const { state, update, reset } = useSimState();

  if (!state) return <div className="loading">Connecting to mock server...</div>;

  return <ControlPanel state={state} onUpdate={update} onReset={reset} />;
}
