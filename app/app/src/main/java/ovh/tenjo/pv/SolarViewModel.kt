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
import ovh.tenjo.pv.api.DaytimeTarget
import ovh.tenjo.pv.api.DaytimeTargetSettings
import ovh.tenjo.pv.api.DischargeWindow
import ovh.tenjo.pv.api.SolarApiClient
import ovh.tenjo.pv.api.WindowSettings
import ovh.tenjo.pv.api.apiErrorMessage

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
    val spareSolarToBattery: Boolean? = null,
    val isLoading: Boolean = true,
    val isRefreshing: Boolean = false,
    val error: String? = null,
)

data class WindowsState(
    val windows: List<DischargeWindow> = emptyList(),
    val loaded: Boolean = false,
    val error: String? = null,
    /** When the list last loaded successfully (ms); a failed refresh keeps the old value. */
    val fetchedAt: Long = 0L,
)

/** The daytime battery target, and a change being saved. */
data class TargetState(
    val target: DaytimeTarget? = null,
    val isSaving: Boolean = false,
    val error: String? = null,
)

/** The window screen's save or delete in progress, its refusal, and whether it finished. */
data class EditorState(
    val isSaving: Boolean = false,
    val isDeleting: Boolean = false,
    val error: String? = null,
    val done: Boolean = false,
)

class SolarViewModel : ViewModel() {

    private val api = SolarApiClient.service

    private val _dashboard = MutableStateFlow(DashboardState())
    val dashboard: StateFlow<DashboardState> = _dashboard.asStateFlow()

    private val _windows = MutableStateFlow(WindowsState())
    val windows: StateFlow<WindowsState> = _windows.asStateFlow()

    private val _target = MutableStateFlow(TargetState())
    val target: StateFlow<TargetState> = _target.asStateFlow()

    private val _editor = MutableStateFlow(EditorState())
    val editor: StateFlow<EditorState> = _editor.asStateFlow()

    /** A saved window the inverter has not caught up with yet, shown above the list until dismissed. */
    private val _notice = MutableStateFlow<String?>(null)
    val notice: StateFlow<String?> = _notice.asStateFlow()

    private var autoRefreshJob: Job? = null

    init {
        refreshDashboard()
        loadWindows()
        loadTarget()
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
                    spareSolarToBattery = d.spareSolarToBattery,
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

    // -- Daytime battery target --

    fun loadTarget(): Job = viewModelScope.launch {
        try {
            val target = api.getDaytimeTarget()
            // A save in progress has the newer value
            if (!_target.value.isSaving) _target.value = TargetState(target = target)
        } catch (e: Exception) {
            if (!_target.value.isSaving) _target.value = _target.value.copy(error = apiErrorMessage(e))
        }
    }

    /** Save a new target. The API sets the inverter before replying. */
    fun saveTarget(targetSoc: Int) {
        val previous = _target.value.target
        if (targetSoc == previous?.targetSoc) return
        viewModelScope.launch {
            // Shown straight away, so the slider does not jump back while saving
            _target.value = TargetState(target = previous?.copy(targetSoc = targetSoc), isSaving = true)
            try {
                val saved = api.setDaytimeTarget(DaytimeTargetSettings(targetSoc))
                _target.value = TargetState(target = saved)
                _notice.value = saved.warning?.let { "Daytime target: $it" }
            } catch (e: Exception) {
                _target.value = TargetState(target = previous, error = apiErrorMessage(e))
            }
        }
    }

    // -- Discharge Windows --

    fun loadWindows(): Job = viewModelScope.launch {
        try {
            val windows = api.getDischargeWindows()
            _windows.value = WindowsState(windows = windows, loaded = true, fetchedAt = System.currentTimeMillis())
        } catch (e: Exception) {
            _windows.value = _windows.value.copy(error = apiErrorMessage(e))
        }
    }

    /** Create (windowId null) or replace a window. The API applies it before replying. */
    fun saveWindow(windowId: String?, settings: WindowSettings) {
        viewModelScope.launch {
            _editor.value = EditorState(isSaving = true)
            try {
                val saved = if (windowId == null) api.createDischargeWindow(settings)
                else api.updateDischargeWindow(windowId, settings)
                loadWindows().join()
                _notice.value = saved.warning?.let { "${saved.name}: $it" }
                _editor.value = EditorState(done = true)
            } catch (e: Exception) {
                _editor.value = EditorState(error = apiErrorMessage(e))
            }
        }
    }

    fun deleteWindow(windowId: String) {
        viewModelScope.launch {
            _editor.value = EditorState(isDeleting = true)
            try {
                api.deleteDischargeWindow(windowId)
                loadWindows().join()
                _editor.value = EditorState(done = true)
            } catch (e: Exception) {
                _editor.value = EditorState(error = apiErrorMessage(e))
            }
        }
    }

    /** Called when the window screen opens, so a previous save's result never carries over. */
    fun resetEditor() {
        _editor.value = EditorState()
    }

    fun dismissNotice() {
        _notice.value = null
    }

    // -- Auto-refresh (lifecycle-aware) --

    /** Called each time the app comes to the foreground. */
    fun startAutoRefresh() {
        if (autoRefreshJob?.isActive == true) return
        autoRefreshJob = viewModelScope.launch {
            // Dashboard: straight away, so the app never shows readings from when it was last open,
            // then every 2 s. Waiting for each request means a slow network never stacks up calls.
            launch {
                while (isActive) {
                    loadDashboard(showLoading = false, showError = false).join()
                    delay(2_000)
                }
            }
            // Window states and the daytime target change slowly: every 15 s
            launch {
                while (isActive) {
                    loadWindows().join()
                    loadTarget().join()
                    delay(15_000)
                }
            }
        }
    }

    fun stopAutoRefresh() {
        autoRefreshJob?.cancel()
        autoRefreshJob = null
    }
}
