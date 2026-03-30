package ovh.tenjo.pv.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.WindowDetailState
import ovh.tenjo.pv.api.DischargeWindowStatus
import ovh.tenjo.pv.api.DischargeWindowUpdate
import ovh.tenjo.pv.ui.theme.EnergyOrange
import ovh.tenjo.pv.ui.theme.OnSurfaceVariant
import ovh.tenjo.pv.ui.theme.SurfaceContainer

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
    var durationMinutes by remember(window) { mutableStateOf(window.durationMinutes.toString()) }
    var targetSoc by remember(window) { mutableFloatStateOf(window.targetSoc.toFloat()) }
    var notify by remember(window) { mutableStateOf(window.notify) }
    var enabled by remember(window) { mutableStateOf(window.enabled) }

    val hasChanges = name != window.name ||
        startTime != window.startTime ||
        durationMinutes != window.durationMinutes.toString() ||
        targetSoc != window.targetSoc.toFloat() ||
        notify != window.notify ||
        enabled != window.enabled

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
                onStartTimeChange = { startTime = it },
                durationMinutes = durationMinutes,
                onDurationChange = { durationMinutes = it },
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
                        val dur = durationMinutes.toIntOrNull() ?: window.durationMinutes
                        viewModel.updateWindow(
                            windowId,
                            DischargeWindowUpdate(
                                name = name,
                                startTime = startTime,
                                durationMinutes = dur,
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
            ControlSection(windowId, status, detailState, viewModel)

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
}

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

@Composable
private fun ConfigSection(
    name: String,
    onNameChange: (String) -> Unit,
    startTime: String,
    onStartTimeChange: (String) -> Unit,
    durationMinutes: String,
    onDurationChange: (String) -> Unit,
    targetSoc: Float,
    onTargetSocChange: (Float) -> Unit,
    notify: Boolean,
    onNotifyChange: (Boolean) -> Unit,
    enabled: Boolean,
    onEnabledChange: (Boolean) -> Unit,
) {
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

            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = startTime,
                    onValueChange = onStartTimeChange,
                    label = { Text("Start Time") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                    placeholder = { Text("HH:MM") },
                )
                OutlinedTextField(
                    value = durationMinutes,
                    onValueChange = { if (it.all { c -> c.isDigit() }) onDurationChange(it) },
                    label = { Text("Duration (min)") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
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
                    steps = 19, // 5% increments
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
private fun ControlSection(
    windowId: String,
    status: DischargeWindowStatus?,
    detailState: WindowDetailState,
    viewModel: SolarViewModel,
) {
    val isActive = status?.active == true

    Button(
        onClick = {
            if (isActive) viewModel.stopWindow(windowId)
            else viewModel.startWindow(windowId)
        },
        modifier = Modifier.fillMaxWidth().height(44.dp),
        shape = RoundedCornerShape(50),
        enabled = !detailState.isStarting && !detailState.isStopping,
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
                if (isActive) "Stop Discharge" else "Start Discharge",
                style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold),
            )
        }
    }
}
