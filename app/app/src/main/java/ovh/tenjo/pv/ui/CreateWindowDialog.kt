package ovh.tenjo.pv.ui

import androidx.compose.foundation.clickable
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
import ovh.tenjo.pv.ui.theme.OnSurfaceVariant

@OptIn(ExperimentalMaterial3Api::class)
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

    // Close dialog after successful creation
    LaunchedEffect(detailState.message) {
        if (detailState.message == "Window created") {
            onDismiss()
        }
    }

    // Helper functions (same logic as detail screen)
    fun parseMinutes(time: String): Int {
        val parts = time.split(":")
        if (parts.size != 2) return 0
        return (parts[0].toIntOrNull() ?: 0) * 60 + (parts[1].toIntOrNull() ?: 0)
    }
    fun minutesToStr(m: Int): String {
        val total = ((m % 1440) + 1440) % 1440
        return "%02d:%02d".format(total / 60, total % 60)
    }

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

                // Start / End / Duration — tappable fields
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = startTime,
                        onValueChange = {},
                        label = { Text("Start") },
                        readOnly = true,
                        singleLine = true,
                        modifier = Modifier.weight(1f).clickable { showStartPicker = true },
                        enabled = false,
                        colors = OutlinedTextFieldDefaults.colors(
                            disabledTextColor = MaterialTheme.colorScheme.onSurface,
                            disabledBorderColor = MaterialTheme.colorScheme.outline,
                            disabledLabelColor = MaterialTheme.colorScheme.onSurfaceVariant,
                        ),
                    )
                    OutlinedTextField(
                        value = endTime,
                        onValueChange = {},
                        label = { Text("End") },
                        readOnly = true,
                        singleLine = true,
                        modifier = Modifier.weight(1f).clickable { showEndPicker = true },
                        enabled = false,
                        colors = OutlinedTextFieldDefaults.colors(
                            disabledTextColor = MaterialTheme.colorScheme.onSurface,
                            disabledBorderColor = MaterialTheme.colorScheme.outline,
                            disabledLabelColor = MaterialTheme.colorScheme.onSurfaceVariant,
                        ),
                    )
                }

                // Duration display — tappable
                val dh = durationMinutes / 60
                val dm = durationMinutes % 60
                OutlinedTextField(
                    value = "${dh}h ${dm}m ($durationMinutes min)",
                    onValueChange = {},
                    label = { Text("Duration") },
                    readOnly = true,
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().clickable { showDurationPicker = true },
                    enabled = false,
                    colors = OutlinedTextFieldDefaults.colors(
                        disabledTextColor = MaterialTheme.colorScheme.onSurface,
                        disabledBorderColor = MaterialTheme.colorScheme.outline,
                        disabledLabelColor = MaterialTheme.colorScheme.onSurfaceVariant,
                    ),
                )

                Column {
                    Text(
                        "Target SOC: ${targetSoc.toInt()}%",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Slider(
                        value = targetSoc,
                        onValueChange = { targetSoc = it },
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
                        onCheckedChange = { notify = it },
                        colors = SwitchDefaults.colors(checkedTrackColor = EnergyOrange),
                    )
                }

                detailState.message?.let { msg ->
                    if (msg.startsWith("Error")) {
                        Text(
                            msg,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                        )
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
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        },
    )

    // -- Time Picker Dialogs --

    if (showStartPicker) {
        val startState = rememberTimePickerState(
            initialHour = parseMinutes(startTime) / 60,
            initialMinute = parseMinutes(startTime) % 60,
            is24Hour = true,
        )
        AlertDialog(
            onDismissRequest = { showStartPicker = false },
            title = { Text("Start Time") },
            text = {
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    TimePicker(state = startState)
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        startTime = "%02d:%02d".format(startState.hour, startState.minute)
                        endTime = minutesToStr(parseMinutes(startTime) + durationMinutes)
                        showStartPicker = false
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = EnergyOrange),
                ) { Text("OK", fontWeight = FontWeight.Bold) }
            },
            dismissButton = { TextButton(onClick = { showStartPicker = false }) { Text("Cancel") } },
        )
    }

    if (showEndPicker) {
        val endState = rememberTimePickerState(
            initialHour = parseMinutes(endTime) / 60,
            initialMinute = parseMinutes(endTime) % 60,
            is24Hour = true,
        )
        AlertDialog(
            onDismissRequest = { showEndPicker = false },
            title = { Text("End Time") },
            text = {
                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    TimePicker(state = endState)
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        endTime = "%02d:%02d".format(endState.hour, endState.minute)
                        val s = parseMinutes(startTime)
                        val e = parseMinutes(endTime)
                        durationMinutes = ((e - s) + 1440) % 1440
                        showEndPicker = false
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = EnergyOrange),
                ) { Text("OK", fontWeight = FontWeight.Bold) }
            },
            dismissButton = { TextButton(onClick = { showEndPicker = false }) { Text("Cancel") } },
        )
    }

    if (showDurationPicker) {
        var dh by remember { mutableIntStateOf(durationMinutes / 60) }
        var dm by remember { mutableIntStateOf(durationMinutes % 60) }
        AlertDialog(
            onDismissRequest = { showDurationPicker = false },
            title = { Text("Duration") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Column {
                        Text("Hours: $dh", style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold))
                        Slider(
                            value = dh.toFloat(), onValueChange = { dh = it.toInt() },
                            valueRange = 0f..23f, steps = 22,
                            colors = SliderDefaults.colors(thumbColor = EnergyOrange, activeTrackColor = EnergyOrange),
                        )
                    }
                    Column {
                        Text("Minutes: $dm", style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold))
                        Slider(
                            value = dm.toFloat(), onValueChange = { dm = it.toInt() },
                            valueRange = 0f..55f, steps = 10,
                            colors = SliderDefaults.colors(thumbColor = EnergyOrange, activeTrackColor = EnergyOrange),
                        )
                    }
                    Text("Total: ${dh}h ${dm}m (${dh * 60 + dm} min)", style = MaterialTheme.typography.bodySmall, color = OnSurfaceVariant)
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        durationMinutes = dh * 60 + dm
                        endTime = minutesToStr(parseMinutes(startTime) + durationMinutes)
                        showDurationPicker = false
                    },
                    enabled = dh > 0 || dm > 0,
                    colors = ButtonDefaults.buttonColors(containerColor = EnergyOrange),
                ) { Text("OK", fontWeight = FontWeight.Bold) }
            },
            dismissButton = { TextButton(onClick = { showDurationPicker = false }) { Text("Cancel") } },
        )
    }
}
