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

// ------------------------------------------------------------------
// Retrofit interface
// ------------------------------------------------------------------

interface SolarApiService {

    @GET("health")
    suspend fun health(): HealthResponse

    @GET("dashboard")
    suspend fun getDashboard(): DashboardData
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
