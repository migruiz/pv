package ovh.tenjo.pv.api

import com.google.gson.JsonParser
import com.google.gson.annotations.SerializedName
import retrofit2.HttpException
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
    @SerializedName("operation_mode") val operationMode: Int = 5,
    @SerializedName("charge_from_ac") val chargeFromAc: Int = 1,
    @SerializedName("max_charge_power") val maxChargePower: Int = 2500,
)

// ------------------------------------------------------------------
// Data models — Discharge Windows
// ------------------------------------------------------------------

/** A saved window, with what the API is doing with it right now. */
data class DischargeWindow(
    val id: String,
    val name: String,
    @SerializedName("start_time") val startTime: String,
    @SerializedName("duration_minutes") val durationMinutes: Int,
    @SerializedName("target_soc") val targetSoc: Double,
    val notify: Boolean,
    val enabled: Boolean,
    val state: WindowState = WindowState(),
    /** Only on a save's reply: saved, but the inverter did not respond yet (the API retries). */
    val warning: String? = null,
) {
    fun settings() = WindowSettings(name, startTime, durationMinutes, targetSoc, notify, enabled)
}

data class WindowState(
    val discharging: Boolean = false,
    @SerializedName("target_reached") val targetReached: Boolean = false,
    @SerializedName("power_kw") val powerKw: Double? = null,
    val soc: Double? = null,
    @SerializedName("minutes_remaining") val minutesRemaining: Double? = null,
)

/** What the window screen edits and saves: the API applies it straight away. */
data class WindowSettings(
    val name: String,
    @SerializedName("start_time") val startTime: String,
    @SerializedName("duration_minutes") val durationMinutes: Int,
    @SerializedName("target_soc") val targetSoc: Double,
    val notify: Boolean,
    val enabled: Boolean,
)

// ------------------------------------------------------------------
// Retrofit interface
// ------------------------------------------------------------------

interface SolarApiService {

    @GET("dashboard")
    suspend fun getDashboard(): DashboardData

    @GET("discharge-windows")
    suspend fun getDischargeWindows(): List<DischargeWindow>

    @POST("discharge-windows")
    suspend fun createDischargeWindow(@Body body: WindowSettings): DischargeWindow

    @PUT("discharge-windows/{windowId}")
    suspend fun updateDischargeWindow(
        @Path("windowId") windowId: String,
        @Body body: WindowSettings,
    ): DischargeWindow

    @DELETE("discharge-windows/{windowId}")
    suspend fun deleteDischargeWindow(@Path("windowId") windowId: String)
}

/** The API's reason for refusing a request ("Overlaps with ..."), or the error itself. */
fun apiErrorMessage(e: Throwable): String {
    val body = (e as? HttpException)?.response()?.errorBody()?.string()
    if (body != null) {
        try {
            val detail = JsonParser.parseString(body).asJsonObject.get("detail")
            return when {
                detail == null -> body
                detail.isJsonPrimitive -> detail.asString
                // FastAPI validation errors: [{"loc": [..., "field"], "msg": "..."}]
                detail.isJsonArray && detail.asJsonArray.size() > 0 -> detail.asJsonArray[0].asJsonObject.let {
                    val field = it.getAsJsonArray("loc")?.lastOrNull()?.asString
                    val msg = it.get("msg")?.asString ?: body
                    if (field != null) "$field: $msg" else msg
                }
                else -> body
            }
        } catch (_: Exception) {
            return body
        }
    }
    return e.message ?: "Connection failed"
}

// ------------------------------------------------------------------
// API client singleton
// ------------------------------------------------------------------

object SolarApiClient {
    var baseUrl: String = "http://10.0.2.2:8000/"
    var apiKey: String = ""

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
