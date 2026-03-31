package ovh.tenjo.pv

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * When the user swipes the charge notification, re-post it
 * if the charge window is still active.
 */
class ChargeWindowDismissReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (ChargeWindowService.isActive) {
            ChargeWindowService.start(
                context,
                ChargeWindowService.lastPower,
                ChargeWindowService.lastMinutes,
                ChargeWindowService.lastWindowName,
            )
        }
    }
}
