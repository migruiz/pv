package ovh.tenjo.pv

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import ovh.tenjo.pv.api.SolarApiClient

class StopDischargeBroadcastReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        // Stop the foreground service immediately
        AutoDischargeService.stop(context)

        // Call the backward-compatible API to stop all active windows
        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                SolarApiClient.service.stopAllDischarge(SolarApiClient.BATTERY_ID)
            } catch (_: Exception) { }
            finally {
                pendingResult.finish()
            }
        }
    }
}
