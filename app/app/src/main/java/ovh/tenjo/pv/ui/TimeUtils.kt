package ovh.tenjo.pv.ui

/** Parse "HH:MM" to total minutes since midnight. */
fun parseTimeToMinutes(time: String): Int {
    val parts = time.split(":")
    if (parts.size != 2) return 0
    return (parts[0].toIntOrNull() ?: 0) * 60 + (parts[1].toIntOrNull() ?: 0)
}

/** Convert total minutes to "HH:MM", wrapping at 24h. */
fun minutesToTimeString(totalMinutes: Int): String {
    val m = ((totalMinutes % 1440) + 1440) % 1440
    return "%02d:%02d".format(m / 60, m % 60)
}

/** Calculate duration in minutes from start to end, handling midnight crossing. */
fun calcDuration(startTime: String, endTime: String): Int {
    val start = parseTimeToMinutes(startTime)
    val end = parseTimeToMinutes(endTime)
    return ((end - start) + 1440) % 1440
}

/** Calculate end time string from start time + duration in minutes. */
fun calcEndTime(startTime: String, durationMinutes: Int): String {
    val start = parseTimeToMinutes(startTime)
    return minutesToTimeString(start + durationMinutes)
}

/**
 * Estimate charge energy (kWh) for a cosine bell curve charge window.
 *
 * The integral of cosine interpolation from power_a to power_b over T hours
 * equals (power_a + power_b) / 2 * T — the average of the two endpoints.
 */
fun estimateChargeEnergy(
    startTime: String, startPower: Int,
    peakTime: String, peakPower: Int,
    endTime: String, endPower: Int,
): Double {
    val startMin = parseTimeToMinutes(startTime)
    var peakMin = parseTimeToMinutes(peakTime)
    var endMin = parseTimeToMinutes(endTime)
    if (peakMin <= startMin) peakMin += 1440
    if (endMin <= peakMin) endMin += 1440

    val seg1Hours = (peakMin - startMin) / 60.0
    val seg2Hours = (endMin - peakMin) / 60.0

    val seg1Wh = (startPower + peakPower) / 2.0 * seg1Hours
    val seg2Wh = (peakPower + endPower) / 2.0 * seg2Hours

    return (seg1Wh + seg2Wh) / 1000.0
}

/** Estimate discharge energy (kWh) based on SOC delta and 4.8 kWh usable capacity. */
fun estimateDischargeEnergy(currentSoc: Double, targetSoc: Double): Double {
    val delta = (currentSoc - targetSoc).coerceAtLeast(0.0)
    return delta / 100.0 * 4.8
}
