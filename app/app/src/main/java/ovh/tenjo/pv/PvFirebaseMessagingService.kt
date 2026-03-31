package ovh.tenjo.pv

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class PvFirebaseMessagingService : FirebaseMessagingService() {

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        val windowName = data["window_name"] ?: ""
        when (data["type"]) {
            "auto_discharge_active" -> {
                AutoDischargeService.start(
                    this,
                    power = data["power_kw"] ?: "?",
                    soc = data["soc"] ?: "?",
                    minutes = data["minutes_remaining"] ?: "0",
                    windowName = windowName,
                    isUpdate = false,
                )
            }
            "auto_discharge_update" -> {
                AutoDischargeService.start(
                    this,
                    power = data["power_kw"] ?: "?",
                    soc = data["soc"] ?: "?",
                    minutes = data["minutes_remaining"] ?: "0",
                    windowName = windowName,
                    isUpdate = true,
                )
            }
            "auto_discharge_stopped" -> {
                AutoDischargeService.stop(this)
            }
            "charge_window_active" -> {
                ChargeWindowService.start(
                    this,
                    power = data["power_w"] ?: "?",
                    minutes = "0",
                    windowName = windowName,
                    isUpdate = false,
                )
            }
            "charge_window_update" -> {
                ChargeWindowService.start(
                    this,
                    power = data["power_w"] ?: "?",
                    minutes = data["minutes_remaining"] ?: "0",
                    windowName = windowName,
                    isUpdate = true,
                )
            }
            "charge_window_stopped" -> {
                ChargeWindowService.stop(this)
            }
        }
    }
}
