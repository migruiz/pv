package ovh.tenjo.pv

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class PvFirebaseMessagingService : FirebaseMessagingService() {

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        when (data["type"]) {
            "auto_discharge_active" -> {
                AutoDischargeService.start(
                    this,
                    power = data["power_kw"] ?: "?",
                    soc = data["soc"] ?: "?",
                    minutes = data["minutes_remaining"] ?: "0",
                    isUpdate = false,
                )
            }
            "auto_discharge_update" -> {
                AutoDischargeService.start(
                    this,
                    power = data["power_kw"] ?: "?",
                    soc = data["soc"] ?: "?",
                    minutes = data["minutes_remaining"] ?: "0",
                    isUpdate = true,
                )
            }
            "auto_discharge_stopped" -> {
                AutoDischargeService.stop(this)
            }
        }
    }
}
