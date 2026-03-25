package ovh.tenjo.pv.api

import com.google.gson.annotations.SerializedName
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*

// ------------------------------------------------------------------
// Data models
// ------------------------------------------------------------------

data class DashboardData(
    @SerializedName("pv_kw") val pvKw: Double,
    @SerializedName("battery_soc") val batterySoc: Double,
    @SerializedName("battery_charge_discharge_kw") val batteryChargeDischargeKw: Double,
    @SerializedName("battery_charging") val batteryCharging: Boolean,
    @SerializedName("grid_kw") val gridKw: Double,
    @SerializedName("grid_importing") val gridImporting: Boolean,
    @SerializedName("home_kw") val homeKw: Double,
    @SerializedName("energy_today_kwh") val energyTodayKwh: Double,
    @SerializedName("discharged_today_kwh") val dischargedTodayKwh: Double,
    @SerializedName("total_energy_kwh") val totalEnergyKwh: Double,
)

data class HealthResponse(
    val status: String,
)

data class AutoDischargeResponse(
    val success: Boolean,
    @SerializedName("initial_soc") val initialSoc: Double? = null,
    @SerializedName("discharge_power_kw") val dischargePowerKw: Double? = null,
    @SerializedName("target_time") val targetTime: String? = null,
    val detail: String? = null,
)

data class AutoDischargeStatus(
    val active: Boolean,
    @SerializedName("battery_id") val batteryId: String? = null,
    @SerializedName("current_soc") val currentSoc: Double? = null,
    @SerializedName("discharge_power_kw") val dischargePowerKw: Double? = null,
    @SerializedName("target_time") val targetTime: String? = null,
    @SerializedName("minutes_remaining") val minutesRemaining: Double? = null,
    @SerializedName("hours_remaining") val hoursRemaining: Double? = null,
    @SerializedName("last_adjustment") val lastAdjustment: String? = null,
)

// ------------------------------------------------------------------
// Retrofit interface
// ------------------------------------------------------------------

interface SolarApiService {

    @GET("health")
    suspend fun health(): HealthResponse

    @GET("dashboard")
    suspend fun getDashboard(): DashboardData

    @POST("batteries/{batteryId}/auto-discharge")
    suspend fun startAutoDischarge(@Path("batteryId") batteryId: String): AutoDischargeResponse

    @POST("batteries/{batteryId}/auto-discharge/stop")
    suspend fun stopAutoDischarge(@Path("batteryId") batteryId: String): AutoDischargeResponse

    @GET("batteries/{batteryId}/auto-discharge/status")
    suspend fun getAutoDischargeStatus(@Path("batteryId") batteryId: String): AutoDischargeStatus
}

// ------------------------------------------------------------------
// API client singleton
// ------------------------------------------------------------------

object SolarApiClient {
    var baseUrl: String = "http://10.0.2.2:8000/"
    var apiKey: String = ""

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
