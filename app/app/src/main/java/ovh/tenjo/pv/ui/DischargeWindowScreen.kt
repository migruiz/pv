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
import ovh.tenjo.pv.api.WindowSettings
import ovh.tenjo.pv.api.WindowState
import ovh.tenjo.pv.ui.theme.BatteryGreen
import ovh.tenjo.pv.ui.theme.EnergyOrange
import ovh.tenjo.pv.ui.theme.OnSurfaceVariant
import ovh.tenjo.pv.ui.theme.SurfaceContainer
import java.util.Calendar

/** A new window starts now, so a one-off discharge is: +, set the end and target, Save. */
private fun newWindowSettings(): WindowSettings {
    val now = Calendar.getInstance()
    return WindowSettings(
        name = "",
        startTime = "%02d:%02d".format(now.get(Calendar.HOUR_OF_DAY), now.get(Calendar.MINUTE)),
        durationMinutes = 60,
        targetSoc = 20.0,
        notify = true,
        enabled = true,
    )
}

/**
 * Create (windowId null) or edit a discharge window. Saving applies it straight away: the API
 * starts, corrects or stops the discharge before it replies, and the list shows the result.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DischargeWindowScreen(
    windowId: String?,
    viewModel: SolarViewModel,
    onBack: () -> Unit,
) {
    val windowsState by viewModel.windows.collectAsState()
    val editor by viewModel.editor.collectAsState()
    val dashboardState by viewModel.dashboard.collectAsState()
    val window = windowId?.let { id -> windowsState.windows.find { it.id == id } }

    LaunchedEffect(editor.done) {
        if (editor.done) onBack()
    }

    if (windowId != null && window == null) {
        Box(
            Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface),
            contentAlignment = Alignment.Center,
        ) {
            CircularProgressIndicator()
        }
        return
    }

    // Keyed on the window id only: the list refreshing in the background never resets what is being typed
    val saved = remember(windowId) { window?.settings() ?: newWindowSettings() }
    var name by remember(windowId) { mutableStateOf(saved.name) }
    var startTime by remember(windowId) { mutableStateOf(saved.startTime) }
    var endTime by remember(windowId) { mutableStateOf(calcEndTime(saved.startTime, saved.durationMinutes)) }
    var targetSoc by remember(windowId) { mutableFloatStateOf(saved.targetSoc.toFloat()) }
    var notify by remember(windowId) { mutableStateOf(saved.notify) }
    var enabled by remember(windowId) { mutableStateOf(saved.enabled) }
    val durationMinutes = calcDuration(startTime, endTime)

    val settings = WindowSettings(name, startTime, durationMinutes, targetSoc.toDouble(), notify, enabled)
    val problem = when {
        name.isBlank() -> "Give the window a name"
        durationMinutes == 0 -> "The end must be different from the start"
        else -> null
    }
    val canSave = problem == null && (windowId == null || settings != saved) &&
        !editor.isSaving && !editor.isDeleting

    var showStartPicker by remember { mutableStateOf(false) }
    var showEndPicker by remember { mutableStateOf(false) }
    var showDurationPicker by remember { mutableStateOf(false) }
    var showDeleteConfirm by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (window == null) "New discharge window" else window.name) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    if (window != null) {
                        IconButton(onClick = { showDeleteConfirm = true }, enabled = !editor.isDeleting) {
                            Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error)
                        }
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
            if (window != null) {
                StatusSection(window.state, window.enabled)
            }

            Surface(
                shape = RoundedCornerShape(16.dp),
                color = SurfaceContainer,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(
                    Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it },
                        label = { Text("Name") },
                        placeholder = { Text("e.g. Night Export") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        ReadOnlyTimeField("Start", startTime, { showStartPicker = true }, Modifier.weight(1f))
                        ReadOnlyTimeField("End", endTime, { showEndPicker = true }, Modifier.weight(1f))
                        ReadOnlyTimeField(
                            "Duration",
                            "${durationMinutes / 60}h ${durationMinutes % 60}m",
                            { showDurationPicker = true },
                            Modifier.weight(1f),
                        )
                    }

                    Column {
                        Text("Target: ${targetSoc.toInt()}%", style = MaterialTheme.typography.bodyMedium)
                        Slider(
                            value = targetSoc,
                            onValueChange = { targetSoc = it },
                            valueRange = 0f..100f,
                            steps = 99,
                            colors = SliderDefaults.colors(thumbColor = EnergyOrange, activeTrackColor = EnergyOrange),
                        )
                    }

                    SwitchRow("Notifications", notify) { notify = it }
                    SwitchRow("Enabled", enabled) { enabled = it }
                }
            }

            Text(
                "Estimated discharge: %.2f kWh (from %.0f%% to %.0f%%)".format(
                    estimateDischargeEnergy(dashboardState.batterySoc, targetSoc.toDouble()),
                    dashboardState.batterySoc,
                    targetSoc.toDouble(),
                ),
                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                color = EnergyOrange,
                modifier = Modifier.fillMaxWidth(),
            )

            Button(
                onClick = { viewModel.saveWindow(windowId, settings) },
                enabled = canSave,
                modifier = Modifier.fillMaxWidth().height(44.dp),
                shape = RoundedCornerShape(50),
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
            ) {
                if (editor.isSaving) {
                    CircularProgressIndicator(Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp)
                } else {
                    Icon(Icons.Default.Save, contentDescription = null, Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(
                        if (windowId == null) "Create" else "Save",
                        style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold),
                    )
                }
            }

            (editor.error ?: problem)?.let { message ->
                Text(
                    message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (editor.error != null) MaterialTheme.colorScheme.error else OnSurfaceVariant,
                )
            }
        }
    }

    if (showStartPicker) {
        TimePickerDialog(
            title = "Start",
            initialHour = parseTimeToMinutes(startTime) / 60,
            initialMinute = parseTimeToMinutes(startTime) % 60,
            onConfirm = { hour, minute ->
                // Keep the duration: the end moves with the start
                val duration = durationMinutes
                startTime = "%02d:%02d".format(hour, minute)
                endTime = calcEndTime(startTime, duration)
                showStartPicker = false
            },
            onDismiss = { showStartPicker = false },
        )
    }

    if (showEndPicker) {
        TimePickerDialog(
            title = "End",
            initialHour = parseTimeToMinutes(endTime) / 60,
            initialMinute = parseTimeToMinutes(endTime) % 60,
            onConfirm = { hour, minute ->
                endTime = "%02d:%02d".format(hour, minute)
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
                endTime = calcEndTime(startTime, hours * 60 + minutes)
                showDurationPicker = false
            },
            onDismiss = { showDurationPicker = false },
        )
    }

    if (showDeleteConfirm && window != null) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            icon = { Icon(Icons.Default.Delete, contentDescription = null, tint = MaterialTheme.colorScheme.error) },
            title = { Text("Delete window?") },
            text = {
                Text(
                    if (window.state.discharging) "\"${window.name}\" is discharging now: deleting it stops the discharge."
                    else "This permanently deletes \"${window.name}\".",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDeleteConfirm = false
                        viewModel.deleteWindow(window.id)
                    },
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                ) {
                    Text("Delete")
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Switch(
            checked = checked,
            onCheckedChange = onChange,
            colors = SwitchDefaults.colors(checkedTrackColor = EnergyOrange),
        )
    }
}

@Composable
private fun StatusSection(state: WindowState, enabled: Boolean) {
    val (icon, label, color) = when {
        state.discharging -> Triple(Icons.Default.PlayCircle, "Discharging now", EnergyOrange)
        state.targetReached -> Triple(Icons.Default.CheckCircle, "Target reached: done until tomorrow", BatteryGreen)
        !enabled -> Triple(Icons.Default.PauseCircle, "Switched off", OnSurfaceVariant)
        else -> Triple(Icons.Default.Schedule, "Not discharging", OnSurfaceVariant)
    }

    Surface(
        shape = RoundedCornerShape(16.dp),
        color = SurfaceContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text(
                    label,
                    style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                    color = color,
                )
            }

            if (state.discharging) {
                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    StatusValue("POWER", "%.2f kW".format(state.powerKw ?: 0.0), Alignment.Start)
                    StatusValue("BATTERY", "%.0f%%".format(state.soc ?: 0.0), Alignment.CenterHorizontally)
                    val mins = (state.minutesRemaining ?: 0.0).toInt()
                    StatusValue("TIME LEFT", "${mins / 60}h ${mins % 60}m", Alignment.End)
                }
            }
        }
    }
}

@Composable
private fun StatusValue(label: String, value: String, alignment: Alignment.Horizontal) {
    Column(horizontalAlignment = alignment) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold))
    }
}
