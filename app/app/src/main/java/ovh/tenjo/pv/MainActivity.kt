package ovh.tenjo.pv

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import ovh.tenjo.pv.api.SolarApiClient
import ovh.tenjo.pv.ui.DashboardScreen
import ovh.tenjo.pv.ui.theme.PVManagerTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // Local API via ADB reverse (adb reverse tcp:8000 tcp:8000)
        SolarApiClient.baseUrl = "http://localhost:8000/"
        SolarApiClient.apiKey = "test"

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
