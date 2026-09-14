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
import ovh.tenjo.pv.api.ChargeWindowCreate
import ovh.tenjo.pv.api.ChargeWindowStatus
import ovh.tenjo.pv.api.ChargeWindowUpdate
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
    val operationMode: Int = 5,
    val chargeFromAc: Int = 1,
    val maxChargePower: Int = 2500,
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

data class ChargeWindowsState(
    val windows: List<ovh.tenjo.pv.api.ChargeWindow> = emptyList(),
    val statuses: Map<String, ChargeWindowStatus> = emptyMap(),
    val isLoading: Boolean = false,
    val error: String? = null,
)

data class ChargeWindowDetailState(
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

    private val _chargeWindows = MutableStateFlow(ChargeWindowsState())
    val chargeWindows: StateFlow<ChargeWindowsState> = _chargeWindows.asStateFlow()

    private val _chargeWindowDetail = MutableStateFlow(ChargeWindowDetailState())
    val chargeWindowDetail: StateFlow<ChargeWindowDetailState> = _chargeWindowDetail.asStateFlow()


    private var autoRefreshJob: Job? = null

    init {
        refreshDashboard()
        loadWindows()
        loadChargeWindows()
    }

    // -- Dashboard --

    fun refreshDashboard() {
        loadDashboard(showLoading = true)
    }

    fun pullToRefresh() {
        loadDashboard(showLoading = false)
    }

    private fun loadDashboard(showLoading: Boolean, showError: Boolean = true): Job =
        viewModelScope.launch {
            if (showLoading || showError) {
                _dashboard.value = _dashboard.value.copy(
                    isLoading = showLoading,
                    isRefreshing = !showLoading,
                    error = null,
                )
            }
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
                    operationMode = d.operationMode,
                    chargeFromAc = d.chargeFromAc,
                    maxChargePower = d.maxChargePower,
                    isLoading = false,
                )
            } catch (e: Exception) {
                if (showError) {
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

    // -- Charge Windows --

    fun loadChargeWindows() {
        viewModelScope.launch {
            _chargeWindows.value = _chargeWindows.value.copy(isLoading = true, error = null)
            try {
                val windowList = api.getChargeWindows()
                val statuses = api.getChargeWindowStatuses()
                val statusMap = statuses.associateBy { it.windowId }
                _chargeWindows.value = ChargeWindowsState(
                    windows = windowList,
                    statuses = statusMap,
                )
            } catch (e: Exception) {
                _chargeWindows.value = _chargeWindows.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load charge windows",
                )
            }
        }
    }

    fun loadChargeWindowStatuses() {
        viewModelScope.launch {
            try {
                val statuses = api.getChargeWindowStatuses()
                val statusMap = statuses.associateBy { it.windowId }
                _chargeWindows.value = _chargeWindows.value.copy(statuses = statusMap)
            } catch (_: Exception) { }
        }
    }

    fun createChargeWindow(create: ChargeWindowCreate) {
        viewModelScope.launch {
            _chargeWindowDetail.value = _chargeWindowDetail.value.copy(isSaving = true, message = null)
            try {
                api.createChargeWindow(create)
                _chargeWindowDetail.value = ChargeWindowDetailState(message = "Window created")
                loadChargeWindows()
            } catch (e: Exception) {
                _chargeWindowDetail.value = _chargeWindowDetail.value.copy(
                    isSaving = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun updateChargeWindow(windowId: String, update: ChargeWindowUpdate) {
        viewModelScope.launch {
            _chargeWindowDetail.value = _chargeWindowDetail.value.copy(isSaving = true, message = null)
            try {
                api.updateChargeWindow(windowId, update)
                _chargeWindowDetail.value = ChargeWindowDetailState(message = "Saved")
                loadChargeWindows()
            } catch (e: Exception) {
                _chargeWindowDetail.value = _chargeWindowDetail.value.copy(
                    isSaving = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun deleteChargeWindow(windowId: String) {
        viewModelScope.launch {
            _chargeWindowDetail.value = _chargeWindowDetail.value.copy(isDeleting = true, message = null)
            try {
                api.deleteChargeWindow(windowId)
                _chargeWindowDetail.value = ChargeWindowDetailState(message = "Deleted")
                loadChargeWindows()
            } catch (e: Exception) {
                _chargeWindowDetail.value = _chargeWindowDetail.value.copy(
                    isDeleting = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun startChargeWindow(windowId: String) {
        viewModelScope.launch {
            _chargeWindowDetail.value = _chargeWindowDetail.value.copy(isStarting = true, message = null)
            try {
                api.startChargeWindow(windowId)
                _chargeWindowDetail.value = _chargeWindowDetail.value.copy(isStarting = false, message = "Started")
                loadChargeWindows()
            } catch (e: Exception) {
                _chargeWindowDetail.value = _chargeWindowDetail.value.copy(
                    isStarting = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun stopChargeWindow(windowId: String) {
        viewModelScope.launch {
            _chargeWindowDetail.value = _chargeWindowDetail.value.copy(isStopping = true, message = null)
            try {
                api.stopChargeWindow(windowId)
                _chargeWindowDetail.value = _chargeWindowDetail.value.copy(isStopping = false, message = "Stopped")
                loadChargeWindows()
            } catch (e: Exception) {
                _chargeWindowDetail.value = _chargeWindowDetail.value.copy(
                    isStopping = false,
                    message = "Error: ${e.message}",
                )
            }
        }
    }

    fun clearChargeWindowDetailMessage() {
        _chargeWindowDetail.value = _chargeWindowDetail.value.copy(message = null)
    }

    // -- Auto-refresh (lifecycle-aware) --

    fun startAutoRefresh() {
        if (autoRefreshJob?.isActive == true) return
        autoRefreshJob = viewModelScope.launch {
            var tick = 0
            while (isActive) {
                // Readings come straight from the inverter, refreshed on the Pi every 3 s
                delay(3_000)
                // Wait for the request so a slow network never stacks up overlapping calls
                loadDashboard(showLoading = false, showError = false).join()
                // Window statuses change slowly: keep roughly their old cadence
                if (tick++ % 5 == 0) {
                    loadStatuses()
                    loadChargeWindowStatuses()
                }
            }
        }
    }

    fun stopAutoRefresh() {
        autoRefreshJob?.cancel()
        autoRefreshJob = null
    }
}
