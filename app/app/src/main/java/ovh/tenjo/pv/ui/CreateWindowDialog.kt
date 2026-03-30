package ovh.tenjo.pv.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.api.DischargeWindowCreate
import ovh.tenjo.pv.ui.theme.EnergyOrange

@Composable
fun CreateWindowDialog(
    viewModel: SolarViewModel,
    onDismiss: () -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var startTime by remember { mutableStateOf("22:00") }
    var endTime by remember { mutableStateOf("02:00") }
    var durationMinutes by remember { mutableIntStateOf(240) }
    var targetSoc by remember { mutableFloatStateOf(0f) }
    var notify by remember { mutableStateOf(true) }

    var showStartPicker by remember { mutableStateOf(false) }
    var showEndPicker by remember { mutableStateOf(false) }
    var showDurationPicker by remember { mutableStateOf(false) }

    val detailState by viewModel.windowDetail.collectAsState()

    LaunchedEffect(detailState.message) {
        if (detailState.message == "Window created") {
            onDismiss()
        }
    }

    val dh = durationMinutes / 60
    val dm = durationMinutes % 60

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New Discharge Window") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("e.g. Morning Discharge") },
                )

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    ReadOnlyTimeField("Start", startTime, { showStartPicker = true }, Modifier.weight(1f))
                    ReadOnlyTimeField("End", endTime, { showEndPicker = true }, Modifier.weight(1f))
                }

                ReadOnlyTimeField(
                    "Duration",
                    "${dh}h ${dm}m ($durationMinutes min)",
                    { showDurationPicker = true },
                    Modifier.fillMaxWidth(),
                )

                Column {
                    Text("Target SOC: ${targetSoc.toInt()}%", style = MaterialTheme.typography.bodyMedium)
                    Slider(
                        value = targetSoc,
                        onValueChange = { targetSoc = it },
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
                        checked = notify,
                        onCheckedChange = { notify = it },
                        colors = SwitchDefaults.colors(checkedTrackColor = EnergyOrange),
                    )
                }

                detailState.message?.let { msg ->
                    if (msg.startsWith("Error")) {
                        Text(msg, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    viewModel.createWindow(
                        DischargeWindowCreate(
                            name = name,
                            startTime = startTime,
                            durationMinutes = durationMinutes,
                            targetSoc = targetSoc.toDouble(),
                            notify = notify,
                        ),
                    )
                },
                enabled = name.isNotBlank() && durationMinutes > 0 && !detailState.isSaving,
                shape = RoundedCornerShape(50),
                colors = ButtonDefaults.buttonColors(containerColor = EnergyOrange),
            ) {
                if (detailState.isSaving) {
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

    if (showStartPicker) {
        TimePickerDialog(
            title = "Start Time",
            initialHour = parseTimeToMinutes(startTime) / 60,
            initialMinute = parseTimeToMinutes(startTime) % 60,
            onConfirm = { hour, minute ->
                startTime = "%02d:%02d".format(hour, minute)
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
                endTime = calcEndTime(startTime, durationMinutes)
                showDurationPicker = false
            },
            onDismiss = { showDurationPicker = false },
        )
    }
}

