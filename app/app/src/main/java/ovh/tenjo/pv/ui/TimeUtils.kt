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

/** Estimate discharge energy (kWh) based on SOC delta and 4.8 kWh usable capacity. */
fun estimateDischargeEnergy(currentSoc: Double, targetSoc: Double): Double {
    val delta = (currentSoc - targetSoc).coerceAtLeast(0.0)
    return delta / 100.0 * 4.8
}
