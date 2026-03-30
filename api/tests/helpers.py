"""Shared test helpers (importable by test modules)."""


class AttrDict(dict):
    """Dict subclass that allows attribute access."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)


class FakeSession:
    """Lightweight session mock that returns configurable SOC and records signals."""

    def __init__(self, soc_sequence: list[float] | None = None):
        self.soc_values = soc_sequence or [80.0]
        self.soc_index = 0
        self.signals_sent: list[dict] = []

    async def call(self, method: str, *args, **kwargs):
        if method == "get_battery_basic_stats":
            soc = self.soc_values[min(self.soc_index, len(self.soc_values) - 1)]
            self.soc_index += 1
            return AttrDict({"state_of_charge": soc})
        raise ValueError(f"FakeSession: unknown method '{method}'")

    async def post_config_signals(self, dn: str, signals: list[dict]):
        self.signals_sent.append({"dn": dn, "signals": signals})
        return {"success": True, "failCode": 0}

    async def keep_alive(self):
        pass

    async def shutdown(self):
        pass


class FakeAppState:
    """Mimics the FastAPI app.state namespace used by scheduler and correction loop."""

    def __init__(self):
        import asyncio
        self.discharge_tasks: dict = {}
        self.discharge_statuses: dict = {}
        self.windows_changed = asyncio.Event()
        # Charge ramp fields
        self.charge_ramp_task = None
        self.charge_ramp_status = None
        self.charge_ramp_manager = None
