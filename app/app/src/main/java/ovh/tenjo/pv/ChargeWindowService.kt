package ovh.tenjo.pv

import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import androidx.core.app.NotificationCompat

class ChargeWindowService : Service() {

    companion object {
        const val NOTIFICATION_ID = 1002
        private const val EXTRA_POWER = "power_w"
        private const val EXTRA_MINUTES = "minutes_remaining"
        private const val EXTRA_WINDOW_NAME = "window_name"
        private const val EXTRA_IS_UPDATE = "is_update"

        var lastPower: String = "?"
        var lastMinutes: String = "0"
        var lastWindowName: String = ""
        var isActive: Boolean = false

        fun start(
            context: Context,
            power: String,
            minutes: String,
            windowName: String = "",
            isUpdate: Boolean = false,
        ) {
            lastPower = power
            lastMinutes = minutes
            lastWindowName = windowName
            isActive = true
            val intent = Intent(context, ChargeWindowService::class.java).apply {
                putExtra(EXTRA_POWER, power)
                putExtra(EXTRA_MINUTES, minutes)
                putExtra(EXTRA_WINDOW_NAME, windowName)
                putExtra(EXTRA_IS_UPDATE, isUpdate)
            }
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            isActive = false
            context.stopService(Intent(context, ChargeWindowService::class.java))
        }
    }

    private var started = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val power = intent?.getStringExtra(EXTRA_POWER) ?: "?"
        val mins = intent?.getStringExtra(EXTRA_MINUTES)?.toDoubleOrNull() ?: 0.0
        val windowName = intent?.getStringExtra(EXTRA_WINDOW_NAME) ?: ""
        val hours = (mins / 60).toInt()
        val m = (mins % 60).toInt()

        val notification = buildNotification(power, hours, m, windowName)

        if (!started) {
            startForeground(NOTIFICATION_ID, notification)
            started = true
        } else {
            getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification)
        }

        return START_STICKY
    }

    private fun buildNotification(power: String, hours: Int, mins: Int, windowName: String): android.app.Notification {
        val stopIntent = Intent(this, StopChargeBroadcastReceiver::class.java)
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

        val dismissIntent = Intent(this, ChargeWindowDismissReceiver::class.java)
        val dismissPendingIntent = PendingIntent.getBroadcast(
            this, 2, dismissIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        return NotificationCompat.Builder(this, PvApplication.CHANNEL_CHARGE_WINDOW)
            .setSmallIcon(R.drawable.ic_battery_charge)
            .setContentTitle(if (windowName.isNotBlank()) "$windowName — Charging" else "Charge Window Active")
            .setContentText("${power}W  |  ${hours}h ${mins}m remaining")
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
