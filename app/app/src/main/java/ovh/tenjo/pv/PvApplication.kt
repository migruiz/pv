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
        val channel = NotificationChannel(
            CHANNEL_AUTO_DISCHARGE,
            "Auto-Discharge",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Auto-discharge status notifications"
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }
}
