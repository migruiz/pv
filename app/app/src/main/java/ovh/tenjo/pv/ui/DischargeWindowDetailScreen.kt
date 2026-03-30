package ovh.tenjo.pv.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import ovh.tenjo.pv.ui.theme.EnergyOrange
import ovh.tenjo.pv.ui.theme.OnSurfaceVariant
import ovh.tenjo.pv.ui.theme.SurfaceContainer
import java.util.Calendar

// -- Time helpers --

private fun parseTimeToMinutes(time: String): Int {
    val parts = time.split(":")
    if (parts.size != 2) return 0
    return (parts[0].toIntOrNull() ?: 0) * 60 + (parts[1].toIntOrNull() ?: 0)
}

private fun minutesToTimeString(totalMinutes: Int): String {
    val m = ((totalMinutes % 1440) + 1440) % 1440
    return "%02d:%02d".format(m / 60, m % 60)
}

private fun calcDuration(startTime: String, endTime: String): Int {
    val start = parseTimeToMinutes(startTime)
    val end = parseTimeToMinutes(endTime)
    return ((end - start) + 1440) % 1440
}

private fun calcEndTime(startTime: String, durationMinutes: Int): String {
    val start = parseTimeToMinutes(startTime)
    return minutesToTimeString(start + durationMinutes)
}


/**
 * Take today's date at start_time, add duration → that's the end datetime.
 * Button enabled if now < end datetime.
 */
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
                    IconButton(onClick = { viewModel.deleteWindow(windowId) }) {
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
}

// ------------------------------------------------------------------
// Time Picker Dialog (Material3 TimePicker in a dialog)
// ------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TimePickerDialog(
    title: String,
    initialHour: Int,
    initialMinute: Int,
    onConfirm: (hour: Int, minute: Int) -> Unit,
    onDismiss: () -> Unit,
) {
    val state = rememberTimePickerState(
        initialHour = initialHour,
        initialMinute = initialMinute,
        is24Hour = true,
    )

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                TimePicker(state = state)
            }
        },
        confirmButton = {
            Button(
                onClick = { onConfirm(state.hour, state.minute) },
                colors = ButtonDefaults.buttonColors(containerColor = EnergyOrange),
            ) {
                Text("OK", fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}

// ------------------------------------------------------------------
// Duration Picker Dialog (hours + minutes sliders)
// ------------------------------------------------------------------

@Composable
private fun DurationPickerDialog(
    initialHours: Int,
    initialMinutes: Int,
    onConfirm: (hours: Int, minutes: Int) -> Unit,
    onDismiss: () -> Unit,
) {
    var hours by remember { mutableIntStateOf(initialHours) }
    var minutes by remember { mutableIntStateOf(initialMinutes) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Duration") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                // Hours
                Column {
                    Text(
                        "Hours: $hours",
                        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                    )
                    Slider(
                        value = hours.toFloat(),
                        onValueChange = { hours = it.toInt() },
                        valueRange = 0f..23f,
                        steps = 22,
                        colors = SliderDefaults.colors(
                            thumbColor = EnergyOrange,
                            activeTrackColor = EnergyOrange,
                        ),
                    )
                }
                // Minutes
                Column {
                    Text(
                        "Minutes: $minutes",
                        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                    )
                    Slider(
                        value = minutes.toFloat(),
                        onValueChange = { minutes = it.toInt() },
                        valueRange = 0f..55f,
                        steps = 10, // 5-min increments
                        colors = SliderDefaults.colors(
                            thumbColor = EnergyOrange,
                            activeTrackColor = EnergyOrange,
                        ),
                    )
                }
                Text(
                    "Total: ${hours}h ${minutes}m (${hours * 60 + minutes} min)",
                    style = MaterialTheme.typography.bodySmall,
                    color = OnSurfaceVariant,
                )
            }
        },
        confirmButton = {
            Button(
                onClick = { onConfirm(hours, minutes) },
                enabled = hours > 0 || minutes > 0,
                colors = ButtonDefaults.buttonColors(containerColor = EnergyOrange),
            ) {
                Text("OK", fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
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
                TimeField(
                    label = "Start",
                    value = startTime,
                    onClick = onStartTimeClick,
                    modifier = Modifier.weight(1f),
                )
                TimeField(
                    label = "End",
                    value = endTime,
                    onClick = onEndTimeClick,
                    modifier = Modifier.weight(1f),
                )
                TimeField(
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
                    steps = 19,
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

@Composable
private fun TimeField(
    label: String,
    value: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    OutlinedTextField(
        value = value,
        onValueChange = {},
        label = { Text(label) },
        readOnly = true,
        singleLine = true,
        modifier = modifier.clickable { onClick() },
        enabled = false,
        colors = OutlinedTextFieldDefaults.colors(
            disabledTextColor = MaterialTheme.colorScheme.onSurface,
            disabledBorderColor = MaterialTheme.colorScheme.outline,
            disabledLabelColor = MaterialTheme.colorScheme.onSurfaceVariant,
        ),
    )
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

    Button(
        onClick = {
            if (isActive) viewModel.stopWindow(windowId)
            else viewModel.startWindow(windowId)
        },
        modifier = Modifier.fillMaxWidth().height(44.dp),
        shape = RoundedCornerShape(50),
        enabled = (isActive || canStart) && !detailState.isStarting && !detailState.isStopping,
        colors = ButtonDefaults.buttonColors(
            containerColor = if (isActive) MaterialTheme.colorScheme.error else EnergyOrange,
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
}
