package ovh.tenjo.pv

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
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

class SolarViewModel : ViewModel() {

    private val api = SolarApiClient.service

    private val _dashboard = MutableStateFlow(DashboardState())
    val dashboard: StateFlow<DashboardState> = _dashboard.asStateFlow()

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
}
