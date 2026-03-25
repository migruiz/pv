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
    val batteryCharging: Boolean = false,
    val batteryStatus: String = "—",
    val batteryCapacity: Double = 0.0,
    val chargedTodayKwh: Double = 0.0,
    val dischargedTodayKwh: Double = 0.0,
    val gridPowerKw: Double = 0.0,
    val gridImporting: Boolean = false,
    val homePowerKw: Double = 0.0,
    val energyTodayKwh: Double = 0.0,
    val consumedTodayKwh: Double = 0.0,
    val totalEnergyKwh: Double = 0.0,
    val isLoading: Boolean = true,
    val isRefreshing: Boolean = false,
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
        loadDashboard(showLoading = true)
    }

    fun pullToRefresh() {
        loadDashboard(showLoading = false)
    }

    private fun loadDashboard(showLoading: Boolean) {
        viewModelScope.launch {
            _dashboard.value = _dashboard.value.copy(
                isLoading = showLoading,
                isRefreshing = !showLoading,
                error = null,
            )
            try {
                val d = api.getDashboard()

                _dashboard.value = DashboardState(
                    pvPowerKw = d.pvKw,
                    batterySoc = d.batterySoc,
                    batteryPowerKw = d.batteryChargeDischargeKw,
                    batteryCharging = d.batteryCharging,
                    batteryStatus = d.batteryStatus,
                    batteryCapacity = d.batteryCapacity,
                    chargedTodayKwh = d.chargedTodayKwh,
                    dischargedTodayKwh = d.dischargedTodayKwh,
                    gridPowerKw = d.gridKw,
                    gridImporting = d.gridImporting,
                    homePowerKw = d.homeKw,
                    energyTodayKwh = d.energyTodayKwh,
                    consumedTodayKwh = d.dischargedTodayKwh + d.energyTodayKwh,
                    totalEnergyKwh = d.totalEnergyKwh,
                    isLoading = false,
                )

                // Sync battery control state
                _batteryControl.value = _batteryControl.value.copy(
                    soc = d.batterySoc,
                    status = d.batteryStatus,
                    currentPowerKw = d.batteryChargeDischargeKw,
                )
            } catch (e: Exception) {
                _dashboard.value = _dashboard.value.copy(
                    isLoading = false,
                    isRefreshing = false,
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
