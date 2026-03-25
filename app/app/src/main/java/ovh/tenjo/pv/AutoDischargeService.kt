package ovh.tenjo.pv

import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat

class AutoDischargeService : Service() {

    companion object {
        const val NOTIFICATION_ID = 1001
        private const val EXTRA_POWER = "power_kw"
        private const val EXTRA_SOC = "soc"
        private const val EXTRA_MINUTES = "minutes_remaining"
        private const val EXTRA_IS_UPDATE = "is_update"

        fun start(context: Context, power: String, soc: String, minutes: String, isUpdate: Boolean = false) {
            NotificationDismissReceiver.lastPower = power
            NotificationDismissReceiver.lastSoc = soc
            NotificationDismissReceiver.lastMinutes = minutes
            NotificationDismissReceiver.isActive = true
            val intent = Intent(context, AutoDischargeService::class.java).apply {
                putExtra(EXTRA_POWER, power)
                putExtra(EXTRA_SOC, soc)
                putExtra(EXTRA_MINUTES, minutes)
                putExtra(EXTRA_IS_UPDATE, isUpdate)
            }
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            NotificationDismissReceiver.isActive = false
            context.stopService(Intent(context, AutoDischargeService::class.java))
        }
    }

    private var started = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val power = intent?.getStringExtra(EXTRA_POWER) ?: "?"
        val soc = intent?.getStringExtra(EXTRA_SOC) ?: "?"
        val mins = intent?.getStringExtra(EXTRA_MINUTES)?.toDoubleOrNull() ?: 0.0
        val isUpdate = intent?.getBooleanExtra(EXTRA_IS_UPDATE, false) ?: false
        val hours = (mins / 60).toInt()
        val m = (mins % 60).toInt()

        val notification = buildNotification(power, soc, hours, m)

        if (!started) {
            // First time — startForeground shows with sound
            startForeground(NOTIFICATION_ID, notification)
            started = true
        } else {
            // Subsequent updates — silent, just update the text
            getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification)
        }

        return START_STICKY
    }

    private fun buildNotification(power: String, soc: String, hours: Int, mins: Int): android.app.Notification {
        val stopIntent = Intent(this, StopDischargeBroadcastReceiver::class.java)
        val stopPendingIntent = PendingIntent.getBroadcast(
            this, 0, stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val tapIntent = Intent(this, MainActivity::class.java).apply {
            this.flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val tapPendingIntent = PendingIntent.getActivity(
            this, 0, tapIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val dismissIntent = Intent(this, NotificationDismissReceiver::class.java)
        val dismissPendingIntent = PendingIntent.getBroadcast(
            this, 1, dismissIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        return NotificationCompat.Builder(this, PvApplication.CHANNEL_AUTO_DISCHARGE)
            .setSmallIcon(R.drawable.ic_battery_discharge)
            .setContentTitle("Auto-Discharge Active")
            .setContentText("${power} kW  |  SOC ${soc}%  |  ${hours}h ${mins}m")
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setContentIntent(tapPendingIntent)
            .setDeleteIntent(dismissPendingIntent)
            .addAction(R.drawable.ic_stop, "Stop", stopPendingIntent)
            .build()
    }
}
