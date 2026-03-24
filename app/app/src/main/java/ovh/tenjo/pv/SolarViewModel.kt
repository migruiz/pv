package ovh.tenjo.pv

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ovh.tenjo.pv.api.ForcedChargeRequest
import ovh.tenjo.pv.api.SolarApiClient

// ------------------------------------------------------------------
// Dashboard state
// ------------------------------------------------------------------

data class DashboardState(
    val pvPowerKw: Double = 0.0,
    val batterySoc: Double = 0.0,
    val batteryPowerKw: Double = 0.0,
    val batteryStatus: String = "—",
    val batteryCapacity: Double = 0.0,
    val chargedTodayKwh: Double = 0.0,
    val dischargedTodayKwh: Double = 0.0,
    val gridPowerKw: Double = 0.0,
    val homePowerKw: Double = 0.0,
    val energyTodayKwh: Double = 0.0,
    val consumedTodayKwh: Double = 0.0,
    val totalEnergyKwh: Double = 0.0,
    val isLoading: Boolean = true,
    val error: String? = null,
)

// ------------------------------------------------------------------
// Battery control state
// ------------------------------------------------------------------

data class BatteryControlState(
    val soc: Double = 0.0,
    val status: String = "—",
    val currentPowerKw: Double = 0.0,
    val mode: String = "stop",          // stop, charge, discharge
    val powerKw: Float = 0.7f,
    val settingMode: String = "duration",
    val durationMin: Int = 60,
    val isApplying: Boolean = false,
    val applyResult: String? = null,
)

// ------------------------------------------------------------------
// ViewModel
// ------------------------------------------------------------------

class SolarViewModel : ViewModel() {

    private val api = SolarApiClient.service

    private val _dashboard = MutableStateFlow(DashboardState())
    val dashboard: StateFlow<DashboardState> = _dashboard.asStateFlow()

    private val _batteryControl = MutableStateFlow(BatteryControlState())
    val batteryControl: StateFlow<BatteryControlState> = _batteryControl.asStateFlow()

    init {
        refreshDashboard()
    }

    fun refreshDashboard() {
        viewModelScope.launch {
            _dashboard.value = _dashboard.value.copy(isLoading = true, error = null)
            try {
                val status = api.getStatus()
                val battery = api.getBatteryStatus(SolarApiClient.BATTERY_ID)

                // Approximate home load and grid from available data
                val homePower = status.currentPowerKw + battery.currentChargeDischargeKw
                val gridPower = homePower - status.currentPowerKw + battery.currentChargeDischargeKw

                _dashboard.value = DashboardState(
                    pvPowerKw = status.currentPowerKw,
                    batterySoc = battery.stateOfCharge,
                    batteryPowerKw = battery.currentChargeDischargeKw,
                    batteryStatus = battery.operatingStatus,
                    batteryCapacity = battery.ratedCapacity,
                    chargedTodayKwh = battery.totalChargedTodayKwh,
                    dischargedTodayKwh = battery.totalDischargedTodayKwh,
                    gridPowerKw = gridPower.coerceAtLeast(0.0),
                    homePowerKw = homePower.coerceAtLeast(0.0),
                    energyTodayKwh = status.energyTodayKwh,
                    consumedTodayKwh = battery.totalDischargedTodayKwh + status.energyTodayKwh,
                    totalEnergyKwh = status.totalEnergyKwh,
                    isLoading = false,
                )

                // Sync battery control state
                _batteryControl.value = _batteryControl.value.copy(
                    soc = battery.stateOfCharge,
                    status = battery.operatingStatus,
                    currentPowerKw = battery.currentChargeDischargeKw,
                )
            } catch (e: Exception) {
                _dashboard.value = _dashboard.value.copy(
                    isLoading = false,
                    error = e.message ?: "Connection failed",
                )
            }
        }
    }

    // -- Battery control mutations --

    fun setMode(mode: String) {
        _batteryControl.value = _batteryControl.value.copy(mode = mode)
    }

    fun setPowerKw(power: Float) {
        _batteryControl.value = _batteryControl.value.copy(powerKw = power)
    }

    fun setSettingMode(mode: String) {
        _batteryControl.value = _batteryControl.value.copy(settingMode = mode)
    }

    fun setDurationMin(min: Int) {
        _batteryControl.value = _batteryControl.value.copy(durationMin = min)
    }

    fun applyForcedCharge() {
        val state = _batteryControl.value
        viewModelScope.launch {
            _batteryControl.value = state.copy(isApplying = true, applyResult = null)
            try {
                val response = api.setForcedCharge(
                    SolarApiClient.BATTERY_ID,
                    ForcedChargeRequest(
                        mode = state.mode,
                        powerKw = state.powerKw.toDouble(),
                        settingMode = state.settingMode,
                        durationMin = state.durationMin,
                    ),
                )
                _batteryControl.value = _batteryControl.value.copy(
                    isApplying = false,
                    applyResult = if (response.success) "Applied: ${state.mode}" else "Failed",
                )
                refreshDashboard()
            } catch (e: Exception) {
                _batteryControl.value = _batteryControl.value.copy(
                    isApplying = false,
                    applyResult = "Error: ${e.message}",
                )
            }
        }
    }

    fun quickAction(mode: String, durationMin: Int) {
        _batteryControl.value = _batteryControl.value.copy(
            mode = mode,
            powerKw = if (mode == "stop") 0f else 0.7f,
            durationMin = durationMin,
            settingMode = "duration",
        )
        applyForcedCharge()
    }

    fun clearResult() {
        _batteryControl.value = _batteryControl.value.copy(applyResult = null)
    }
}
