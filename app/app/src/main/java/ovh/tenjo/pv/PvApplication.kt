package ovh.tenjo.pv

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager

class PvApplication : Application() {
    companion object {
        const val CHANNEL_AUTO_DISCHARGE = "auto_discharge"
        const val CHANNEL_CHARGE_WINDOW = "charge_window"
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
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_CHARGE_WINDOW,
                "Charge Window",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "Charge window status notifications"
            },
        )
    }
}
