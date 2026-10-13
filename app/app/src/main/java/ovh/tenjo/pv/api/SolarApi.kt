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
    /** Where TOU mode sends solar the house does not use: the battery (true) or the grid. */
    @SerializedName("spare_solar_to_battery") val spareSolarToBattery: Boolean? = null,
)

// ------------------------------------------------------------------
// Data models — Daytime battery target
// ------------------------------------------------------------------

/** Spare solar charges the battery up to the target, and goes to the grid above it. */
data class DaytimeTarget(
    @SerializedName("target_soc") val targetSoc: Int,
    /** Once at the target, spare solar goes back into the battery at this %. */
    @SerializedName("resume_below") val resumeBelow: Int,
    /** A discharge window is running: spare solar goes to the grid until it ends. */
    @SerializedName("window_running") val windowRunning: Boolean,
    /** Only on a save's reply: saved, but the inverter did not respond yet (the API retries). */
    val warning: String? = null,
)

data class DaytimeTargetSettings(
    @SerializedName("target_soc") val targetSoc: Int,
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
// Data models — Electricity usage
// ------------------------------------------------------------------

/** Electricity bought and sold each day, by the tariff's price windows, from the grid meter. */
data class UsageReport(
    val tariff: Tariff,
    /** Oldest first; the last one is today so far. */
    val days: List<UsageDay>,
)

data class Tariff(
    val name: String,
    /** The price bands in display order; their ids key each day's `bought`. */
    val bands: List<TariffBand>,
    @SerializedName("export_cents_per_kwh") val exportCentsPerKwh: Double,
    @SerializedName("standing_charge_eur_per_day") val standingChargeEurPerDay: Double,
)

data class TariffBand(
    val id: String,
    val name: String,
    /** "02:00-04:00" */
    val hours: String,
    @SerializedName("cents_per_kwh") val centsPerKwh: Double,
)

/** kWh, and what it cost or earned in euro. */
data class Energy(
    val kwh: Double = 0.0,
    val eur: Double = 0.0,
)

data class UsageDay(
    /** Dublin date, "2026-10-13". */
    val date: String,
    /** The whole day was read; false for today and for a day with gaps. */
    val complete: Boolean,
    @SerializedName("measured_hours") val measuredHours: Double,
    /** Bought from the grid, by band id. */
    val bought: Map<String, Energy> = emptyMap(),
    @SerializedName("bought_total") val boughtTotal: Energy = Energy(),
    val sold: Energy = Energy(),
    /** Bought minus sold, without the standing charge: below 0 the day earned money. */
    @SerializedName("net_eur") val netEur: Double = 0.0,
    /** In time order: 48, or 46 / 50 on a clock-change day; today's future ones are zeros. */
    @SerializedName("half_hours") val halfHours: List<HalfHour>? = null,
    /** What the house used from any source (grid, battery or solar), kWh, not corrected. */
    @SerializedName("used_kwh") val usedKwh: Double? = null,
)

data class HalfHour(
    /** Dublin wall clock, "02:30" */
    val start: String,
    /** The band id its price comes from */
    val band: String,
    @SerializedName("bought_kwh") val boughtKwh: Double = 0.0,
    @SerializedName("bought_eur") val boughtEur: Double = 0.0,
    @SerializedName("sold_kwh") val soldKwh: Double = 0.0,
    @SerializedName("sold_eur") val soldEur: Double = 0.0,
    /** What the house used in this half hour from any source, kWh, not corrected. */
    @SerializedName("used_kwh") val usedKwh: Double? = null,
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

    @GET("daytime-target")
    suspend fun getDaytimeTarget(): DaytimeTarget

    @PUT("daytime-target")
    suspend fun setDaytimeTarget(@Body body: DaytimeTargetSettings): DaytimeTarget

    @GET("usage")
    suspend fun getUsage(@Query("days") days: Int): UsageReport
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
