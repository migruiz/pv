package ovh.tenjo.pv

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class StopChargeBroadcastReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        ChargeWindowService.stop(context)
    }
}
