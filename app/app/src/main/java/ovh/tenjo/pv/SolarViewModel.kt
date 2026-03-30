package ovh.tenjo.pv

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import ovh.tenjo.pv.api.DischargeWindowCreate
import ovh.tenjo.pv.api.DischargeWindowStatus
import ovh.tenjo.pv.api.DischargeWindowUpdate
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

data class DischargeWindowsState(
    val windows: List<ovh.tenjo.pv.api.DischargeWindow> = emptyList(),
    val statuses: Map<String, DischargeWindowStatus> = emptyMap(),
    val isLoading: Boolean = false,
    val error: String? = null,
)

data class WindowDetailState(
    val isStarting: Boolean = false,
    val isStopping: Boolean = false,
    val isSaving: Boolean = false,
    val isDeleting: Boolean = false,
    val message: String? = null,
)

class SolarViewModel : ViewModel() {

    private val api = SolarApiClient.service

    private val _dashboard = MutableStateFlow(DashboardState())
    val dashboard: StateFlow<DashboardState> = _dashboard.asStateFlow()

    private val _windows = MutableStateFlow(DischargeWindowsState())
    val windows: StateFlow<DischargeWindowsState> = _windows.asStateFlow()

    private val _windowDetail = MutableStateFlow(WindowDetailState())
    val windowDetail: StateFlow<WindowDetailState> = _windowDetail.asStateFlow()


    init {
        refreshDashboard()
        loadWindows()
        startAutoRefresh()
    }

    // -- Dashboard --

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

    // -- Discharge Windows --

    fun loadWindows() {
        viewModelScope.launch {
            _windows.value = _windows.value.copy(isLoading = true, error = null)
            try {
                val windowList = api.getDischargeWindows()
                val statuses = api.getWindowStatuses()
                val statusMap = statuses.associateBy { it.windowId }
                _windows.value = DischargeWindowsState(
                    windows = windowList,
                    statuses = statusMap,
                )
            } catch (e: Exception) {
                _windows.value = _windows.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load windows",
                )
            }
        }
    }

    fun loadStatuses() {
        viewModelScope.launch {
            try {
                val statuses = api.getWindowStatuses()
                val statusMap = statuses.associateBy { it.windowId }
                _windows.value = _windows.value.copy(statuses = statusMap)
            } catch (_: Exception) { }
        }
    }

    fun createWindow(create: DischargeWindowCreate) {
        viewModelScope.launch {
            _windowDetail.value = _windowDetail.value.copy(isSaving = true, message = null)
            try {
                api.createDischargeWindow(create)
                _windowDetail.value = WindowDetailState(message = "Window created")
                loadWindows()
            } catch (e: Exception) {
                _windowDetail.value = _windowDetail.value.copy(
                    isSaving = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun updateWindow(windowId: String, update: DischargeWindowUpdate) {
        viewModelScope.launch {
            _windowDetail.value = _windowDetail.value.copy(isSaving = true, message = null)
            try {
                api.updateDischargeWindow(windowId, update)
                _windowDetail.value = WindowDetailState(message = "Saved")
                loadWindows()
            } catch (e: Exception) {
                _windowDetail.value = _windowDetail.value.copy(
                    isSaving = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun deleteWindow(windowId: String) {
        viewModelScope.launch {
            _windowDetail.value = _windowDetail.value.copy(isDeleting = true, message = null)
            try {
                api.deleteDischargeWindow(windowId)
                _windowDetail.value = WindowDetailState(message = "Deleted")
                loadWindows()
            } catch (e: Exception) {
                _windowDetail.value = _windowDetail.value.copy(
                    isDeleting = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun startWindow(windowId: String) {
        viewModelScope.launch {
            _windowDetail.value = _windowDetail.value.copy(isStarting = true, message = null)
            try {
                api.startWindow(windowId)
                _windowDetail.value = _windowDetail.value.copy(isStarting = false, message = "Started")
                loadWindows()
            } catch (e: Exception) {
                _windowDetail.value = _windowDetail.value.copy(
                    isStarting = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun stopWindow(windowId: String) {
        viewModelScope.launch {
            _windowDetail.value = _windowDetail.value.copy(isStopping = true, message = null)
            try {
                api.stopWindow(windowId)
                _windowDetail.value = _windowDetail.value.copy(isStopping = false, message = "Stopped")
                loadWindows()
            } catch (e: Exception) {
                _windowDetail.value = _windowDetail.value.copy(
                    isStopping = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun toggleWindowEnabled(windowId: String, enabled: Boolean) {
        updateWindow(windowId, DischargeWindowUpdate(enabled = enabled))
    }

    fun clearDetailMessage() {
        _windowDetail.value = _windowDetail.value.copy(message = null)
    }

    // -- Auto-refresh --

    private fun startAutoRefresh() {
        viewModelScope.launch {
            while (isActive) {
                delay(20_000)
                loadDashboard(showLoading = false)
                loadStatuses()
            }
        }
    }
}
