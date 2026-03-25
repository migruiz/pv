package ovh.tenjo.pv

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import ovh.tenjo.pv.api.SolarApiClient

data class DashboardState(
    val pvPowerKw: Double = 0.0,
    val batterySoc: Double = 0.0,
    val batteryPowerKw: Double = 0.0,
    val batteryCharging: Boolean = false,
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

data class AutoDischargeState(
    val active: Boolean = false,
    val currentSoc: Double? = null,
    val dischargePowerKw: Double? = null,
    val minutesRemaining: Double? = null,
    val targetTime: String? = null,
    val isStarting: Boolean = false,
    val isStopping: Boolean = false,
    val message: String? = null,
)

class SolarViewModel : ViewModel() {

    private val api = SolarApiClient.service

    private val _dashboard = MutableStateFlow(DashboardState())
    val dashboard: StateFlow<DashboardState> = _dashboard.asStateFlow()

    private val _autoDischarge = MutableStateFlow(AutoDischargeState())
    val autoDischarge: StateFlow<AutoDischargeState> = _autoDischarge.asStateFlow()

    private var statusPollingJob: Job? = null

    init {
        refreshDashboard()
        refreshAutoDischargeStatus()
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
                    gridPowerKw = d.gridKw,
                    gridImporting = d.gridImporting,
                    homePowerKw = d.homeKw,
                    energyTodayKwh = d.energyTodayKwh,
                    consumedTodayKwh = d.dischargedTodayKwh + d.energyTodayKwh,
                    totalEnergyKwh = d.totalEnergyKwh,
                    isLoading = false,
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

    // -- Auto-discharge --

    fun refreshAutoDischargeStatus() {
        viewModelScope.launch {
            try {
                val s = api.getAutoDischargeStatus(SolarApiClient.BATTERY_ID)
                _autoDischarge.value = _autoDischarge.value.copy(
                    active = s.active,
                    currentSoc = s.currentSoc,
                    dischargePowerKw = s.dischargePowerKw,
                    minutesRemaining = s.minutesRemaining,
                    targetTime = s.targetTime,
                    message = null,
                )
                if (s.active) startStatusPolling() else stopStatusPolling()
            } catch (_: Exception) {
                // Silently ignore — status will refresh on next poll or action
            }
        }
    }

    fun startAutoDischarge() {
        viewModelScope.launch {
            _autoDischarge.value = _autoDischarge.value.copy(isStarting = true, message = null)
            try {
                val r = api.startAutoDischarge(SolarApiClient.BATTERY_ID)
                _autoDischarge.value = _autoDischarge.value.copy(
                    isStarting = false,
                    active = true,
                    currentSoc = r.initialSoc,
                    dischargePowerKw = r.dischargePowerKw,
                    targetTime = r.targetTime,
                    message = "Started",
                )
                startStatusPolling()
                refreshDashboard()
            } catch (e: Exception) {
                _autoDischarge.value = _autoDischarge.value.copy(
                    isStarting = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun stopAutoDischarge() {
        viewModelScope.launch {
            _autoDischarge.value = _autoDischarge.value.copy(isStopping = true, message = null)
            try {
                api.stopAutoDischarge(SolarApiClient.BATTERY_ID)
                _autoDischarge.value = AutoDischargeState(message = "Stopped")
                stopStatusPolling()
                refreshDashboard()
            } catch (e: Exception) {
                _autoDischarge.value = _autoDischarge.value.copy(
                    isStopping = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun clearAutoDischargeMessage() {
        _autoDischarge.value = _autoDischarge.value.copy(message = null)
    }

    private fun startStatusPolling() {
        if (statusPollingJob?.isActive == true) return
        statusPollingJob = viewModelScope.launch {
            while (isActive) {
                delay(10_000) // Poll every 10 seconds
                refreshAutoDischargeStatus()
                loadDashboard(showLoading = false)
            }
        }
    }

    private fun stopStatusPolling() {
        statusPollingJob?.cancel()
        statusPollingJob = null
    }
}
