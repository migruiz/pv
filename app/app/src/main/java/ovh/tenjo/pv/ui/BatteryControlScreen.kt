package ovh.tenjo.pv.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
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
import kotlinx.coroutines.delay
import ovh.tenjo.pv.BatteryControlState
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.ui.theme.*

@Composable
fun BatteryControlScreen(
    viewModel: SolarViewModel,
    onBack: () -> Unit,
) {
    val state by viewModel.batteryControl.collectAsState()

    // Auto-clear result snackbar
    LaunchedEffect(state.applyResult) {
        if (state.applyResult != null) {
            delay(3000)
            viewModel.clearResult()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.surface)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp)
            .padding(top = 24.dp, bottom = 100.dp),
    ) {
        // -- Top Bar --
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back", tint = MaterialTheme.colorScheme.onSurface)
            }
            Text(
                "Battery Control",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.primary,
            )
        }

        Spacer(Modifier.height(20.dp))

        // -- Status Banner --
        StatusBanner(state)

        Spacer(Modifier.height(24.dp))

        // -- Forced Charge/Discharge Card --
        ForcedChargeCard(state, viewModel)

        Spacer(Modifier.height(24.dp))

        // -- Quick Actions --
        QuickActions(viewModel)

        // -- Result feedback --
        state.applyResult?.let { result ->
            Spacer(Modifier.height(16.dp))
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = if (result.startsWith("Error")) MaterialTheme.colorScheme.errorContainer
                else SolarGreenContainer.copy(alpha = 0.3f),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    result,
                    modifier = Modifier.padding(16.dp),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}

// ------------------------------------------------------------------
// Status Banner
// ------------------------------------------------------------------

@Composable
private fun StatusBanner(state: BatteryControlState) {
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = SurfaceContainerLow,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            Modifier.padding(20.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Battery icon
            Box(
                Modifier
                    .size(48.dp)
                    .background(PrimaryAccent.copy(alpha = 0.1f), CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Default.BatteryChargingFull,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(24.dp),
                )
            }

            Spacer(Modifier.width(16.dp))

            Column(Modifier.weight(1f)) {
                Text(
                    "%.0f%%".format(state.soc),
                    style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Bold),
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    "System Health: ${state.status}",
                    style = MaterialTheme.typography.bodySmall,
                    color = OnSurfaceVariant,
                )
            }

            Column(horizontalAlignment = Alignment.End) {
                Text(
                    "%.3f".format(state.currentPowerKw),
                    style = MaterialTheme.typography.headlineLarge.copy(fontWeight = FontWeight.ExtraBold),
                )
                Text(
                    "kW CURRENT FLOW",
                    style = MaterialTheme.typography.labelSmall,
                    color = OnSurfaceVariant,
                )
            }
        }
    }
}

// ------------------------------------------------------------------
// Forced Charge/Discharge Card
// ------------------------------------------------------------------

@Composable
private fun ForcedChargeCard(state: BatteryControlState, viewModel: SolarViewModel) {
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = SurfaceContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(20.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "Forced Charge / Discharge",
                    style = MaterialTheme.typography.titleLarge,
                )
                Icon(Icons.Default.Info, contentDescription = null, tint = OnSurfaceVariant, modifier = Modifier.size(20.dp))
            }

            Spacer(Modifier.height(20.dp))

            // -- Segmented buttons --
            SegmentedModeButtons(state.mode, viewModel::setMode)

            Spacer(Modifier.height(28.dp))

            // -- Power Slider --
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Bottom,
            ) {
                Text("POWER OUTPUT", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = PrimaryAccent.copy(alpha = 0.1f),
                    border = androidx.compose.foundation.BorderStroke(1.dp, PrimaryAccent.copy(alpha = 0.2f)),
                ) {
                    Text(
                        "%.1f kW".format(state.powerKw),
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Bold),
                        color = PrimaryAccent,
                    )
                }
            }

            Spacer(Modifier.height(8.dp))

            Slider(
                value = state.powerKw,
                onValueChange = { viewModel.setPowerKw(it) },
                valueRange = 0f..2.5f,
                steps = 24,
                colors = SliderDefaults.colors(
                    thumbColor = PrimaryAccent,
                    activeTrackColor = PrimaryAccent,
                    inactiveTrackColor = SurfaceContainerHighest,
                ),
                modifier = Modifier.fillMaxWidth(),
            )

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("0.0 kW", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                Text("2.5 kW", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
            }

            Spacer(Modifier.height(24.dp))

            // -- Setting Mode --
            Text("CONTROL MODE", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                RadioOption("Duration", state.settingMode == "duration") { viewModel.setSettingMode("duration") }
                RadioOption("Energy", state.settingMode == "energy") { viewModel.setSettingMode("energy") }
            }

            Spacer(Modifier.height(24.dp))

            // -- Duration input --
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("DURATION", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                Text("[0-1440]", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
            }
            Spacer(Modifier.height(8.dp))

            OutlinedTextField(
                value = state.durationMin.toString(),
                onValueChange = { viewModel.setDurationMin(it.toIntOrNull() ?: 0) },
                modifier = Modifier.fillMaxWidth(),
                suffix = { Text("min", color = OnSurfaceVariant) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
                shape = RoundedCornerShape(14.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    unfocusedContainerColor = SurfaceContainerHighest,
                    focusedContainerColor = SurfaceContainerHighest,
                    unfocusedBorderColor = Color.Transparent,
                    focusedBorderColor = PrimaryAccent.copy(alpha = 0.5f),
                    cursorColor = PrimaryAccent,
                ),
                textStyle = MaterialTheme.typography.titleLarge,
            )

            Spacer(Modifier.height(28.dp))

            // -- Apply Button --
            Button(
                onClick = { viewModel.applyForcedCharge() },
                modifier = Modifier.fillMaxWidth().height(52.dp),
                shape = RoundedCornerShape(50),
                enabled = !state.isApplying,
                colors = ButtonDefaults.buttonColors(
                    containerColor = PrimaryAccent,
                    contentColor = MaterialTheme.colorScheme.surface,
                ),
            ) {
                if (state.isApplying) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        color = MaterialTheme.colorScheme.surface,
                        strokeWidth = 2.dp,
                    )
                } else {
                    Text(
                        "Apply Settings",
                        style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.ExtraBold),
                    )
                }
            }
        }
    }
}

// ------------------------------------------------------------------
// Segmented Mode Buttons
// ------------------------------------------------------------------

@Composable
private fun SegmentedModeButtons(selected: String, onSelect: (String) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(SurfaceContainerHighest, RoundedCornerShape(50)),
        horizontalArrangement = Arrangement.SpaceEvenly,
    ) {
        listOf("stop" to "Stop", "charge" to "Charge", "discharge" to "Discharge").forEach { (key, label) ->
            val isSelected = selected == key
            val bgColor = if (isSelected) OutlineVariant.copy(alpha = 0.4f) else Color.Transparent
            val textColor = when {
                isSelected && key == "charge" -> PrimaryAccent
                isSelected && key == "discharge" -> EnergyOrange
                isSelected -> MaterialTheme.colorScheme.onSurface
                else -> OnSurfaceVariant
            }
            Box(
                modifier = Modifier
                    .weight(1f)
                    .padding(4.dp)
                    .background(bgColor, RoundedCornerShape(50))
                    .clickable { onSelect(key) }
                    .padding(vertical = 10.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    label,
                    style = MaterialTheme.typography.bodySmall.copy(
                        fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                    ),
                    color = textColor,
                )
            }
        }
    }
}

// ------------------------------------------------------------------
// Radio Option
// ------------------------------------------------------------------

@Composable
private fun RadioOption(label: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        modifier = Modifier.clickable(onClick = onClick),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(20.dp)
                .border(2.dp, if (selected) PrimaryAccent else OutlineVariant, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            if (selected) {
                Box(
                    Modifier
                        .size(10.dp)
                        .background(PrimaryAccent, CircleShape)
                )
            }
        }
        Spacer(Modifier.width(8.dp))
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium),
            color = if (selected) MaterialTheme.colorScheme.onSurface else OnSurfaceVariant,
        )
    }
}

// ------------------------------------------------------------------
// Quick Actions
// ------------------------------------------------------------------

@Composable
private fun QuickActions(viewModel: SolarViewModel) {
    Text("QUICK ACTIONS", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
    Spacer(Modifier.height(12.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        QuickChip(Icons.Default.Bolt, "Charge 30 min", PrimaryAccent) {
            viewModel.quickAction("charge", 30)
        }
        QuickChip(Icons.Default.Bolt, "Charge 1 hour", PrimaryAccent) {
            viewModel.quickAction("charge", 60)
        }
        QuickChip(Icons.Default.StopCircle, "Stop", EnergyOrange) {
            viewModel.quickAction("stop", 0)
        }
    }
}

@Composable
private fun QuickChip(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    color: Color,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(14.dp),
        color = SurfaceContainerHigh,
        border = androidx.compose.foundation.BorderStroke(1.dp, OutlineVariant.copy(alpha = 0.2f)),
    ) {
        Row(
            Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(icon, null, tint = color, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text(label, style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold))
        }
    }
}
