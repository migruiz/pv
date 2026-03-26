package ovh.tenjo.pv

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.firebase.messaging.FirebaseMessaging
import ovh.tenjo.pv.api.SolarApiClient
import ovh.tenjo.pv.ui.DashboardScreen
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
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    DashboardScreen(
                        viewModel = solarViewModel,
                        modifier = Modifier.padding(innerPadding),
                    )
                }
            }
        }
    }
}
