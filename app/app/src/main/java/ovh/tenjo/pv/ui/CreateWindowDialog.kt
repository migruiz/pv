package ovh.tenjo.pv.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.api.ChargeWindowCreate
import ovh.tenjo.pv.api.DischargeWindowCreate
import ovh.tenjo.pv.ui.theme.BatteryGreen
import ovh.tenjo.pv.ui.theme.EnergyOrange
import java.util.Calendar
import kotlin.math.roundToInt

@Composable
fun CreateWindowDialog(
    viewModel: SolarViewModel,
    onDismiss: () -> Unit,
) {
    var windowType by remember { mutableStateOf("discharge") }

    // Discharge fields
    var dName by remember { mutableStateOf("") }
    var dStartTime by remember { mutableStateOf("22:00") }
    var dEndTime by remember { mutableStateOf("02:00") }
    var dDuration by remember { mutableIntStateOf(240) }
    var dTargetSoc by remember { mutableFloatStateOf(0f) }
    var dNotify by remember { mutableStateOf(true) }

    // Charge fields
    var cName by remember { mutableStateOf("") }
    var cStartTime by remember { mutableStateOf("10:00") }
    var cStartPower by remember { mutableIntStateOf(200) }
    var cPeakTime by remember { mutableStateOf("12:00") }
    var cPeakPower by remember { mutableIntStateOf(2500) }
    var cEndTime by remember { mutableStateOf("14:00") }
    var cEndPower by remember { mutableIntStateOf(200) }
    var cNotify by remember { mutableStateOf(true) }

    // Pickers
    var showStartPicker by remember { mutableStateOf(false) }
    var showEndPicker by remember { mutableStateOf(false) }
    var showDurationPicker by remember { mutableStateOf(false) }
    var showPeakPicker by remember { mutableStateOf(false) }
    var showPresetMenu by remember { mutableStateOf(false) }

    val detailState by viewModel.windowDetail.collectAsState()
    val chargeDetailState by viewModel.chargeWindowDetail.collectAsState()
    val dashboardState by viewModel.dashboard.collectAsState()

    LaunchedEffect(detailState.message) {
        if (detailState.message == "Window created") onDismiss()
    }
    LaunchedEffect(chargeDetailState.message) {
        if (chargeDetailState.message == "Window created") onDismiss()
    }

    val dh = dDuration / 60
    val dm = dDuration % 60
    val isSaving = if (windowType == "discharge") detailState.isSaving else chargeDetailState.isSaving

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New Window") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                // Type selector
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    FilterChip(
                        selected = windowType == "discharge",
                        onClick = { windowType = "discharge" },
                        label = { Text("Discharge") },
                        modifier = Modifier.weight(1f),
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = EnergyOrange.copy(alpha = 0.15f),
                            selectedLabelColor = EnergyOrange,
                        ),
                    )
                    FilterChip(
                        selected = windowType == "charge",
                        onClick = { windowType = "charge" },
                        label = { Text("Charge") },
                        modifier = Modifier.weight(1f),
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = BatteryGreen.copy(alpha = 0.15f),
                            selectedLabelColor = BatteryGreen,
                        ),
                    )
                }

                if (windowType == "discharge") {
                    // -- Discharge form --
                    OutlinedTextField(
                        value = dName,
                        onValueChange = { dName = it },
                        label = { Text("Name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = { Text("e.g. Morning Discharge") },
                    )

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        ReadOnlyTimeField("Start", dStartTime, { showStartPicker = true }, Modifier.weight(1f))
                        ReadOnlyTimeField("End", dEndTime, { showEndPicker = true }, Modifier.weight(1f))
                    }

                    ReadOnlyTimeField(
                        "Duration",
                        "${dh}h ${dm}m ($dDuration min)",
                        { showDurationPicker = true },
                        Modifier.fillMaxWidth(),
                    )

                    Column {
                        Text("Target SOC: ${dTargetSoc.toInt()}%", style = MaterialTheme.typography.bodyMedium)
                        Slider(
                            value = dTargetSoc,
                            onValueChange = { dTargetSoc = it },
                            valueRange = 0f..100f,
                            steps = 99,
                            colors = SliderDefaults.colors(thumbColor = EnergyOrange, activeTrackColor = EnergyOrange),
                        )
                    }

                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Notifications", style = MaterialTheme.typography.bodyMedium)
                        Switch(
                            checked = dNotify,
                            onCheckedChange = { dNotify = it },
                            colors = SwitchDefaults.colors(checkedTrackColor = EnergyOrange),
                        )
                    }

                    val estDischarge = estimateDischargeEnergy(dashboardState.batterySoc, dTargetSoc.toDouble())
                    Text(
                        "Estimated discharge: %.2f kWh (from %.0f%% to %.0f%%)".format(
                            estDischarge, dashboardState.batterySoc, dTargetSoc.toDouble(),
                        ),
                        style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Bold),
                        color = EnergyOrange,
                    )
                } else {
                    // -- Charge form --
                    OutlinedTextField(
                        value = cName,
                        onValueChange = { cName = it },
                        label = { Text("Name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = { Text("e.g. Midday Charge") },
                    )

                    // Presets
                    Box {
                        TextButton(onClick = { showPresetMenu = true }) {
                            Text("Apply Preset", style = MaterialTheme.typography.labelMedium)
                        }
                        DropdownMenu(
                            expanded = showPresetMenu,
                            onDismissRequest = { showPresetMenu = false },
                        ) {
                            DropdownMenuItem(
                                text = { Text("Mid-day (10:00-14:00)") },
                                onClick = {
                                    cStartTime = "10:00"; cStartPower = 200
                                    cPeakTime = "12:00"; cPeakPower = 2500
                                    cEndTime = "14:00"; cEndPower = 200
                                    showPresetMenu = false
                                },
                            )
                            DropdownMenuItem(
                                text = { Text("Now + 4 hours") },
                                onClick = {
                                    val cal = Calendar.getInstance()
                                    val nowH = cal.get(Calendar.HOUR_OF_DAY)
                                    val nowM = cal.get(Calendar.MINUTE)
                                    cStartTime = "%02d:%02d".format(nowH, nowM)
                                    cPeakTime = "%02d:%02d".format((nowH + 2) % 24, nowM)
                                    cEndTime = "%02d:%02d".format((nowH + 4) % 24, nowM)
                                    cStartPower = 200; cPeakPower = 2500; cEndPower = 200
                                    showPresetMenu = false
                                },
                            )
                        }
                    }

                    ReadOnlyTimeField("Start", cStartTime, { showStartPicker = true }, Modifier.fillMaxWidth())
                    Column {
                        Text("Start Power: ${cStartPower}W", style = MaterialTheme.typography.bodyMedium)
                        Slider(
                            value = cStartPower.toFloat(),
                            onValueChange = { cStartPower = ((it / 100f).roundToInt() * 100).coerceIn(200, 2500) },
                            valueRange = 200f..2500f,
                            steps = 22,
                            colors = SliderDefaults.colors(thumbColor = EnergyOrange, activeTrackColor = EnergyOrange),
                        )
                    }

                    ReadOnlyTimeField("Peak", cPeakTime, { showPeakPicker = true }, Modifier.fillMaxWidth())
                    Column {
                        Text("Peak Power: ${cPeakPower}W", style = MaterialTheme.typography.bodyMedium)
                        Slider(
                            value = cPeakPower.toFloat(),
                            onValueChange = { cPeakPower = ((it / 100f).roundToInt() * 100).coerceIn(200, 2500) },
                            valueRange = 200f..2500f,
                            steps = 22,
                            colors = SliderDefaults.colors(thumbColor = EnergyOrange, activeTrackColor = EnergyOrange),
                        )
                    }

                    ReadOnlyTimeField("End", cEndTime, { showEndPicker = true }, Modifier.fillMaxWidth())
                    Column {
                        Text("End Power: ${cEndPower}W", style = MaterialTheme.typography.bodyMedium)
                        Slider(
                            value = cEndPower.toFloat(),
                            onValueChange = { cEndPower = ((it / 100f).roundToInt() * 100).coerceIn(200, 2500) },
                            valueRange = 200f..2500f,
                            steps = 22,
                            colors = SliderDefaults.colors(thumbColor = EnergyOrange, activeTrackColor = EnergyOrange),
                        )
                    }

                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Notifications", style = MaterialTheme.typography.bodyMedium)
                        Switch(
                            checked = cNotify,
                            onCheckedChange = { cNotify = it },
                            colors = SwitchDefaults.colors(checkedTrackColor = EnergyOrange),
                        )
                    }

                    val estCharge = estimateChargeEnergy(cStartTime, cStartPower, cPeakTime, cPeakPower, cEndTime, cEndPower)
                    Text(
                        "Estimated charge: %.2f kWh".format(estCharge),
                        style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Bold),
                        color = BatteryGreen,
                    )
                }

                // Error message
                val msg = if (windowType == "discharge") detailState.message else chargeDetailState.message
                msg?.let {
                    if (it.startsWith("Error")) {
                        Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        },
        confirmButton = {
            val canCreate = if (windowType == "discharge") {
                dName.isNotBlank() && dDuration > 0 && !isSaving
            } else {
                cName.isNotBlank() && !isSaving
            }
            Button(
                onClick = {
                    if (windowType == "discharge") {
                        viewModel.createWindow(
                            DischargeWindowCreate(
                                name = dName,
                                startTime = dStartTime,
                                durationMinutes = dDuration,
                                targetSoc = dTargetSoc.toDouble(),
                                notify = dNotify,
                            ),
                        )
                    } else {
                        viewModel.createChargeWindow(
                            ChargeWindowCreate(
                                name = cName,
                                startTime = cStartTime, startPower = cStartPower,
                                peakTime = cPeakTime, peakPower = cPeakPower,
                                endTime = cEndTime, endPower = cEndPower,
                                notify = cNotify,
                            ),
                        )
                    }
                },
                enabled = canCreate,
                shape = RoundedCornerShape(50),
                colors = ButtonDefaults.buttonColors(containerColor = EnergyOrange),
            ) {
                if (isSaving) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                } else {
                    Text("Create", fontWeight = FontWeight.Bold)
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )

    // Time pickers (shared)
    if (showStartPicker) {
        val currentStart = if (windowType == "discharge") dStartTime else cStartTime
        TimePickerDialog(
            title = "Start Time",
            initialHour = parseTimeToMinutes(currentStart) / 60,
            initialMinute = parseTimeToMinutes(currentStart) % 60,
            onConfirm = { hour, minute ->
                val time = "%02d:%02d".format(hour, minute)
                if (windowType == "discharge") {
                    dStartTime = time
                    dEndTime = calcEndTime(dStartTime, dDuration)
                } else {
                    cStartTime = time
                }
                showStartPicker = false
            },
            onDismiss = { showStartPicker = false },
        )
    }

    if (showEndPicker) {
        val currentEnd = if (windowType == "discharge") dEndTime else cEndTime
        TimePickerDialog(
            title = "End Time",
            initialHour = parseTimeToMinutes(currentEnd) / 60,
            initialMinute = parseTimeToMinutes(currentEnd) % 60,
            onConfirm = { hour, minute ->
                val time = "%02d:%02d".format(hour, minute)
                if (windowType == "discharge") {
                    dEndTime = time
                    dDuration = calcDuration(dStartTime, dEndTime)
                } else {
                    cEndTime = time
                }
                showEndPicker = false
            },
            onDismiss = { showEndPicker = false },
        )
    }

    if (showPeakPicker) {
        TimePickerDialog(
            title = "Peak Time",
            initialHour = parseTimeToMinutes(cPeakTime) / 60,
            initialMinute = parseTimeToMinutes(cPeakTime) % 60,
            onConfirm = { hour, minute ->
                cPeakTime = "%02d:%02d".format(hour, minute)
                showPeakPicker = false
            },
            onDismiss = { showPeakPicker = false },
        )
    }

    if (showDurationPicker) {
        DurationPickerDialog(
            initialHours = dDuration / 60,
            initialMinutes = dDuration % 60,
            onConfirm = { hours, minutes ->
                dDuration = hours * 60 + minutes
                dEndTime = calcEndTime(dStartTime, dDuration)
                showDurationPicker = false
            },
            onDismiss = { showDurationPicker = false },
        )
    }
}
