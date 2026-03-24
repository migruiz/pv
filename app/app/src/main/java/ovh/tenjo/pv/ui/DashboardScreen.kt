package ovh.tenjo.pv.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ovh.tenjo.pv.DashboardState
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.ui.theme.*

@Composable
fun DashboardScreen(
    viewModel: SolarViewModel,
    onBatteryControlClick: () -> Unit,
) {
    val state by viewModel.dashboard.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.surface)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp)
            .padding(top = 24.dp, bottom = 100.dp),
    ) {
        // -- Top Bar --
        TopBar()

        Spacer(Modifier.height(24.dp))

        if (state.isLoading) {
            Box(Modifier.fillMaxWidth().height(300.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
            }
        } else if (state.error != null) {
            ErrorCard(state.error!!) { viewModel.refreshDashboard() }
        } else {
            // -- Energy Flow --
            EnergyFlowSection(state)

            Spacer(Modifier.height(28.dp))

            // -- Today Stats --
            StatsRow(state)

            Spacer(Modifier.height(20.dp))

            // -- Battery Card --
            BatteryCard(state, onBatteryControlClick)
        }
    }
}

// ------------------------------------------------------------------
// Top Bar
// ------------------------------------------------------------------

@Composable
private fun TopBar() {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                Icons.Default.EnergySavingsLeaf,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(28.dp),
            )
            Spacer(Modifier.width(10.dp))
            Text(
                "Solar Pulse",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
        Icon(
            Icons.Outlined.Settings,
            contentDescription = "Settings",
            tint = OnSurfaceVariant,
            modifier = Modifier.size(24.dp),
        )
    }
}

// ------------------------------------------------------------------
// Energy Flow Diamond
// ------------------------------------------------------------------

@Composable
private fun EnergyFlowSection(state: DashboardState) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            "LIVE ENERGY SYSTEM",
            style = MaterialTheme.typography.labelSmall,
            color = OnSurfaceVariant,
        )
        Spacer(Modifier.height(16.dp))

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f)
                .padding(horizontal = 16.dp),
            contentAlignment = Alignment.Center,
        ) {
            // Dashed cross lines
            val lineColor = OutlineVariant
            Canvas(Modifier.fillMaxSize()) {
                val cx = size.width / 2
                val cy = size.height / 2
                val dash = PathEffect.dashPathEffect(floatArrayOf(6f, 6f))
                drawLine(lineColor, Offset(cx, size.height * 0.12f), Offset(cx, size.height * 0.88f), strokeWidth = 1.5f, pathEffect = dash)
                drawLine(lineColor, Offset(size.width * 0.12f, cy), Offset(size.width * 0.88f, cy), strokeWidth = 1.5f, pathEffect = dash)
            }

            // PV — Top
            EnergyNode(
                modifier = Modifier.align(Alignment.TopCenter).padding(top = 4.dp),
                icon = Icons.Default.WbSunny,
                value = "%.2f kW".format(state.pvPowerKw),
                label = "SOLAR PV",
                color = MaterialTheme.colorScheme.primary,
            )
            // Battery — Left
            EnergyNode(
                modifier = Modifier.align(Alignment.CenterStart).padding(start = 4.dp),
                icon = Icons.Default.BatteryChargingFull,
                value = "%.0f%%".format(state.batterySoc),
                label = "BATTERY",
                color = MaterialTheme.colorScheme.secondary,
            )
            // Grid — Right
            EnergyNode(
                modifier = Modifier.align(Alignment.CenterEnd).padding(end = 4.dp),
                icon = Icons.Default.Bolt,
                value = "%.2f kW".format(state.gridPowerKw),
                label = "GRID",
                color = GridBlue,
            )
            // Home — Bottom
            EnergyNode(
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 4.dp),
                icon = Icons.Default.Home,
                value = "%.2f kW".format(state.homePowerKw),
                label = "HOME",
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
    }
}

@Composable
private fun EnergyNode(
    modifier: Modifier = Modifier,
    icon: ImageVector,
    value: String,
    label: String,
    color: Color,
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            modifier = Modifier
                .size(56.dp)
                .background(SurfaceContainerHigh, RoundedCornerShape(16.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(icon, contentDescription = label, tint = color, modifier = Modifier.size(30.dp))
        }
        Spacer(Modifier.height(6.dp))
        Text(
            value,
            style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.ExtraBold),
            color = color,
        )
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = OnSurfaceVariant,
        )
    }
}

// ------------------------------------------------------------------
// Stats Row
// ------------------------------------------------------------------

@Composable
private fun StatsRow(state: DashboardState) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        StatCard(Modifier.weight(1f), Icons.Default.WbSunny, "%.1f".format(state.energyTodayKwh), "kWh", "GENERATED", MaterialTheme.colorScheme.primary)
        StatCard(Modifier.weight(1f), Icons.Default.Power, "%.1f".format(state.consumedTodayKwh), "kWh", "CONSUMED", GridBlue)
        StatCard(Modifier.weight(1f), Icons.Default.TrendingUp, "%.1f".format(state.totalEnergyKwh), "kWh", "YIELD", MaterialTheme.colorScheme.secondary)
    }
}

@Composable
private fun StatCard(
    modifier: Modifier,
    icon: ImageVector,
    value: String,
    unit: String,
    label: String,
    color: Color,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        color = SurfaceContainerLow,
    ) {
        Column(
            Modifier.padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(icon, contentDescription = null, tint = color.copy(alpha = 0.8f), modifier = Modifier.size(20.dp))
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.Bottom) {
                Text(value, style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.width(2.dp))
                Text(unit, style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
            }
            Spacer(Modifier.height(4.dp))
            Text(label, style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
        }
    }
}

// ------------------------------------------------------------------
// Battery Status Card
// ------------------------------------------------------------------

@Composable
private fun BatteryCard(state: DashboardState, onControlClick: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(24.dp),
        color = SurfaceContainer,
        shadowElevation = 8.dp,
    ) {
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                // Circular gauge
                Box(modifier = Modifier.size(120.dp), contentAlignment = Alignment.Center) {
                    val soc = (state.batterySoc / 100f).toFloat()
                    val gaugeColor = MaterialTheme.colorScheme.secondary
                    val trackColor = SurfaceContainerHigh
                    Canvas(Modifier.fillMaxSize()) {
                        drawArc(trackColor, 0f, 360f, false, style = Stroke(width = 10.dp.toPx(), cap = StrokeCap.Round))
                        drawArc(gaugeColor, -90f, 360f * soc, false, style = Stroke(width = 10.dp.toPx(), cap = StrokeCap.Round))
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            "%.0f%%".format(state.batterySoc),
                            style = MaterialTheme.typography.headlineLarge.copy(fontWeight = FontWeight.ExtraBold),
                        )
                        Text("SOC", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                    }
                }

                Spacer(Modifier.width(20.dp))

                // Stats
                Column(Modifier.weight(1f)) {
                    // Status
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .padding(bottom = 8.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("Status", style = MaterialTheme.typography.bodySmall, color = OnSurfaceVariant)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                Modifier
                                    .size(8.dp)
                                    .background(MaterialTheme.colorScheme.primary, CircleShape)
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(state.batteryStatus, style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold), color = MaterialTheme.colorScheme.primary)
                        }
                    }
                    HorizontalDivider(color = OutlineVariant.copy(alpha = 0.3f))
                    Spacer(Modifier.height(10.dp))

                    // Grid of stats
                    Row(Modifier.fillMaxWidth()) {
                        Column(Modifier.weight(1f)) {
                            StatLabel("CAPACITY")
                            StatValue("%.1f kWh".format(state.batteryCapacity))
                            Spacer(Modifier.height(10.dp))
                            StatLabel("CHARGED")
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.North, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(12.dp))
                                StatValue("%.2f kWh".format(state.chargedTodayKwh))
                            }
                        }
                        Column(Modifier.weight(1f)) {
                            StatLabel("CURRENT")
                            StatValue("%.3f kW".format(state.batteryPowerKw))
                            Spacer(Modifier.height(10.dp))
                            StatLabel("DISCHARGED")
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.South, null, tint = MaterialTheme.colorScheme.secondary, modifier = Modifier.size(12.dp))
                                StatValue("%.2f kWh".format(state.dischargedTodayKwh))
                            }
                        }
                    }
                }
            }

            Spacer(Modifier.height(20.dp))

            // Battery Control button
            Button(
                onClick = onControlClick,
                modifier = Modifier.fillMaxWidth().height(52.dp),
                shape = RoundedCornerShape(50),
                colors = ButtonDefaults.buttonColors(
                    containerColor = SolarGreenContainer,
                    contentColor = Color.White,
                ),
            ) {
                Icon(Icons.Default.Tune, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Battery Control", style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}

@Composable
private fun StatLabel(text: String) {
    Text(text, style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
}

@Composable
private fun StatValue(text: String) {
    Text(text, style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Bold))
}

// ------------------------------------------------------------------
// Error card
// ------------------------------------------------------------------

@Composable
private fun ErrorCard(error: String, onRetry: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.errorContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(Icons.Default.CloudOff, contentDescription = null, tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(40.dp))
            Spacer(Modifier.height(12.dp))
            Text(error, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface)
            Spacer(Modifier.height(16.dp))
            OutlinedButton(onClick = onRetry) { Text("Retry") }
        }
    }
}
