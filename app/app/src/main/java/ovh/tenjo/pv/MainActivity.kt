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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.firebase.messaging.FirebaseMessaging
import ovh.tenjo.pv.api.SolarApiClient
import ovh.tenjo.pv.ui.ChargeWindowDetailScreen
import ovh.tenjo.pv.ui.CreateWindowDialog
import ovh.tenjo.pv.ui.DashboardScreen
import ovh.tenjo.pv.ui.DischargeWindowDetailScreen
import ovh.tenjo.pv.ui.theme.PVManagerTheme

class MainActivity : ComponentActivity() {

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
                val solarViewModel: SolarViewModel = viewModel()
                var selectedDischargeWindowId by remember { mutableStateOf<String?>(null) }
                var selectedChargeWindowId by remember { mutableStateOf<String?>(null) }
                var showCreateDialog by remember { mutableStateOf(false) }

                BackHandler(enabled = selectedChargeWindowId != null || selectedDischargeWindowId != null) {
                    if (selectedChargeWindowId != null) selectedChargeWindowId = null
                    else selectedDischargeWindowId = null
                }

                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    if (selectedChargeWindowId != null) {
                        ChargeWindowDetailScreen(
                            windowId = selectedChargeWindowId!!,
                            viewModel = solarViewModel,
                            onBack = { selectedChargeWindowId = null },
                        )
                    } else if (selectedDischargeWindowId != null) {
                        DischargeWindowDetailScreen(
                            windowId = selectedDischargeWindowId!!,
                            viewModel = solarViewModel,
                            onBack = { selectedDischargeWindowId = null },
                        )
                    } else {
                        DashboardScreen(
                            viewModel = solarViewModel,
                            modifier = Modifier.padding(innerPadding),
                            onDischargeWindowClick = {
                                solarViewModel.clearDetailMessage()
                                selectedDischargeWindowId = it
                            },
                            onChargeWindowClick = {
                                solarViewModel.clearChargeWindowDetailMessage()
                                selectedChargeWindowId = it
                            },
                            onCreateWindow = { showCreateDialog = true },
                        )
                    }

                    if (showCreateDialog) {
                        CreateWindowDialog(
                            viewModel = solarViewModel,
                            onDismiss = { showCreateDialog = false },
                        )
                    }
                }
            }
        }
    }
}
