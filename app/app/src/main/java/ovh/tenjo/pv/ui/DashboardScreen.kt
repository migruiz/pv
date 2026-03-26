package ovh.tenjo.pv.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.BiasAlignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ovh.tenjo.pv.AutoDischargeState
import ovh.tenjo.pv.DashboardState
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(viewModel: SolarViewModel, modifier: Modifier = Modifier) {
    val state by viewModel.dashboard.collectAsState()
    val adState by viewModel.autoDischarge.collectAsState()

    PullToRefreshBox(
        isRefreshing = state.isRefreshing,
        onRefresh = { viewModel.pullToRefresh() },
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.surface),
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(top = 24.dp, bottom = 16.dp),
        ) {
            if (state.isLoading) {
                Box(Modifier.fillMaxWidth().height(300.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                }
            } else if (state.error != null) {
                ErrorCard(state.error!!) { viewModel.refreshDashboard() }
            } else {
                // -- Energy Flow --
                EnergyFlowSection(state)

                Spacer(Modifier.height(32.dp))

                // -- Today Stats --
                StatsRow(state)

                Spacer(Modifier.weight(1f))

                // -- Auto-discharge --
                AutoDischargeCard(adState, viewModel)
            }
        }
    }
}

// ------------------------------------------------------------------
// Energy Flow Diamond
// ------------------------------------------------------------------

@Composable
private fun EnergyFlowSection(state: DashboardState) {
    val infiniteTransition = rememberInfiniteTransition(label = "flow")

    // Elapsed animation time — increases monotonically, no global wrap
    var animTimeMs by remember { mutableFloatStateOf(0f) }
    LaunchedEffect(Unit) {
        val startNanos = withInfiniteAnimationFrameNanos { it }
        while (true) {
            withInfiniteAnimationFrameNanos { now -> animTimeMs = (now - startNanos) / 1_000_000f }
        }
    }

    // Speed scales linearly with power: 3 kW → 1×, 6 kW → 2×, 1.5 kW → 0.5×
    // Clamped to [0.35, 3.5] → duration range ~1000ms–10000ms
    fun speedMult(kw: Double): Float = (kw / 3.0).toFloat().coerceIn(0.033f, 3.5f)
    fun particleProg(mult: Float, idx: Int): Float {
        val period = 3500f / mult
        return ((animTimeMs % period) / period + idx * 0.25f) % 1.0f
    }

    // Glow pulse
    val glowAlpha by infiniteTransition.animateFloat(
        0.15f, 0.45f,
        infiniteRepeatable(tween(2000, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "glow",
    )

    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f)
                .padding(horizontal = 16.dp),
            contentAlignment = Alignment.Center,
        ) {
            val primaryColor = MaterialTheme.colorScheme.primary
            val secondaryColor = MaterialTheme.colorScheme.secondary
            val tertiaryColor = GridBlue
            val homeColor = Color.White

            Canvas(Modifier.fillMaxSize()) {
                val cx = size.width / 2
                val cy = size.height / 2
                val topY = size.height * 0.15f
                val bottomY = size.height * 0.85f
                val leftX = size.width * 0.15f
                val rightX = size.width * 0.85f

                val dotR = 4.dp.toPx()
                val glowR = 12.dp.toPx()
                val lineWidth = 2.dp.toPx()

                // Helper to draw a glowing line between two points
                fun drawFlowLine(from: Offset, to: Offset, color: Color, active: Boolean) {
                    // Faint base line always visible
                    drawLine(color.copy(alpha = 0.12f), from, to, strokeWidth = lineWidth, cap = StrokeCap.Round)
                    if (active) {
                        // Brighter active line
                        drawLine(color.copy(alpha = 0.35f), from, to, strokeWidth = lineWidth, cap = StrokeCap.Round)
                    }
                }

                // Helper to draw a triangle pointing in the flow direction
                fun drawTriangle(pos: Offset, dirX: Float, dirY: Float, size: Float, color: Color) {
                    val len = kotlin.math.sqrt(dirX * dirX + dirY * dirY)
                    if (len == 0f) return
                    val dx = dirX / len
                    val dy = dirY / len
                    // Perpendicular
                    val px = -dy
                    val py = dx
                    val half = size * 0.55f
                    val path = Path().apply {
                        moveTo(pos.x + dx * size, pos.y + dy * size)       // Tip
                        lineTo(pos.x - dx * half + px * half, pos.y - dy * half + py * half)
                        lineTo(pos.x - dx * half - px * half, pos.y - dy * half - py * half)
                        close()
                    }
                    drawPath(path, color)
                }

                // Helper to draw a stream of 3 directional triangle particles along a path
                fun drawParticleStream(
                    from: Offset, to: Offset, color: Color,
                    prog1: Float, prog2: Float, prog3: Float, prog4: Float,
                ) {
                    val dirX = to.x - from.x
                    val dirY = to.y - from.y
                    listOf(prog1, prog2, prog3, prog4).forEach { t ->
                        // Fade in over first 15%, fade out over last 15%
                        val fade = when {
                            t < 0.15f -> t / 0.15f
                            t > 0.85f -> (1f - t) / 0.15f
                            else -> 1f
                        }
                        val pos = Offset(
                            from.x + dirX * t,
                            from.y + dirY * t,
                        )
                        // Outer glow
                        drawCircle(color.copy(alpha = glowAlpha * 0.4f * fade), glowR, pos)
                        // Triangle pointing in flow direction
                        drawTriangle(pos, dirX, dirY, dotR * 1.4f, color.copy(alpha = fade))
                        // Bright center dot
                        drawTriangle(pos, dirX, dirY, dotR * 0.6f, Color.White.copy(alpha = 0.5f * fade))
                    }
                }

                val center = Offset(cx, cy)
                val topPt = Offset(cx, topY)
                val bottomPt = Offset(cx, bottomY)
                val leftPt = Offset(leftX, cy)
                val rightPt = Offset(rightX, cy)

                val pvActive = state.pvPowerKw > 0.01
                val battActive = state.batteryPowerKw > 0.005
                val homeActive = state.homePowerKw > 0.01
                val gridActive = state.gridPowerKw > 0.01

                // Draw lines
                drawFlowLine(topPt, center, primaryColor, pvActive)
                drawFlowLine(leftPt, center, secondaryColor, battActive)
                drawFlowLine(center, rightPt, homeColor, homeActive)
                drawFlowLine(center, bottomPt, tertiaryColor, gridActive)

                // PV particles (top → center)
                if (pvActive) {
                    val m = speedMult(state.pvPowerKw)
                    drawParticleStream(topPt, center, primaryColor,
                        particleProg(m, 0), particleProg(m, 1), particleProg(m, 2), particleProg(m, 3))
                }

                // Battery particles
                if (battActive) {
                    val m = speedMult(state.batteryPowerKw)
                    if (state.batteryCharging) {
                        drawParticleStream(center, leftPt, secondaryColor,
                            particleProg(m, 0), particleProg(m, 1), particleProg(m, 2), particleProg(m, 3))
                    } else {
                        drawParticleStream(leftPt, center, secondaryColor,
                            particleProg(m, 0), particleProg(m, 1), particleProg(m, 2), particleProg(m, 3))
                    }
                }

                // Home particles (center → right)
                if (homeActive) {
                    val m = speedMult(state.homePowerKw)
                    drawParticleStream(center, rightPt, homeColor,
                        particleProg(m, 0), particleProg(m, 1), particleProg(m, 2), particleProg(m, 3))
                }

                // Grid particles
                if (gridActive) {
                    val m = speedMult(state.gridPowerKw)
                    if (state.gridImporting) {
                        drawParticleStream(bottomPt, center, tertiaryColor,
                            particleProg(m, 0), particleProg(m, 1), particleProg(m, 2), particleProg(m, 3))
                    } else {
                        drawParticleStream(center, bottomPt, tertiaryColor,
                            particleProg(m, 0), particleProg(m, 1), particleProg(m, 2), particleProg(m, 3))
                    }
                }
            }

            // PV — Top
            EnergyNode(
                modifier = Modifier.align(Alignment.TopCenter).padding(top = 4.dp),
                icon = Icons.Default.WbSunny,
                value = "%.2f kW".format(state.pvPowerKw),
                label = "SOLAR PV",
                color = MaterialTheme.colorScheme.primary,
                valueOnTop = true,
            )
            // Battery — Left (show SOC + power + direction)
            val battDir = if (state.batteryCharging) "▲ charging" else "▼ discharging"
            EnergyNode(
                modifier = Modifier.align(Alignment.CenterStart).padding(start = 4.dp),
                icon = Icons.Default.BatteryChargingFull,
                value = "%.0f%%".format(state.batterySoc),
                subtitle = "%.3f kW".format(state.batteryPowerKw),
                label = if (state.batteryPowerKw > 0.005) battDir else "BATTERY",
                color = MaterialTheme.colorScheme.secondary,
            )
            // Home — Right
            EnergyNode(
                modifier = Modifier.align(Alignment.CenterEnd).padding(end = 4.dp),
                icon = Icons.Default.Home,
                value = "%.2f kW".format(state.homePowerKw),
                label = "HOME",
                color = MaterialTheme.colorScheme.onSurface,
            )
            // Grid — Bottom
            val gridDir = if (state.gridImporting) "↓ import" else "↑ export"
            EnergyNode(
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 4.dp),
                icon = Icons.Default.Bolt,
                value = "%.2f kW".format(state.gridPowerKw),
                label = if (state.gridPowerKw > 0.01) gridDir else "GRID",
                color = GridBlue,
            )
        }
    }
}

@Composable
private fun EnergyNode(
    modifier: Modifier = Modifier,
    icon: ImageVector,
    value: String,
    subtitle: String? = null,
    label: String,
    color: Color,
    valueOnTop: Boolean = false,
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        if (valueOnTop) {
            Text(
                value,
                style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.ExtraBold),
                color = color,
            )
            Spacer(Modifier.height(6.dp))
        }
        Box(
            modifier = Modifier
                .size(56.dp)
                .background(SurfaceContainerHigh, RoundedCornerShape(16.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(icon, contentDescription = label, tint = color, modifier = Modifier.size(30.dp))
        }
        if (!valueOnTop) {
            Spacer(Modifier.height(6.dp))
            Text(
                value,
                style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.ExtraBold),
                color = color,
            )
        }
        if (subtitle != null) {
            Text(
                subtitle,
                style = MaterialTheme.typography.bodySmall,
                color = color.copy(alpha = 0.7f),
            )
        }
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
// Auto-discharge card
// ------------------------------------------------------------------

@Composable
private fun AutoDischargeCard(state: AutoDischargeState, viewModel: SolarViewModel) {
    // Auto-clear message
    LaunchedEffect(state.message) {
        if (state.message != null) {
            kotlinx.coroutines.delay(3000)
            viewModel.clearAutoDischargeMessage()
        }
    }

    Surface(
        shape = RoundedCornerShape(16.dp),
        color = SurfaceContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Default.NightsStay,
                        contentDescription = null,
                        tint = if (state.active) EnergyOrange else OnSurfaceVariant,
                        modifier = Modifier.size(20.dp),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "Auto-Discharge",
                        style = MaterialTheme.typography.titleMedium,
                    )
                }
                if (state.active) {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = EnergyOrange.copy(alpha = 0.15f),
                    ) {
                        Text(
                            "ACTIVE",
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                            style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                            color = EnergyOrange,
                        )
                    }
                }
            }

            if (state.active) {
                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column {
                        Text("POWER", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                        Text(
                            "%.2f kW".format(state.dischargePowerKw ?: 0.0),
                            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                        )
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("REMAINING", style = MaterialTheme.typography.labelSmall, color = OnSurfaceVariant)
                        val mins = state.minutesRemaining ?: 0.0
                        val hours = (mins / 60).toInt()
                        val m = (mins % 60).toInt()
                        Text(
                            "${hours}h ${m}m",
                            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                        )
                    }
                }
            }

            Spacer(Modifier.height(12.dp))

            Button(
                onClick = {
                    if (state.active) viewModel.stopAutoDischarge()
                    else viewModel.startAutoDischarge()
                },
                modifier = Modifier.fillMaxWidth().height(44.dp),
                shape = RoundedCornerShape(50),
                enabled = !state.isStarting && !state.isStopping,
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (state.active) MaterialTheme.colorScheme.error else EnergyOrange,
                    contentColor = Color.White,
                ),
            ) {
                if (state.isStarting || state.isStopping) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        color = Color.White,
                        strokeWidth = 2.dp,
                    )
                } else {
                    Icon(
                        if (state.active) Icons.Default.StopCircle else Icons.Default.PlayArrow,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        if (state.active) "Stop Discharge" else "Start Auto-Discharge",
                        style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.Bold),
                    )
                }
            }

            state.message?.let { msg ->
                Spacer(Modifier.height(8.dp))
                Text(
                    msg,
                    style = MaterialTheme.typography.bodySmall,
                    color = if (msg.startsWith("Error")) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
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
