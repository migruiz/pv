package ovh.tenjo.pv

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager

class PvApplication : Application() {
    companion object {
        const val CHANNEL_AUTO_DISCHARGE = "auto_discharge"
    }

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_AUTO_DISCHARGE,
                "Auto-Discharge",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "Auto-discharge status notifications"
            },
        )
        // Charge windows are gone: remove their channel from the phone's notification settings
        nm.deleteNotificationChannel("charge_window")
    }
}
