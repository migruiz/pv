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
import ovh.tenjo.pv.ChargeRampState
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.api.ChargeRampConfigUpdate
import ovh.tenjo.pv.ui.theme.BatteryGreenContainer
import ovh.tenjo.pv.ui.theme.EnergyOrange
import ovh.tenjo.pv.ui.theme.OnSurfaceVariant
import ovh.tenjo.pv.ui.theme.SurfaceContainer
import kotlin.math.cos
import kotlin.math.PI
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChargeRampScreen(
    viewModel: SolarViewModel,
    onBack: () -> Unit,
) {
    val rampState by viewModel.chargeRamp.collectAsState()
    val config = rampState.config

    // Auto-clear messages
    LaunchedEffect(rampState.message) {
        if (rampState.message != null) {
            kotlinx.coroutines.delay(3000)
            viewModel.clearChargeRampMessage()
        }
    }

    // Editable fields (init from config when it loads)
    var durationMinutes by remember(config) { mutableIntStateOf(config?.durationMinutes ?: 240) }
    var initialPower by remember(config) { mutableIntStateOf(config?.initialPower ?: 200) }
    var topPower by remember(config) { mutableIntStateOf(config?.topPower ?: 2500) }
    var finalPower by remember(config) { mutableIntStateOf(config?.finalPower ?: 200) }

    val savedDuration = config?.durationMinutes ?: 240
    val savedInitial = config?.initialPower ?: 200
    val savedTop = config?.topPower ?: 2500
    val savedFinal = config?.finalPower ?: 200
    val hasChanges = durationMinutes != savedDuration ||
        initialPower != savedInitial ||
        topPower != savedTop ||
        finalPower != savedFinal

    var showDurationPicker by remember { mutableStateOf(false) }
    var showConfirmDialog by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Solar Charge Ramp") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
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
            RampStatusSection(rampState)

            // -- Bell curve preview --
            BellCurvePreview(initialPower, topPower, finalPower)

            // -- Configuration section --
            RampConfigSection(
                durationMinutes = durationMinutes,
                onDurationClick = { showDurationPicker = true },
                initialPower = initialPower,
                onInitialPowerChange = { initialPower = it },
                topPower = topPower,
                onTopPowerChange = { topPower = it },
                finalPower = finalPower,
                onFinalPowerChange = { finalPower = it },
            )

            // -- Save button --
            if (hasChanges) {
                Button(
                    onClick = {
                        viewModel.updateChargeRampConfig(
                            ChargeRampConfigUpdate(
                                durationMinutes = durationMinutes,
                                initialPower = initialPower,
                                topPower = topPower,
                                finalPower = finalPower,
                            ),
                        )
                    },
                    modifier = Modifier.fillMaxWidth().height(44.dp),
                    shape = RoundedCornerShape(50),
                    enabled = !rampState.isSaving,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.primary,
                    ),
                ) {
                    if (rampState.isSaving) {
                        CircularProgressIndicator(Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp)
                    } else {
                        Icon(Icons.Default.Save, contentDescription = null, Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("Save Changes", style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold))
                    }
                }
            }

            // -- Start/Stop button --
            RampControlSection(rampState, viewModel) { showConfirmDialog = true }

            // -- Message --
            rampState.message?.let { msg ->
                Text(
                    msg,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (msg.startsWith("Error")) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                )
            }
        }
    }

    // -- Duration picker --
    if (showDurationPicker) {
        DurationPickerDialog(
            initialHours = durationMinutes / 60,
            initialMinutes = durationMinutes % 60,
            onConfirm = { hours, minutes ->
                durationMinutes = (hours * 60 + minutes).coerceIn(10, 1440)
                showDurationPicker = false
            },
            onDismiss = { showDurationPicker = false },
        )
    }

    // -- Confirm dialog --
    if (showConfirmDialog) {
        val isActive = rampState.status?.active == true
        AlertDialog(
            onDismissRequest = { showConfirmDialog = false },
            icon = {
                Icon(
                    if (isActive) Icons.Default.StopCircle else Icons.Default.PlayArrow,
                    contentDescription = null,
                    tint = if (isActive) MaterialTheme.colorScheme.error else EnergyOrange,
                )
            },
            title = {
                Text(if (isActive) "Stop Charge Ramp?" else "Start Charge Ramp?")
            },
            text = {
                Text(
                    if (isActive) "This will stop the ramp and restore TOU mode."
                    else "This will switch to self-consumption mode and ramp charge power.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showConfirmDialog = false
                        if (isActive) viewModel.stopChargeRamp()
                        else viewModel.startChargeRamp()
                    },
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = if (isActive) MaterialTheme.colorScheme.error else EnergyOrange,
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

// ------------------------------------------------------------------
// Status section
// ------------------------------------------------------------------

@Composable
private fun RampStatusSection(rampState: ChargeRampState) {
    val isActive = rampState.status?.active == true

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
                    if (isActive) "Ramp Active" else "Idle",
                    style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                    color = if (isActive) EnergyOrange else OnSurfaceVariant,
                )
            }

            if (isActive) {
                val status = rampState.status!!
                Spacer(Modifier.height(12.dp))

                // Progress bar
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
                        val totalMins = status.totalMinutes ?: 0
                        val elapsedMins = status.elapsedMinutes ?: 0.0
                        val remaining = (totalMins - elapsedMins).coerceAtLeast(0.0)
                        val hours = (remaining / 60).toInt()
                        val m = (remaining % 60).toInt()
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
// Bell curve preview
// ------------------------------------------------------------------

@Composable
private fun BellCurvePreview(initialPower: Int, topPower: Int, finalPower: Int) {
    val curveColor = EnergyOrange
    val gridColor = OnSurfaceVariant.copy(alpha = 0.2f)

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

                // Grid lines at 200, 1000, 2000, 2500
                listOf(200f, 1000f, 2000f, 2500f).forEach { p ->
                    val y = yForPower(p)
                    drawLine(gridColor, Offset(padLeft, y), Offset(size.width - padRight, y), strokeWidth = 1f)
                }

                // Bell curve path
                val path = Path()
                val steps = 100
                for (i in 0..steps) {
                    val progress = i.toFloat() / steps
                    val power = if (progress <= 0.5f) {
                        val t = progress / 0.5f
                        val factor = (1 - cos(t * PI)).toFloat() / 2
                        initialPower + (topPower - initialPower) * factor
                    } else {
                        val t = (progress - 0.5f) / 0.5f
                        val factor = (1 - cos(t * PI)).toFloat() / 2
                        topPower + (finalPower - topPower) * factor
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
                Text("${initialPower}W", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                Text("${topPower}W", style = MaterialTheme.typography.labelSmall, color = EnergyOrange)
                Text("${finalPower}W", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
            }
        }
    }
}

// ------------------------------------------------------------------
// Configuration section
// ------------------------------------------------------------------

@Composable
private fun RampConfigSection(
    durationMinutes: Int,
    onDurationClick: () -> Unit,
    initialPower: Int,
    onInitialPowerChange: (Int) -> Unit,
    topPower: Int,
    onTopPowerChange: (Int) -> Unit,
    finalPower: Int,
    onFinalPowerChange: (Int) -> Unit,
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

            ReadOnlyTimeField(
                label = "Duration",
                value = "${durationHours}h ${durationMins}m",
                onClick = onDurationClick,
                modifier = Modifier.fillMaxWidth(),
            )

            PowerSlider(
                label = "Initial Power",
                value = initialPower,
                onValueChange = onInitialPowerChange,
            )

            PowerSlider(
                label = "Top Power",
                value = topPower,
                onValueChange = onTopPowerChange,
            )

            PowerSlider(
                label = "Final Power",
                value = finalPower,
                onValueChange = onFinalPowerChange,
            )
        }
    }
}

@Composable
private fun PowerSlider(
    label: String,
    value: Int,
    onValueChange: (Int) -> Unit,
) {
    Column {
        Text(
            "$label: ${value}W",
            style = MaterialTheme.typography.bodyMedium,
        )
        Slider(
            value = value.toFloat(),
            onValueChange = {
                // Round to nearest 100W and clamp to valid range
                val rounded = ((it / 100f).roundToInt() * 100).coerceIn(200, 2500)
                onValueChange(rounded)
            },
            valueRange = 200f..2500f,
            steps = 22,
            colors = SliderDefaults.colors(
                thumbColor = EnergyOrange,
                activeTrackColor = EnergyOrange,
            ),
        )
    }
}

// ------------------------------------------------------------------
// Control section
// ------------------------------------------------------------------

@Composable
private fun RampControlSection(
    rampState: ChargeRampState,
    viewModel: SolarViewModel,
    onConfirmClick: () -> Unit,
) {
    val isActive = rampState.status?.active == true

    Button(
        onClick = onConfirmClick,
        modifier = Modifier.fillMaxWidth().height(44.dp),
        shape = RoundedCornerShape(50),
        enabled = !rampState.isStarting && !rampState.isStopping,
        colors = ButtonDefaults.buttonColors(
            containerColor = if (isActive) MaterialTheme.colorScheme.error else BatteryGreenContainer,
            contentColor = Color.White,
        ),
    ) {
        if (rampState.isStarting || rampState.isStopping) {
            CircularProgressIndicator(Modifier.size(18.dp), color = Color.White, strokeWidth = 2.dp)
        } else {
            Icon(
                if (isActive) Icons.Default.StopCircle else Icons.Default.PlayArrow,
                contentDescription = null,
                Modifier.size(18.dp),
            )
            Spacer(Modifier.width(8.dp))
            Text(
                if (isActive) "Stop Ramp" else "Start Ramp",
                style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold),
            )
        }
    }
}
