package ovh.tenjo.pv

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * When the user swipes the notification, this receiver re-posts it
 * by re-starting the foreground service with the last known values.
 */
class NotificationDismissReceiver : BroadcastReceiver() {
    companion object {
        var lastPower: String = "?"
        var lastSoc: String = "?"
        var lastMinutes: String = "0"
        var isActive: Boolean = false
    }

    override fun onReceive(context: Context, intent: Intent?) {
        if (isActive) {
            AutoDischargeService.start(context, lastPower, lastSoc, lastMinutes)
        }
    }
}
