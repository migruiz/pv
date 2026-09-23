package ovh.tenjo.pv

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.ViewModelProvider
import com.google.firebase.messaging.FirebaseMessaging
import ovh.tenjo.pv.api.SolarApiClient
import ovh.tenjo.pv.ui.DashboardScreen
import ovh.tenjo.pv.ui.DischargeWindowScreen
import ovh.tenjo.pv.ui.theme.PVManagerTheme

private sealed interface Screen {
    data object Dashboard : Screen

    /** The window screen: an existing window, or a new one when id is null. */
    data class Window(val id: String?) : Screen
}

class MainActivity : ComponentActivity() {

    private val solarViewModel by lazy {
        ViewModelProvider(this)[SolarViewModel::class.java]
    }

    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { /* granted or not — FCM still works, just silently */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // API config injected from local.properties via BuildConfig
        SolarApiClient.baseUrl = BuildConfig.PV_API_URL
        SolarApiClient.apiKey = BuildConfig.PV_API_KEY

        // Request notification permission (Android 13+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        // Subscribe to auto_discharge topic — all devices get notifications
        FirebaseMessaging.getInstance().subscribeToTopic("auto_discharge")
            .addOnSuccessListener { Log.d("FCM", "Subscribed to auto_discharge topic") }

        setContent {
            PVManagerTheme {
                var screen by remember { mutableStateOf<Screen>(Screen.Dashboard) }
                val windows by solarViewModel.windows.collectAsState()

                // A lost "stopped" push would leave the discharging notification up for good. Only a
                // successful, fresh list can say nothing is discharging: never a cached one after a failure.
                LaunchedEffect(windows.fetchedAt) {
                    if (windows.fetchedAt > 0 && windows.windows.none { it.state.discharging }) {
                        AutoDischargeService.stopIfStale(this@MainActivity, windows.fetchedAt)
                    }
                }

                BackHandler(enabled = screen != Screen.Dashboard) {
                    screen = Screen.Dashboard
                }

                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    when (val current = screen) {
                        is Screen.Window -> DischargeWindowScreen(
                            windowId = current.id,
                            viewModel = solarViewModel,
                            onBack = { screen = Screen.Dashboard },
                        )
                        Screen.Dashboard -> DashboardScreen(
                            viewModel = solarViewModel,
                            modifier = Modifier.padding(innerPadding),
                            onWindowClick = {
                                solarViewModel.resetEditor()
                                screen = Screen.Window(it)
                            },
                            onCreateWindow = {
                                solarViewModel.resetEditor()
                                screen = Screen.Window(null)
                            },
                        )
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        solarViewModel.startAutoRefresh()
    }

    override fun onPause() {
        super.onPause()
        solarViewModel.stopAutoRefresh()
    }
}
