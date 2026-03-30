package ovh.tenjo.pv.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
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
    var startTime by remember { mutableStateOf("") }
    var durationMinutes by remember { mutableStateOf("") }
    var targetSoc by remember { mutableFloatStateOf(0f) }
    var notify by remember { mutableStateOf(true) }

    val detailState by viewModel.windowDetail.collectAsState()

    // Close dialog after successful creation
    LaunchedEffect(detailState.message) {
        if (detailState.message == "Window created") {
            onDismiss()
        }
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

                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedTextField(
                        value = startTime,
                        onValueChange = { startTime = it },
                        label = { Text("Start") },
                        singleLine = true,
                        modifier = Modifier.weight(1f),
                        placeholder = { Text("HH:MM") },
                    )
                    OutlinedTextField(
                        value = durationMinutes,
                        onValueChange = { if (it.all { c -> c.isDigit() }) durationMinutes = it },
                        label = { Text("Duration") },
                        singleLine = true,
                        modifier = Modifier.weight(1f),
                        placeholder = { Text("min") },
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
                    val dur = durationMinutes.toIntOrNull() ?: return@Button
                    viewModel.createWindow(
                        DischargeWindowCreate(
                            name = name,
                            startTime = startTime,
                            durationMinutes = dur,
                            targetSoc = targetSoc.toDouble(),
                            notify = notify,
                        ),
                    )
                },
                enabled = name.isNotBlank() && startTime.matches(Regex("\\d{2}:\\d{2}")) &&
                    durationMinutes.toIntOrNull() != null && !detailState.isSaving,
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
}
