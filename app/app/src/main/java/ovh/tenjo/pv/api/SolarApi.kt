package ovh.tenjo.pv.api

import com.google.gson.annotations.SerializedName
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*

// ------------------------------------------------------------------
// Data models — Dashboard
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

// ------------------------------------------------------------------
// Data models — Discharge Windows
// ------------------------------------------------------------------

data class DischargeWindow(
    val id: String,
    val name: String,
    @SerializedName("start_time") val startTime: String,
    @SerializedName("duration_minutes") val durationMinutes: Int,
    @SerializedName("target_soc") val targetSoc: Double,
    val notify: Boolean,
    val enabled: Boolean,
)

data class DischargeWindowCreate(
    val name: String,
    @SerializedName("start_time") val startTime: String,
    @SerializedName("duration_minutes") val durationMinutes: Int,
    @SerializedName("target_soc") val targetSoc: Double,
    val notify: Boolean = true,
    val enabled: Boolean = true,
)

data class DischargeWindowUpdate(
    val name: String? = null,
    @SerializedName("start_time") val startTime: String? = null,
    @SerializedName("duration_minutes") val durationMinutes: Int? = null,
    @SerializedName("target_soc") val targetSoc: Double? = null,
    val notify: Boolean? = null,
    val enabled: Boolean? = null,
)

data class DischargeWindowStatus(
    @SerializedName("window_id") val windowId: String,
    @SerializedName("window_name") val windowName: String,
    val active: Boolean,
    @SerializedName("current_soc") val currentSoc: Double? = null,
    @SerializedName("discharge_power_kw") val dischargePowerKw: Double? = null,
    @SerializedName("target_time") val targetTime: String? = null,
    @SerializedName("minutes_remaining") val minutesRemaining: Double? = null,
    @SerializedName("hours_remaining") val hoursRemaining: Double? = null,
    @SerializedName("last_adjustment") val lastAdjustment: String? = null,
)

data class StartWindowResponse(
    val success: Boolean,
    @SerializedName("window_id") val windowId: String? = null,
    @SerializedName("window_name") val windowName: String? = null,
    @SerializedName("initial_soc") val initialSoc: Double? = null,
    @SerializedName("discharge_power_kw") val dischargePowerKw: Double? = null,
    @SerializedName("target_time") val targetTime: String? = null,
    val detail: String? = null,
)

data class StopWindowResponse(
    val success: Boolean,
    val detail: String? = null,
)

// ------------------------------------------------------------------
// Retrofit interface
// ------------------------------------------------------------------

interface SolarApiService {

    @GET("health")
    suspend fun health(): HealthResponse

    @GET("dashboard")
    suspend fun getDashboard(): DashboardData

    // -- Discharge Windows CRUD --

    @GET("discharge-windows")
    suspend fun getDischargeWindows(): List<DischargeWindow>

    @GET("discharge-windows/{windowId}")
    suspend fun getDischargeWindow(@Path("windowId") windowId: String): DischargeWindow

    @POST("discharge-windows")
    suspend fun createDischargeWindow(@Body body: DischargeWindowCreate): DischargeWindow

    @PUT("discharge-windows/{windowId}")
    suspend fun updateDischargeWindow(
        @Path("windowId") windowId: String,
        @Body body: DischargeWindowUpdate,
    ): DischargeWindow

    @DELETE("discharge-windows/{windowId}")
    suspend fun deleteDischargeWindow(@Path("windowId") windowId: String)

    // -- Discharge Window Control --

    @GET("discharge-windows/status")
    suspend fun getWindowStatuses(): List<DischargeWindowStatus>

    @GET("discharge-windows/{windowId}/status")
    suspend fun getWindowStatus(@Path("windowId") windowId: String): DischargeWindowStatus

    @POST("discharge-windows/{windowId}/start")
    suspend fun startWindow(@Path("windowId") windowId: String): StartWindowResponse

    @POST("discharge-windows/{windowId}/stop")
    suspend fun stopWindow(@Path("windowId") windowId: String): StopWindowResponse

    // Backward-compatible: stop all active windows
    @POST("batteries/{batteryId}/auto-discharge/stop")
    suspend fun stopAllDischarge(@Path("batteryId") batteryId: String): StopWindowResponse
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
