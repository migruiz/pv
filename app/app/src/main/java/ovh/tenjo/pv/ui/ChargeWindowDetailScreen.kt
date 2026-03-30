package ovh.tenjo.pv.ui

import androidx.compose.foundation.Canvas
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ovh.tenjo.pv.ChargeWindowDetailState
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.api.ChargeWindowUpdate
import ovh.tenjo.pv.ui.theme.BatteryGreen
import ovh.tenjo.pv.ui.theme.BatteryGreenContainer
import ovh.tenjo.pv.ui.theme.EnergyOrange
import ovh.tenjo.pv.ui.theme.ErrorRed
import ovh.tenjo.pv.ui.theme.OnSurfaceVariant
import ovh.tenjo.pv.ui.theme.SurfaceContainer
import java.util.Calendar
import kotlin.math.cos
import kotlin.math.PI
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChargeWindowDetailScreen(
    windowId: String,
    viewModel: SolarViewModel,
    onBack: () -> Unit,
) {
    val chargeState by viewModel.chargeWindows.collectAsState()
    val detailState by viewModel.chargeWindowDetail.collectAsState()
    val window = chargeState.windows.find { it.id == windowId }
    val status = chargeState.statuses[windowId]

    LaunchedEffect(detailState.message) {
        if (detailState.message == "Deleted") {
            onBack()
        } else if (detailState.message != null) {
            kotlinx.coroutines.delay(3000)
            viewModel.clearChargeWindowDetailMessage()
        }
    }

    // Editable fields
    var name by remember(window) { mutableStateOf(window?.name ?: "") }
    var startTime by remember(window) { mutableStateOf(window?.startTime ?: "10:00") }
    var startPower by remember(window) { mutableIntStateOf(window?.startPower ?: 200) }
    var peakTime by remember(window) { mutableStateOf(window?.peakTime ?: "12:00") }
    var peakPower by remember(window) { mutableIntStateOf(window?.peakPower ?: 2500) }
    var endTime by remember(window) { mutableStateOf(window?.endTime ?: "14:00") }
    var endPower by remember(window) { mutableIntStateOf(window?.endPower ?: 200) }
    var notify by remember(window) { mutableStateOf(window?.notify ?: true) }
    var enabled by remember(window) { mutableStateOf(window?.enabled ?: true) }

    val hasChanges = window != null && (
        name != window.name ||
        startTime != window.startTime || startPower != window.startPower ||
        peakTime != window.peakTime || peakPower != window.peakPower ||
        endTime != window.endTime || endPower != window.endPower ||
        notify != window.notify || enabled != window.enabled
    )

    var showStartPicker by remember { mutableStateOf(false) }
    var showPeakPicker by remember { mutableStateOf(false) }
    var showEndPicker by remember { mutableStateOf(false) }
    var showConfirmDialog by remember { mutableStateOf(false) }
    var showDeleteDialog by remember { mutableStateOf(false) }
    var showPresetMenu by remember { mutableStateOf(false) }

    val isActive = status?.active == true

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(window?.name ?: "Charge Window") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { showDeleteDialog = true }) {
                        Icon(Icons.Default.Delete, contentDescription = "Delete", tint = ErrorRed)
                    }
                },
            )
        },
    ) { padding ->
        if (window == null) {
            Box(
                Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) {
                Text("Window not found", color = OnSurfaceVariant)
            }
            return@Scaffold
        }

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
            ChargeStatusSection(status)

            // -- Bell curve preview --
            AsymmetricBellCurvePreview(
                startPower = startPower,
                peakPower = peakPower,
                endPower = endPower,
                startTime = startTime,
                peakTime = peakTime,
                endTime = endTime,
            )

            // -- Configuration section --
            Surface(
                shape = RoundedCornerShape(16.dp),
                color = SurfaceContainer,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(
                    Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Configuration", style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold))
                        Box {
                            TextButton(onClick = { showPresetMenu = true }) {
                                Text("Presets", style = MaterialTheme.typography.labelMedium)
                            }
                            DropdownMenu(
                                expanded = showPresetMenu,
                                onDismissRequest = { showPresetMenu = false },
                            ) {
                                DropdownMenuItem(
                                    text = { Text("Mid-day (10:00-14:00)") },
                                    onClick = {
                                        startTime = "10:00"; startPower = 200
                                        peakTime = "12:00"; peakPower = 2500
                                        endTime = "14:00"; endPower = 200
                                        showPresetMenu = false
                                    },
                                )
                                DropdownMenuItem(
                                    text = { Text("Now + 4 hours") },
                                    onClick = {
                                        val cal = Calendar.getInstance()
                                        val nowH = cal.get(Calendar.HOUR_OF_DAY)
                                        val nowM = cal.get(Calendar.MINUTE)
                                        startTime = "%02d:%02d".format(nowH, nowM)
                                        peakTime = "%02d:%02d".format((nowH + 2) % 24, nowM)
                                        endTime = "%02d:%02d".format((nowH + 4) % 24, nowM)
                                        startPower = 200; peakPower = 2500; endPower = 200
                                        showPresetMenu = false
                                    },
                                )
                            }
                        }
                    }

                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it },
                        label = { Text("Name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )

                    // Start time + power
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        ReadOnlyTimeField("Start", startTime, { showStartPicker = true }, Modifier.weight(1f))
                        Column(Modifier.weight(1f)) {
                            Text("Start: ${startPower}W", style = MaterialTheme.typography.bodyMedium)
                            Slider(
                                value = startPower.toFloat(),
                                onValueChange = { startPower = ((it / 100f).roundToInt() * 100).coerceIn(200, 2500) },
                                valueRange = 200f..2500f,
                                steps = 22,
                                colors = SliderDefaults.colors(thumbColor = EnergyOrange, activeTrackColor = EnergyOrange),
                            )
                        }
                    }

                    // Peak time + power
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        ReadOnlyTimeField("Peak", peakTime, { showPeakPicker = true }, Modifier.weight(1f))
                        Column(Modifier.weight(1f)) {
                            Text("Peak: ${peakPower}W", style = MaterialTheme.typography.bodyMedium)
                            Slider(
                                value = peakPower.toFloat(),
                                onValueChange = { peakPower = ((it / 100f).roundToInt() * 100).coerceIn(200, 2500) },
                                valueRange = 200f..2500f,
                                steps = 22,
                                colors = SliderDefaults.colors(thumbColor = EnergyOrange, activeTrackColor = EnergyOrange),
                            )
                        }
                    }

                    // End time + power
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        ReadOnlyTimeField("End", endTime, { showEndPicker = true }, Modifier.weight(1f))
                        Column(Modifier.weight(1f)) {
                            Text("End: ${endPower}W", style = MaterialTheme.typography.bodyMedium)
                            Slider(
                                value = endPower.toFloat(),
                                onValueChange = { endPower = ((it / 100f).roundToInt() * 100).coerceIn(200, 2500) },
                                valueRange = 200f..2500f,
                                steps = 22,
                                colors = SliderDefaults.colors(thumbColor = EnergyOrange, activeTrackColor = EnergyOrange),
                            )
                        }
                    }

                    // Toggles
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Notifications", style = MaterialTheme.typography.bodyMedium)
                        Switch(
                            checked = notify,
                            onCheckedChange = { notify = it },
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
                            onCheckedChange = { enabled = it },
                            colors = SwitchDefaults.colors(checkedTrackColor = BatteryGreen),
                        )
                    }
                }
            }

            // -- Save button --
            if (hasChanges) {
                Button(
                    onClick = {
                        viewModel.updateChargeWindow(
                            windowId,
                            ChargeWindowUpdate(
                                name = name,
                                startTime = startTime, startPower = startPower,
                                peakTime = peakTime, peakPower = peakPower,
                                endTime = endTime, endPower = endPower,
                                notify = notify, enabled = enabled,
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

            // -- Start/Stop button --
            Button(
                onClick = { showConfirmDialog = true },
                modifier = Modifier.fillMaxWidth().height(44.dp),
                shape = RoundedCornerShape(50),
                enabled = !detailState.isStarting && !detailState.isStopping,
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
                        if (isActive) "Stop Charge" else "Start Charge",
                        style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold),
                    )
                }
            }

            // -- Message --
            detailState.message?.let { msg ->
                Text(
                    msg,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (msg.startsWith("Error")) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                )
            }
        }
    }

    // Time pickers
    if (showStartPicker) {
        TimePickerDialog(
            title = "Start Time",
            initialHour = parseTimeToMinutes(startTime) / 60,
            initialMinute = parseTimeToMinutes(startTime) % 60,
            onConfirm = { h, m -> startTime = "%02d:%02d".format(h, m); showStartPicker = false },
            onDismiss = { showStartPicker = false },
        )
    }
    if (showPeakPicker) {
        TimePickerDialog(
            title = "Peak Time",
            initialHour = parseTimeToMinutes(peakTime) / 60,
            initialMinute = parseTimeToMinutes(peakTime) % 60,
            onConfirm = { h, m -> peakTime = "%02d:%02d".format(h, m); showPeakPicker = false },
            onDismiss = { showPeakPicker = false },
        )
    }
    if (showEndPicker) {
        TimePickerDialog(
            title = "End Time",
            initialHour = parseTimeToMinutes(endTime) / 60,
            initialMinute = parseTimeToMinutes(endTime) % 60,
            onConfirm = { h, m -> endTime = "%02d:%02d".format(h, m); showEndPicker = false },
            onDismiss = { showEndPicker = false },
        )
    }

    // Confirm dialog
    if (showConfirmDialog) {
        AlertDialog(
            onDismissRequest = { showConfirmDialog = false },
            icon = {
                Icon(
                    if (isActive) Icons.Default.StopCircle else Icons.Default.PlayArrow,
                    contentDescription = null,
                    tint = if (isActive) MaterialTheme.colorScheme.error else EnergyOrange,
                )
            },
            title = { Text(if (isActive) "Stop Charge?" else "Start Charge?") },
            text = {
                Text(
                    if (isActive) "This will stop the charge and restore TOU mode."
                    else "This will switch to self-consumption mode and ramp charge power.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showConfirmDialog = false
                        if (isActive) viewModel.stopChargeWindow(windowId)
                        else viewModel.startChargeWindow(windowId)
                    },
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = if (isActive) MaterialTheme.colorScheme.error else EnergyOrange,
                    ),
                ) { Text(if (isActive) "Stop" else "Start") }
            },
            dismissButton = {
                TextButton(onClick = { showConfirmDialog = false }) { Text("Cancel") }
            },
        )
    }

    // Delete dialog
    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            icon = { Icon(Icons.Default.Delete, contentDescription = null, tint = ErrorRed) },
            title = { Text("Delete Window?") },
            text = { Text("This will permanently delete '${window?.name}'.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDeleteDialog = false
                        viewModel.deleteChargeWindow(windowId)
                    },
                    colors = ButtonDefaults.textButtonColors(contentColor = ErrorRed),
                ) { Text("Delete") }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) { Text("Cancel") }
            },
        )
    }
}

// ------------------------------------------------------------------
// Status section
// ------------------------------------------------------------------

@Composable
private fun ChargeStatusSection(status: ovh.tenjo.pv.api.ChargeWindowStatus?) {
    val isActive = status?.active == true

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
                    if (isActive) "Charging" else "Idle",
                    style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                    color = if (isActive) EnergyOrange else OnSurfaceVariant,
                )
            }

            if (isActive && status != null) {
                Spacer(Modifier.height(12.dp))

                LinearProgressIndicator(
                    progress = { (status.progress ?: 0.0).toFloat() },
                    modifier = Modifier.fillMaxWidth().height(6.dp),
                    color = EnergyOrange,
                    trackColor = OnSurfaceVariant.copy(alpha = 0.2f),
                )

                Spacer(Modifier.height(12.dp))

                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column {
                        Text("POWER", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                        Text(
                            "${status.currentPowerW ?: 0}W",
                            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                        )
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("PROGRESS", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                        Text(
                            "${((status.progress ?: 0.0) * 100).toInt()}%",
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
// Asymmetric bell curve preview
// ------------------------------------------------------------------

@Composable
private fun AsymmetricBellCurvePreview(
    startPower: Int,
    peakPower: Int,
    endPower: Int,
    startTime: String,
    peakTime: String,
    endTime: String,
) {
    val curveColor = EnergyOrange
    val gridColor = OnSurfaceVariant.copy(alpha = 0.2f)

    // Calculate proportional peak position
    val startMins = parseTimeToMinutes(startTime)
    var peakMins = parseTimeToMinutes(peakTime)
    var endMins = parseTimeToMinutes(endTime)
    if (peakMins <= startMins) peakMins += 1440
    if (endMins <= peakMins) endMins += 1440
    val totalMins = endMins - startMins
    val peakFraction = if (totalMins > 0) (peakMins - startMins).toFloat() / totalMins else 0.5f

    Surface(
        shape = RoundedCornerShape(16.dp),
        color = SurfaceContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            Text("Power Curve", style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold))
            Spacer(Modifier.height(8.dp))

            Canvas(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(100.dp),
            ) {
                val padLeft = 40.dp.toPx()
                val padRight = 8.dp.toPx()
                val padTop = 8.dp.toPx()
                val padBottom = 20.dp.toPx()
                val w = size.width - padLeft - padRight
                val h = size.height - padTop - padBottom

                val minP = 200f
                val maxP = 2500f

                fun yForPower(power: Float): Float {
                    return padTop + h * (1 - (power - minP) / (maxP - minP))
                }

                // Grid lines
                listOf(200f, 1000f, 2000f, 2500f).forEach { p ->
                    val y = yForPower(p)
                    drawLine(gridColor, Offset(padLeft, y), Offset(size.width - padRight, y), strokeWidth = 1f)
                }

                // Asymmetric bell curve
                val path = Path()
                val steps = 100
                for (i in 0..steps) {
                    val progress = i.toFloat() / steps
                    val power = if (progress <= peakFraction) {
                        val t = if (peakFraction > 0) progress / peakFraction else 0f
                        val factor = (1 - cos(t * PI)).toFloat() / 2
                        startPower + (peakPower - startPower) * factor
                    } else {
                        val t = if (peakFraction < 1) (progress - peakFraction) / (1 - peakFraction) else 1f
                        val factor = (1 - cos(t * PI)).toFloat() / 2
                        peakPower + (endPower - peakPower) * factor
                    }
                    val x = padLeft + w * progress
                    val y = yForPower(power)
                    if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                }
                drawPath(path, curveColor, style = Stroke(width = 3.dp.toPx()))
            }

            // Labels
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("$startTime ${startPower}W", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                Text("$peakTime ${peakPower}W", style = MaterialTheme.typography.labelSmall, color = EnergyOrange)
                Text("$endTime ${endPower}W", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
            }
        }
    }
}
