package ovh.tenjo.pv.api

import com.google.gson.annotations.SerializedName
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*

// ------------------------------------------------------------------
// Data models
// ------------------------------------------------------------------

data class PowerStatus(
    @SerializedName("current_power_kw") val currentPowerKw: Double,
    @SerializedName("energy_today_kwh") val energyTodayKwh: Double,
    @SerializedName("total_energy_kwh") val totalEnergyKwh: Double,
)

data class BatteryStatus(
    @SerializedName("state_of_charge") val stateOfCharge: Double,
    @SerializedName("rated_capacity") val ratedCapacity: Double,
    @SerializedName("operating_status") val operatingStatus: String,
    @SerializedName("backup_time") val backupTime: String,
    @SerializedName("bus_voltage") val busVoltage: Double,
    @SerializedName("total_charged_today_kwh") val totalChargedTodayKwh: Double,
    @SerializedName("total_discharged_today_kwh") val totalDischargedTodayKwh: Double,
    @SerializedName("current_charge_discharge_kw") val currentChargeDischargeKw: Double,
)

data class ForcedChargeRequest(
    val mode: String,            // "stop", "charge", "discharge"
    @SerializedName("power_kw") val powerKw: Double = 0.7,
    @SerializedName("setting_mode") val settingMode: String = "duration",
    @SerializedName("duration_min") val durationMin: Int = 60,
)

data class ForcedChargeResponse(
    val success: Boolean,
    val mode: String?,
)

data class HealthResponse(
    val status: String,
)

// ------------------------------------------------------------------
// Retrofit interface
// ------------------------------------------------------------------

interface SolarApiService {

    @GET("health")
    suspend fun health(): HealthResponse

    @GET("status")
    suspend fun getStatus(): PowerStatus

    @GET("batteries/{batteryId}")
    suspend fun getBatteryStatus(@Path("batteryId") batteryId: String): BatteryStatus

    @POST("batteries/{batteryId}/forced-charge")
    suspend fun setForcedCharge(
        @Path("batteryId") batteryId: String,
        @Body request: ForcedChargeRequest,
    ): ForcedChargeResponse
}

// ------------------------------------------------------------------
// API client singleton
// ------------------------------------------------------------------

object SolarApiClient {
    // For emulator → host: http://10.0.2.2:8000
    // For real device on same network: http://<your-pc-ip>:8000
    var baseUrl: String = "http://10.0.2.2:8000/"
    var apiKey: String = ""

    // Known device IDs from your plant
    const val BATTERY_ID = "NE=239198746"

    val service: SolarApiService by lazy {
        Retrofit.Builder()
            .baseUrl(baseUrl)
            .addConverterFactory(GsonConverterFactory.create())
            .client(
                okhttp3.OkHttpClient.Builder()
                    .addInterceptor { chain ->
                        val request = chain.request().newBuilder()
                            .addHeader("X-API-Key", apiKey)
                            .build()
                        chain.proceed(request)
                    }
                    .build()
            )
            .build()
            .create(SolarApiService::class.java)
    }
}
