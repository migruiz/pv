package ovh.tenjo.pv.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.WindowDetailState
import ovh.tenjo.pv.api.DischargeWindowStatus
import ovh.tenjo.pv.api.DischargeWindowUpdate
import ovh.tenjo.pv.ui.theme.BatteryGreen
import ovh.tenjo.pv.ui.theme.BatteryGreenContainer
import ovh.tenjo.pv.ui.theme.EnergyOrange
import ovh.tenjo.pv.ui.theme.OnSurfaceVariant
import ovh.tenjo.pv.ui.theme.SurfaceContainer
import java.util.Calendar

/** Today at start_time + duration = end. Button enabled if now < end. */
private fun canStartWindow(startTime: String, durationMinutes: Int): Boolean {
    val now = Calendar.getInstance()
    val startMinutes = parseTimeToMinutes(startTime)

    val endCal = (now.clone() as Calendar).apply {
        set(Calendar.HOUR_OF_DAY, startMinutes / 60)
        set(Calendar.MINUTE, startMinutes % 60)
        set(Calendar.SECOND, 0)
        set(Calendar.MILLISECOND, 0)
        add(Calendar.MINUTE, durationMinutes)
    }

    return now.before(endCal)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DischargeWindowDetailScreen(
    windowId: String,
    viewModel: SolarViewModel,
    onBack: () -> Unit,
) {
    val windowsState by viewModel.windows.collectAsState()
    val detailState by viewModel.windowDetail.collectAsState()
    val dashboardState by viewModel.dashboard.collectAsState()
    val window = windowsState.windows.find { it.id == windowId }
    val status = windowsState.statuses[windowId]

    // Auto-clear messages
    LaunchedEffect(detailState.message) {
        if (detailState.message != null) {
            kotlinx.coroutines.delay(3000)
            viewModel.clearDetailMessage()
        }
    }

    // Navigate back after delete
    LaunchedEffect(detailState.message) {
        if (detailState.message == "Deleted") {
            onBack()
        }
    }

    if (window == null) {
        Box(
            Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface),
            contentAlignment = Alignment.Center,
        ) {
            CircularProgressIndicator()
        }
        return
    }

    // Editable fields
    var name by remember(window) { mutableStateOf(window.name) }
    var startTime by remember(window) { mutableStateOf(window.startTime) }
    var durationMinutes by remember(window) { mutableIntStateOf(window.durationMinutes) }
    var endTime by remember(window) { mutableStateOf(calcEndTime(window.startTime, window.durationMinutes)) }
    var targetSoc by remember(window) { mutableFloatStateOf(window.targetSoc.toFloat()) }
    var notify by remember(window) { mutableStateOf(window.notify) }
    var enabled by remember(window) { mutableStateOf(window.enabled) }

    val hasChanges = name != window.name ||
        startTime != window.startTime ||
        durationMinutes != window.durationMinutes ||
        targetSoc != window.targetSoc.toFloat() ||
        notify != window.notify ||
        enabled != window.enabled

    // Time picker states
    var showStartPicker by remember { mutableStateOf(false) }
    var showEndPicker by remember { mutableStateOf(false) }
    var showDurationPicker by remember { mutableStateOf(false) }
    var showDeleteConfirm by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(window.name) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { showDeleteConfirm = true }) {
                        Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error)
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.surface)
                .verticalScroll(rememberScrollState())
                .padding(padding)
                .padding(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // -- Status section --
            StatusSection(status)

            // -- Configuration section --
            ConfigSection(
                name = name,
                onNameChange = { name = it },
                startTime = startTime,
                endTime = endTime,
                durationMinutes = durationMinutes,
                onStartTimeClick = { showStartPicker = true },
                onEndTimeClick = { showEndPicker = true },
                onDurationClick = { showDurationPicker = true },
                targetSoc = targetSoc,
                onTargetSocChange = { targetSoc = it },
                notify = notify,
                onNotifyChange = { notify = it },
                enabled = enabled,
                onEnabledChange = { enabled = it },
            )

            // -- Estimated energy --
            val estKwh = estimateDischargeEnergy(dashboardState.batterySoc, targetSoc.toDouble())
            Text(
                "Estimated discharge: %.2f kWh (from %.0f%% to %.0f%%)".format(
                    estKwh, dashboardState.batterySoc, targetSoc.toDouble(),
                ),
                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                color = EnergyOrange,
                modifier = Modifier.fillMaxWidth(),
            )

            // -- Save button --
            if (hasChanges) {
                Button(
                    onClick = {
                        viewModel.updateWindow(
                            windowId,
                            DischargeWindowUpdate(
                                name = name,
                                startTime = startTime,
                                durationMinutes = durationMinutes,
                                targetSoc = targetSoc.toDouble(),
                                notify = notify,
                                enabled = enabled,
                            ),
                        )
                    },
                    modifier = Modifier.fillMaxWidth().height(44.dp),
                    shape = RoundedCornerShape(50),
                    enabled = !detailState.isSaving,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.primary,
                    ),
                ) {
                    if (detailState.isSaving) {
                        CircularProgressIndicator(Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp)
                    } else {
                        Icon(Icons.Default.Save, contentDescription = null, Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("Save Changes", style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold))
                    }
                }
            }

            // -- Control section --
            ControlSection(windowId, startTime, durationMinutes, status, detailState, viewModel)

            // -- Message --
            detailState.message?.let { msg ->
                if (msg != "Deleted") {
                    Text(
                        msg,
                        style = MaterialTheme.typography.bodySmall,
                        color = if (msg.startsWith("Error")) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                    )
                }
            }
        }
    }

    // -- Time Picker Dialogs --

    if (showStartPicker) {
        TimePickerDialog(
            title = "Start Time",
            initialHour = parseTimeToMinutes(startTime) / 60,
            initialMinute = parseTimeToMinutes(startTime) % 60,
            onConfirm = { hour, minute ->
                startTime = "%02d:%02d".format(hour, minute)
                // Recalculate end time from new start + existing duration
                endTime = calcEndTime(startTime, durationMinutes)
                showStartPicker = false
            },
            onDismiss = { showStartPicker = false },
        )
    }

    if (showEndPicker) {
        TimePickerDialog(
            title = "End Time",
            initialHour = parseTimeToMinutes(endTime) / 60,
            initialMinute = parseTimeToMinutes(endTime) % 60,
            onConfirm = { hour, minute ->
                endTime = "%02d:%02d".format(hour, minute)
                // Recalculate duration from start to new end
                durationMinutes = calcDuration(startTime, endTime)
                showEndPicker = false
            },
            onDismiss = { showEndPicker = false },
        )
    }

    if (showDurationPicker) {
        DurationPickerDialog(
            initialHours = durationMinutes / 60,
            initialMinutes = durationMinutes % 60,
            onConfirm = { hours, minutes ->
                durationMinutes = hours * 60 + minutes
                // Recalculate end time from start + new duration
                endTime = calcEndTime(startTime, durationMinutes)
                showDurationPicker = false
            },
            onDismiss = { showDurationPicker = false },
        )
    }

    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            icon = {
                Icon(
                    Icons.Default.Delete,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.error,
                )
            },
            title = { Text("Delete Window?") },
            text = { Text("This will permanently delete \"${window.name}\".") },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDeleteConfirm = false
                        viewModel.deleteWindow(windowId)
                    },
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = MaterialTheme.colorScheme.error,
                    ),
                ) {
                    Text("Delete")
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) {
                    Text("Cancel")
                }
            },
        )
    }
}

// ------------------------------------------------------------------
// Status section
// ------------------------------------------------------------------

@Composable
private fun StatusSection(status: DischargeWindowStatus?) {
    val isActive = status != null && status.active

    Surface(
        shape = RoundedCornerShape(16.dp),
        color = SurfaceContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    if (isActive) Icons.Default.PlayCircle else Icons.Default.PauseCircle,
                    contentDescription = null,
                    tint = if (isActive) EnergyOrange else OnSurfaceVariant,
                    modifier = Modifier.size(20.dp),
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    if (isActive) "Currently Discharging" else "Idle",
                    style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                    color = if (isActive) EnergyOrange else OnSurfaceVariant,
                )
            }

            if (isActive) {
                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column {
                        Text("POWER", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                        Text(
                            "%.2f kW".format(status.dischargePowerKw ?: 0.0),
                            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                        )
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("SOC", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                        Text(
                            "%.1f%%".format(status.currentSoc ?: 0.0),
                            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                        )
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("REMAINING", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                        val mins = status.minutesRemaining ?: 0.0
                        val hours = (mins / 60).toInt()
                        val m = (mins % 60).toInt()
                        Text(
                            "${hours}h ${m}m",
                            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                        )
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------
// Configuration section
// ------------------------------------------------------------------

@Composable
private fun ConfigSection(
    name: String,
    onNameChange: (String) -> Unit,
    startTime: String,
    endTime: String,
    durationMinutes: Int,
    onStartTimeClick: () -> Unit,
    onEndTimeClick: () -> Unit,
    onDurationClick: () -> Unit,
    targetSoc: Float,
    onTargetSocChange: (Float) -> Unit,
    notify: Boolean,
    onNotifyChange: (Boolean) -> Unit,
    enabled: Boolean,
    onEnabledChange: (Boolean) -> Unit,
) {
    val durationHours = durationMinutes / 60
    val durationMins = durationMinutes % 60

    Surface(
        shape = RoundedCornerShape(16.dp),
        color = SurfaceContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("Configuration", style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold))

            OutlinedTextField(
                value = name,
                onValueChange = onNameChange,
                label = { Text("Name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            // Start / End / Duration — tappable fields
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ReadOnlyTimeField(
                    label = "Start",
                    value = startTime,
                    onClick = onStartTimeClick,
                    modifier = Modifier.weight(1f),
                )
                ReadOnlyTimeField(
                    label = "End",
                    value = endTime,
                    onClick = onEndTimeClick,
                    modifier = Modifier.weight(1f),
                )
                ReadOnlyTimeField(
                    label = "Duration",
                    value = "${durationHours}h ${durationMins}m",
                    onClick = onDurationClick,
                    modifier = Modifier.weight(1f),
                )
            }

            Column {
                Text(
                    "Target SOC: ${targetSoc.toInt()}%",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Slider(
                    value = targetSoc,
                    onValueChange = onTargetSocChange,
                    valueRange = 0f..100f,
                    steps = 99,
                    colors = SliderDefaults.colors(
                        thumbColor = EnergyOrange,
                        activeTrackColor = EnergyOrange,
                    ),
                )
            }

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Notifications", style = MaterialTheme.typography.bodyMedium)
                Switch(
                    checked = notify,
                    onCheckedChange = onNotifyChange,
                    colors = SwitchDefaults.colors(checkedTrackColor = EnergyOrange),
                )
            }

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Enabled", style = MaterialTheme.typography.bodyMedium)
                Switch(
                    checked = enabled,
                    onCheckedChange = onEnabledChange,
                    colors = SwitchDefaults.colors(checkedTrackColor = EnergyOrange),
                )
            }
        }
    }
}

// ------------------------------------------------------------------
// Control section
// ------------------------------------------------------------------

@Composable
private fun ControlSection(
    windowId: String,
    startTime: String,
    durationMinutes: Int,
    status: DischargeWindowStatus?,
    detailState: WindowDetailState,
    viewModel: SolarViewModel,
) {
    val isActive = status?.active == true
    val canStart = canStartWindow(startTime, durationMinutes)

    var showConfirmDialog by remember { mutableStateOf(false) }

    Button(
        onClick = { showConfirmDialog = true },
        modifier = Modifier.fillMaxWidth().height(44.dp),
        shape = RoundedCornerShape(50),
        enabled = (isActive || canStart) && !detailState.isStarting && !detailState.isStopping,
        colors = ButtonDefaults.buttonColors(
            containerColor = if (isActive) MaterialTheme.colorScheme.error else BatteryGreenContainer,
            contentColor = Color.White,
        ),
    ) {
        if (detailState.isStarting || detailState.isStopping) {
            CircularProgressIndicator(Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp)
        } else {
            Icon(
                if (isActive) Icons.Default.StopCircle else Icons.Default.PlayArrow,
                contentDescription = null,
                Modifier.size(18.dp),
            )
            Spacer(Modifier.width(8.dp))
            Text(
                when {
                    isActive -> "Stop Discharge"
                    canStart -> "Start Discharge"
                    else -> "Window Expired"
                },
                style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold),
            )
        }
    }

    if (showConfirmDialog) {
        AlertDialog(
            onDismissRequest = { showConfirmDialog = false },
            icon = {
                Icon(
                    if (isActive) Icons.Default.StopCircle else Icons.Default.PlayArrow,
                    contentDescription = null,
                    tint = if (isActive) MaterialTheme.colorScheme.error else BatteryGreen,
                )
            },
            title = {
                Text(if (isActive) "Stop Discharge?" else "Start Discharge?")
            },
            text = {
                Text(
                    if (isActive) "This will stop the current discharge session."
                    else "This will start discharging the battery now.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showConfirmDialog = false
                        if (isActive) viewModel.stopWindow(windowId)
                        else viewModel.startWindow(windowId)
                    },
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = if (isActive) MaterialTheme.colorScheme.error else BatteryGreen,
                    ),
                ) {
                    Text(if (isActive) "Stop" else "Start")
                }
            },
            dismissButton = {
                TextButton(onClick = { showConfirmDialog = false }) {
                    Text("Cancel")
                }
            },
        )
    }
}
