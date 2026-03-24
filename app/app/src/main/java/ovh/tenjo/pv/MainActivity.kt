package ovh.tenjo.pv

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.*
import ovh.tenjo.pv.api.SolarApiClient
import ovh.tenjo.pv.ui.BatteryControlScreen
import ovh.tenjo.pv.ui.DashboardScreen
import ovh.tenjo.pv.ui.theme.OnSurfaceVariant
import ovh.tenjo.pv.ui.theme.PVManagerTheme
import ovh.tenjo.pv.ui.theme.SurfaceDark

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // Configure API — change these for your network setup
        // Emulator: "http://10.0.2.2:8000/"
        // Real device on same WiFi: "http://<your-pc-ip>:8000/"
        SolarApiClient.baseUrl = "http://10.0.2.2:8000/"
        SolarApiClient.apiKey = "pCcnYvYPl5IwmWbCpKvU1D9SdQVzp7xWMXhU2YHf_vs"

        setContent {
            PVManagerTheme {
                SolarApp()
            }
        }
    }
}

@Composable
fun SolarApp(solarViewModel: SolarViewModel = viewModel()) {
    val navController = rememberNavController()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.surface,
        bottomBar = {
            BottomNavBar(
                currentRoute = currentRoute ?: "dashboard",
                onDashboard = {
                    navController.navigate("dashboard") {
                        popUpTo("dashboard") { inclusive = true }
                    }
                },
                onSettings = {
                    navController.navigate("battery_control") {
                        popUpTo("dashboard")
                    }
                },
            )
        },
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = "dashboard",
            modifier = Modifier.padding(innerPadding),
        ) {
            composable("dashboard") {
                DashboardScreen(
                    viewModel = solarViewModel,
                    onBatteryControlClick = {
                        navController.navigate("battery_control")
                    },
                )
            }
            composable("battery_control") {
                BatteryControlScreen(
                    viewModel = solarViewModel,
                    onBack = { navController.popBackStack() },
                )
            }
        }
    }
}

@Composable
private fun BottomNavBar(
    currentRoute: String,
    onDashboard: () -> Unit,
    onSettings: () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp),
        color = SurfaceDark.copy(alpha = 0.85f),
        shadowElevation = 16.dp,
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(horizontal = 32.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.SpaceAround,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BottomNavItem(
                icon = Icons.Default.Dashboard,
                label = "DASHBOARD",
                selected = currentRoute == "dashboard",
                onClick = onDashboard,
            )
            BottomNavItem(
                icon = Icons.Outlined.Settings,
                label = "SETTINGS",
                selected = currentRoute == "battery_control",
                onClick = onSettings,
            )
        }
    }
}

@Composable
private fun BottomNavItem(
    icon: ImageVector,
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val color = if (selected) MaterialTheme.colorScheme.primary else OnSurfaceVariant

    Surface(
        onClick = onClick,
        color = if (selected) MaterialTheme.colorScheme.primary.copy(alpha = 0.1f) else Color.Transparent,
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(
            Modifier.padding(horizontal = 24.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(icon, contentDescription = label, tint = color, modifier = Modifier.size(24.dp))
            Spacer(Modifier.height(4.dp))
            Text(
                label,
                style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold),
                color = color,
            )
        }
    }
}
