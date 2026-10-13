package ovh.tenjo.pv.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculateCentroid
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.ZoomIn
import androidx.compose.material.icons.filled.ZoomOut
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.geometry.isSpecified
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ovh.tenjo.pv.MonthsState
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.UsageState
import ovh.tenjo.pv.api.Energy
import ovh.tenjo.pv.api.HalfHour
import ovh.tenjo.pv.api.Tariff
import ovh.tenjo.pv.api.UsageDay
import ovh.tenjo.pv.api.UsageMonth
import ovh.tenjo.pv.ui.theme.*
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

private val DUBLIN = ZoneId.of("Europe/Dublin")
private val DAY_LABEL = DateTimeFormatter.ofPattern("EEE d MMM", Locale.ENGLISH)
private val DAY_SHORT = DateTimeFormatter.ofPattern("EEE", Locale.ENGLISH)
private val DAY_MONTH = DateTimeFormatter.ofPattern("d MMM", Locale.ENGLISH)
private val MONTH_LABEL = DateTimeFormatter.ofPattern("MMMM yyyy", Locale.ENGLISH)
private val MONTH_SHORT = DateTimeFormatter.ofPattern("MMM", Locale.ENGLISH)
private val MONTH_SHORT_YEAR = DateTimeFormatter.ofPattern("MMM yy", Locale.ENGLISH)

/** Each price band's colour; sold is the solar yellow. */
private fun bandColor(id: String): Color = when (id) {
    "boost" -> BatteryGreen
    "night" -> GridBlue
    "day" -> EnergyOrange
    else -> Outline
}

private fun euro(value: Double) = "€%.2f".format(value)
private fun kwh(value: Double) = "%.2f".format(value)

/** A value in the chosen unit: "€1.14" or "10.49". */
private fun Energy.shown(inEuro: Boolean) = if (inEuro) euro(eur) else kwh(kwh)
private fun Energy.amount(inEuro: Boolean) = if (inEuro) eur else kwh

/**
 * Electricity bought and sold, by the tariff's price windows. Day: the chosen day (net, bought, sold, its hours),
 * what it bought at each price, and its week with the windows picked by the chips. Month: the same for a month,
 * with a bar per day, and the months.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ElectricityScreen(
    viewModel: SolarViewModel,
    onBack: () -> Unit,
) {
    val state by viewModel.usage.collectAsState()
    val monthsState by viewModel.months.collectAsState()

    DisposableEffect(Unit) {
        viewModel.openUsage()
        onDispose { viewModel.closeUsage() }
    }

    var inEuro by remember { mutableStateOf(true) }
    var byMonth by remember { mutableStateOf(false) }
    // null: the latest day loaded (today), so the screen follows midnight
    var selectedDate by remember { mutableStateOf<String?>(null) }
    // null: the latest month (this one)
    var selectedMonth by remember { mutableStateOf<String?>(null) }
    // null: every band
    var shownBands by remember { mutableStateOf<Set<String>?>(null) }

    if (byMonth) {
        DisposableEffect(Unit) {
            viewModel.openMonths()
            onDispose { viewModel.closeMonths() }
        }
    }

    val tariff = state.report?.tariff ?: monthsState.report?.tariff
    val bands = shownBands ?: tariff?.bands?.map { it.id }?.toSet().orEmpty()
    val toggleBand = { id: String ->
        val next = if (id in bands) bands - id else bands + id
        if (next.isNotEmpty()) shownBands = next  // at least one stays on
    }

    Scaffold(
        topBar = {
            // Back, Day | Month and kWh | € in one row; the tariff's name is in the note at the bottom
            TopAppBar(
                title = {
                    Toggle(listOf("Day", "Month"), selected = if (byMonth) 1 else 0) { byMonth = it == 1 }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    Toggle(listOf("kWh", "€"), selected = if (inEuro) 1 else 0) { inEuro = it == 1 }
                    Spacer(Modifier.width(8.dp))
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.surface)
                .verticalScroll(rememberScrollState())
                .padding(padding)
                .padding(vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            if (byMonth) {
                MonthView(
                    state = monthsState,
                    selectedMonth = selectedMonth,
                    inEuro = inEuro,
                    shownBands = bands,
                    onSelectMonth = { selectedMonth = it },
                    onToggleBand = toggleBand,
                    onOpenDay = { date ->
                        selectedDate = date
                        byMonth = false
                        // A day outside the days loaded: load the week around it
                        if (state.report?.days.orEmpty().none { it.date == date }) {
                            viewModel.showUsageDays(endAround(LocalDate.parse(date)))
                        }
                    },
                    onRetry = { viewModel.loadMonths() },
                )
            } else {
                DayView(
                    state = state,
                    selectedDate = selectedDate,
                    inEuro = inEuro,
                    shownBands = bands,
                    onSelectDate = { selectedDate = it },
                    onShowDays = { viewModel.showUsageDays(it) },
                    onToggleBand = toggleBand,
                    onRetry = { viewModel.loadUsage() },
                )
            }
        }
    }
}

/** The last of the days shown around `day`: three days on, or today (null). */
private fun endAround(day: LocalDate): String? {
    val end = minOf(day.plusDays(3), today())
    return if (end == today()) null else end.toString()
}

// ------------------------------------------------------------------
// Header
// ------------------------------------------------------------------

/** Choices in a pill, the chosen one in yellow: Day | Month and kWh | €, side by side in the top bar. */
@Composable
private fun Toggle(options: List<String>, selected: Int, onSelect: (Int) -> Unit) {
    Row(
        Modifier
            .background(SurfaceContainerLow, RoundedCornerShape(50))
            .padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        options.forEachIndexed { i, label -> ToggleButton(label, selected = i == selected) { onSelect(i) } }
    }
}

@Composable
private fun ToggleButton(label: String, selected: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(50),
        color = if (selected) SolarYellow else Color.Transparent,
        contentColor = if (selected) OnSolarYellow else OnSurfaceVariant,
        modifier = Modifier.heightIn(min = 44.dp).widthIn(min = 44.dp),
    ) {
        Box(Modifier.padding(horizontal = 12.dp), contentAlignment = Alignment.Center) {
            Text(
                label,
                fontWeight = if (selected) FontWeight.ExtraBold else FontWeight.Bold,
                fontSize = 14.sp,
                lineHeight = 18.sp,
                maxLines = 1,
            )
        }
    }
}

// ------------------------------------------------------------------
// Day view
// ------------------------------------------------------------------

/**
 * The chosen day, what it bought by price, and the days loaded with it. Its arrows go on past the days loaded:
 * the API is asked for the week before or after.
 */
@Composable
private fun DayView(
    state: UsageState,
    selectedDate: String?,
    inEuro: Boolean,
    shownBands: Set<String>,
    onSelectDate: (String?) -> Unit,
    onShowDays: (String?) -> Unit,
    onToggleBand: (String) -> Unit,
    onRetry: () -> Unit,
) {
    val report = state.report
    val days = report?.days.orEmpty()
    val index = if (selectedDate == null) days.lastIndex else days.indexOfFirst { it.date == selectedDate }
    if (report == null || index < 0) {
        Pending(state.error, onRetry)
        return
    }
    val day = days[index]
    val today = today()
    val first = LocalDate.parse(days.first().date)
    val last = LocalDate.parse(days.last().date)

    DayCard(
        day = day,
        tariff = report.tariff,
        inEuro = inEuro,
        onPrevious = when {
            index > 0 -> ({ onSelectDate(days[index - 1].date) })
            // Before the days loaded, while there are readings: the week ending the day before
            days.first().measuredHours > 0 -> ({
                val target = first.minusDays(1).toString()
                onSelectDate(target)
                onShowDays(target)
            })
            else -> null
        },
        onNext = when {
            index < days.lastIndex -> ({ onSelectDate(days[index + 1].date) })
            // After the days loaded: the week starting the day after, up to today
            last < today -> ({
                val target = last.plusDays(1)
                val end = minOf(target.plusDays(6), today)
                onSelectDate(target.toString())
                onShowDays(if (end == today) null else end.toString())
            })
            else -> null
        },
    )

    BandsCard(bought = day.bought, tariff = report.tariff, inEuro = inEuro)

    PeriodsCard(
        title = if (last == today) "This week" else "${days.size} days to ${last.format(DAY_LABEL)}",
        hint = if (inEuro) "€ bought · tap a day" else "kWh bought · tap a day",
        rows = days.map { Period(dayShort(it.date), it.bought, it.measuredHours > 0, dayNote(it)) },
        tariff = report.tariff,
        inEuro = inEuro,
        shownBands = shownBands,
        selectedIndex = index,
        labelWidth = 44.dp,
        onToggleBand = onToggleBand,
        onSelect = { onSelectDate(days[it].date) },
        onToday = if (last == today) null else ({
            onSelectDate(null)
            onShowDays(null)
        }),
    )

    Footer(report.tariff, state.error)
}

/** While a report loads: a spinner, or its error with Retry. */
@Composable
private fun Pending(error: String?, onRetry: () -> Unit) {
    if (error != null) {
        UsageError(error, onRetry)
    } else {
        Box(Modifier.fillMaxWidth().height(300.dp), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
        }
    }
}

/** The tariff the prices are from and the standing charge note, and a failed refresh. */
@Composable
private fun Footer(tariff: Tariff, error: String?) {
    Text(
        "${tariff.name} prices. Standing charge (${euro(tariff.standingChargeEurPerDay)} a day) not included.",
        style = MaterialTheme.typography.bodySmall,
        color = OnSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp),
    )
    if (error != null) {
        Text(
            "Could not refresh: $error",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.error,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
    }
}

// ------------------------------------------------------------------
// Day: net, bought and sold
// ------------------------------------------------------------------

private fun today(): LocalDate = LocalDate.now(DUBLIN)

private fun dayLabel(date: String): String {
    val d = LocalDate.parse(date)
    return if (d == today()) "Today (so far)" else d.format(DAY_LABEL)
}

private fun dayShort(date: String): String {
    val d = LocalDate.parse(date)
    return if (d == today()) "Today" else d.format(DAY_SHORT)
}

/** Why a day's numbers are not a whole day, or null. */
private fun dayNote(day: UsageDay): String? = when {
    day.measuredHours <= 0.0 -> "No readings"
    LocalDate.parse(day.date) == today() -> null
    !day.complete && day.measuredHours < 23 -> "Partial: %.0f h of readings".format(day.measuredHours)
    else -> null
}

@Composable
private fun DayCard(
    day: UsageDay,
    tariff: Tariff,
    inEuro: Boolean,
    onPrevious: (() -> Unit)?,
    onNext: (() -> Unit)?,
) {
    Surface(shape = RoundedCornerShape(24.dp), color = SurfaceContainerLow, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            CardHeader(dayLabel(day.date), "Previous day", "Next day", onPrevious, onNext)

            Totals(
                net = day.netEur,
                bought = day.boughtTotal,
                sold = day.sold,
                usedKwh = day.usedKwh,
                measured = day.measuredHours > 0.0,
                note = dayNote(day),
                tariff = tariff,
                inEuro = inEuro,
            )

            HorizontalDivider(color = OutlineVariant)

            // -- Every hour or half hour: bought above the line by price band, sold below, at one scale --
            key(day.date) { HalfHourChart(day.halfHours.orEmpty(), tariff, inEuro) }
        }
    }
}

/** A card's day or month between its previous and next arrows. */
@Composable
private fun CardHeader(
    label: String,
    previousLabel: String,
    nextLabel: String,
    onPrevious: (() -> Unit)?,
    onNext: (() -> Unit)?,
) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        DayArrow(Icons.AutoMirrored.Filled.KeyboardArrowLeft, previousLabel, onPrevious)
        Text(
            label,
            modifier = Modifier.weight(1f),
            textAlign = TextAlign.Center,
            style = MaterialTheme.typography.titleMedium,
            color = OnSurfaceVariant,
        )
        DayArrow(Icons.AutoMirrored.Filled.KeyboardArrowRight, nextLabel, onNext)
    }
}

/** The net, big, then bought and sold, the house's use and a note: a day's or a month's. */
@Composable
private fun Totals(
    net: Double,
    bought: Energy,
    sold: Energy,
    usedKwh: Double?,
    measured: Boolean,
    note: String?,
    tariff: Tariff,
    inEuro: Boolean,
) {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
        if (!measured) {
            Text("No readings", style = MaterialTheme.typography.headlineMedium, color = OnSurfaceVariant)
            return@Column
        }
        val earned = net < 0
        Text(
            when {
                !inEuro -> "You bought"
                earned -> "You earned"
                else -> "You spent"
            },
            color = OnSurfaceVariant,
            fontSize = 14.sp,
        )
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                if (inEuro) euro(abs(net)) else kwh(bought.kwh),
                fontSize = 44.sp,
                lineHeight = 48.sp,
                fontWeight = FontWeight.ExtraBold,
                color = if (inEuro && earned) BatteryGreen else OnSurface,
            )
            if (!inEuro) {
                Spacer(Modifier.width(4.dp))
                Text("kWh", color = OnSurfaceVariant, fontSize = 14.sp, modifier = Modifier.padding(bottom = 8.dp))
            }
        }
        Spacer(Modifier.height(6.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(18.dp), verticalAlignment = Alignment.CenterVertically) {
            CompactValue("Bought", bought.shown(inEuro), inEuro, OnSurface)
            CompactValue(
                "Sold · ${trimCents(tariff.exportCentsPerKwh)}c",
                sold.shown(inEuro),
                inEuro,
                SolarYellow,
            )
        }
        // Whatever the source (grid, battery or solar): always kWh
        usedKwh?.let { used ->
            Spacer(Modifier.height(4.dp))
            Text("House used ${kwh(used)} kWh", fontSize = 12.sp, color = OnSurfaceVariant)
        }
        if (note != null) {
            Spacer(Modifier.height(6.dp))
            Text(note, style = MaterialTheme.typography.bodySmall, color = OnSurfaceVariant)
        }
    }
}

@Composable
private fun CompactValue(label: String, value: String, inEuro: Boolean, color: Color) {
    Row(verticalAlignment = Alignment.Bottom) {
        Text("$label ", fontSize = 13.sp, color = OnSurfaceVariant)
        Text(value, fontSize = 15.sp, fontWeight = FontWeight.ExtraBold, color = color)
        if (!inEuro) Text(" kWh", fontSize = 12.sp, color = OnSurfaceVariant)
    }
}

/** 19.5 -> "19.5", 10.88 -> "10.88", 20.0 -> "20". */
private fun trimCents(cents: Double): String =
    if (cents == cents.roundToInt().toDouble()) "%d".format(cents.roundToInt())
    else "%.2f".format(cents).trimEnd('0')

@Composable
private fun DayArrow(icon: ImageVector, label: String, onClick: (() -> Unit)?) {
    OutlinedIconButton(
        onClick = { onClick?.invoke() },
        enabled = onClick != null,
        border = BorderStroke(1.dp, OutlineVariant),
        modifier = Modifier.size(44.dp),
    ) {
        Icon(icon, contentDescription = label)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChartLegend(tariff: Tariff, used: String?) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        tariff.bands.forEach { LegendItem(bandColor(it.id), it.name) }
        LegendItem(SolarYellow, "Sold (below the line)")
        if (used != null) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(10.dp)
                        .background(USED_FILL, RoundedCornerShape(2.5.dp))
                        .border(1.dp, USED_STROKE, RoundedCornerShape(2.5.dp)),
                )
                Spacer(Modifier.width(6.dp))
                Text(used, fontSize = 12.sp, color = OnSurfaceVariant)
            }
        }
    }
}

/** The outline of what the house used, behind each bought bar. */
private val USED_STROKE = OnSurfaceVariant.copy(alpha = 0.6f)
private val USED_FILL = Color.White.copy(alpha = 0.06f)

@Composable
private fun LegendItem(color: Color, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        ColorDot(color, 10.dp)
        Spacer(Modifier.width(6.dp))
        Text(label, fontSize = 12.sp, color = OnSurfaceVariant)
    }
}

/** One bar of the day chart: an hour or a half hour, its half hours summed. */
private class Bar(
    val start: String,
    val end: String,
    val band: String,
    val boughtKwh: Double,
    val boughtEur: Double,
    val soldKwh: Double,
    val soldEur: Double,
    val usedKwh: Double,
)

/**
 * The day's bars, `per` half hours each: 2 for hours (each wall-clock hour is two half hours in a row, also on a
 * clock-change day), 1 for half hours. An hour sits in one band: the windows start on the hour.
 */
private fun bars(halfHours: List<HalfHour>, per: Int): List<Bar> =
    (halfHours.indices step per).map { i ->
        val part = halfHours.subList(i, minOf(i + per, halfHours.size))
        Bar(
            start = halfHours[i].start,
            end = halfHours.getOrNull(i + per)?.start ?: "24:00",
            band = halfHours[i].band,
            boughtKwh = part.sumOf { it.boughtKwh },
            boughtEur = part.sumOf { it.boughtEur },
            soldKwh = part.sumOf { it.soldKwh },
            soldEur = part.sumOf { it.soldEur },
            usedKwh = part.sumOf { it.usedKwh ?: 0.0 },
        )
    }

/**
 * The day's hours: a title with zoom buttons, the legend, the chart, the hours and, for a tapped bar, its details.
 * One bar per hour, or per half hour from 2x zoom: bought above the line in its band colour, sold below in yellow,
 * at one scale, then a strip of the band colours. Behind each bought bar, an outline of what the house used from
 * any source (in euro: at that time's price), so the hours the battery runs the house still show their use. Pinch
 * or the buttons zoom into the day (up to 8x), a sideways drag moves along it once zoomed, a tap picks a bar and
 * the details' arrows step along. Positions come from each entry index, so the 46 or 50 half hours of a
 * clock-change day still fill the width.
 */
@Composable
private fun HalfHourChart(halfHours: List<HalfHour>, tariff: Tariff, inEuro: Boolean) {
    val rates = tariff.bands.associate { it.id to it.centsPerKwh / 100 }

    // The visible part of the day: from `start` (a fraction of the day) for 1 / zoom of it
    var zoom by remember { mutableFloatStateOf(1f) }
    var start by remember { mutableFloatStateOf(0f) }
    // The picked half hour; in hours, the hour it starts. Kept across the switch between the two.
    var picked by remember { mutableStateOf<Int?>(null) }

    val hourly = zoom < HALF_HOURS_FROM
    val per = if (hourly) 2 else 1
    val bars = remember(halfHours, per) { bars(halfHours, per) }
    val n = bars.size
    val shown = picked?.let { it / per }?.takeIf { it < n }
    val up = bars.map { if (inEuro) it.boughtEur else it.boughtKwh }
    val used = bars.map { if (inEuro) it.usedKwh * (rates[it.band] ?: 0.0) else it.usedKwh }
    val down = bars.map { if (inEuro) it.soldEur else it.soldKwh }
    val colors = bars.map { bandColor(it.band) }
    val maxUp = (up + used).maxOrNull()?.coerceAtLeast(0.0) ?: 0.0
    val maxDown = down.maxOrNull()?.coerceAtLeast(0.0) ?: 0.0
    val span = if (hourly) "an hour" else "a half hour"
    val description = if (inEuro) {
        "Day chart: most bought in $span ${euro(maxUp)}, most sold ${euro(maxDown)}"
    } else {
        "Day chart: most bought in $span ${kwh(maxUp)} kWh, most sold ${kwh(maxDown)} kWh"
    }

    /** Zoom to `level`, keeping the day at `focus` (a fraction of the chart's width) where it is. */
    fun zoomTo(level: Float, focus: Float) {
        val next = level.coerceIn(1f, MAX_ZOOM)
        val dayAtFocus = start + focus / zoom
        zoom = next
        start = (dayAtFocus - focus / next).coerceIn(0f, 1f - 1f / next)
    }

    /** Move along the day by `fraction` of the chart's width (positive: towards earlier). */
    fun panBy(fraction: Float) {
        start = (start - fraction / zoom).coerceIn(0f, 1f - 1f / zoom)
    }

    /** Where the buttons zoom around: the picked bar if it is in view, else the middle. */
    fun focus(): Float {
        val i = shown ?: return 0.5f
        val at = ((i + 0.5f) / n - start) * zoom
        return if (at in 0f..1f) at else 0.5f
    }

    /** Pick bar `i` and, once zoomed, move along the day so it is in view. */
    fun pick(i: Int) {
        picked = i * per
        val from = i.toFloat() / n
        val to = (i + 1f) / n
        if (from < start) start = from
        else if (to > start + 1f / zoom) start = to - 1f / zoom
        start = start.coerceIn(0f, 1f - 1f / zoom)
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(
                    if (hourly) "Every hour" else "Every half hour",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    (if (inEuro) "euro" else "kWh") + if (zoom > 1f) " · ${"%.0f".format(zoom)}x" else "",
                    fontSize = 12.sp,
                    color = OnSurfaceVariant,
                )
            }
            IconButton(onClick = { zoomTo(zoom / 2, focus()) }, enabled = zoom > 1f) {
                Icon(Icons.Filled.ZoomOut, contentDescription = "Zoom out")
            }
            IconButton(onClick = { zoomTo(zoom * 2, focus()) }, enabled = zoom < MAX_ZOOM) {
                Icon(Icons.Filled.ZoomIn, contentDescription = "Zoom in")
            }
        }
        ChartLegend(tariff, if (inEuro) "House used, at that time's price" else "House used")

        Canvas(
            Modifier
                .fillMaxWidth()
                .height(204.dp)
                .clipToBounds()
                .semantics { contentDescription = description }
                // Two fingers zoom (and move); once zoomed, one finger dragging sideways moves along the day.
                // Anything else is left alone, so the screen still scrolls up and down over the chart. Not keyed
                // on the bars, so a pinch carries on across the switch between hours and half hours.
                .pointerInput(Unit) {
                    awaitEachGesture {
                        awaitFirstDown(requireUnconsumed = false)
                        do {
                            val event = awaitPointerEvent()
                            val width = size.width.toFloat().coerceAtLeast(1f)
                            if (event.changes.count { it.pressed } >= 2) {
                                val change = event.calculateZoom()
                                val centroid = event.calculateCentroid(useCurrent = true)
                                if (change != 1f && centroid.isSpecified) {
                                    zoomTo(zoom * change, (centroid.x / width).coerceIn(0f, 1f))
                                }
                                panBy(event.calculatePan().x / width)
                                event.changes.forEach { if (it.positionChanged()) it.consume() }
                            } else if (zoom > 1f) {
                                val pan = event.calculatePan()
                                if (abs(pan.x) > abs(pan.y)) {
                                    panBy(pan.x / width)
                                    event.changes.forEach { if (it.positionChanged()) it.consume() }
                                }
                            }
                        } while (event.changes.any { it.pressed })
                    }
                }
                .pointerInput(n, per) {
                    detectTapGestures { position ->
                        if (n == 0) return@detectTapGestures
                        val day = start + position.x / size.width / zoom
                        val i = (day * n).toInt().coerceIn(0, n - 1)
                        if (picked?.let { it / per } == i) picked = null else pick(i)
                    }
                },
        ) {
            val chart = 180.dp.toPx()
            val stripTop = chart + 8.dp.toPx()
            val strip = 6.dp.toPx()
            if (n == 0) {
                drawLine(Outline, Offset(0f, chart / 2), Offset(size.width, chart / 2), 1.dp.toPx())
                return@Canvas
            }
            val slot = size.width * zoom / n  // px per bar
            val gap = if (slot > 6.dp.toPx()) 1.dp.toPx() else 0.5f
            val bar = (slot - gap).coerceAtLeast(1f)
            val total = maxUp + maxDown
            // Bought above, sold below, one scale: the line sits where the tallest of each just fits
            val scale = if (total > 0) chart / total else 0.0
            val line = if (total > 0) (maxUp * scale).toFloat() else chart / 2
            val minBar = 1.5.dp.toPx()
            val stroke = 1.dp.toPx()
            val corner = CornerRadius(2.dp.toPx())
            for (i in 0 until n) {
                val x = (i.toFloat() / n - start) * zoom * size.width
                if (x + slot < 0f || x > size.width) continue
                // While a bar is picked, the others fade back
                val alpha = if (shown != null && i != shown) DIMMED else 1f
                if (i == shown) drawRect(PICKED, Offset(x - gap / 2, 0f), Size(slot, chart))
                // The house's use first, as a faint outline; the bought bar covers it where it is bigger
                val u = if (used[i] > 0) maxOf((used[i] * scale).toFloat(), minBar) else 0f
                if (u > 0f) {
                    drawRoundRect(USED_FILL, Offset(x, line - u), Size(bar, u), corner, alpha = alpha)
                    drawRoundRect(
                        USED_STROKE,
                        Offset(x + stroke / 2, line - u + stroke / 2),
                        Size((bar - stroke).coerceAtLeast(0f), (u - stroke).coerceAtLeast(0f)),
                        corner,
                        style = Stroke(stroke),
                        alpha = alpha,
                    )
                }
                val h = if (up[i] > 0) maxOf((up[i] * scale).toFloat(), minBar) else 0f
                if (h > 0f) drawRect(colors[i], Offset(x, line - h), Size(bar, h), alpha = alpha)
                val d = if (down[i] > 0) maxOf((down[i] * scale).toFloat(), minBar) else 0f
                if (d > 0f) drawRect(SolarYellow, Offset(x, line), Size(bar, d), alpha = alpha)
                drawRect(colors[i], Offset(x, stripTop), Size(slot, strip), alpha = alpha)
                if (i == shown) drawMarker(x + bar / 2, stripTop + strip + 3.dp.toPx())
            }
            drawLine(Outline, Offset(0f, line), Offset(size.width, line), 1.dp.toPx())
        }
        HourLabels(halfHours, zoom, start)

        if (shown != null) {
            BarDetails(
                bar = bars[shown],
                tariff = tariff,
                hourly = hourly,
                onPrevious = if (shown > 0) ({ pick(shown - 1) }) else null,
                onNext = if (shown < n - 1) ({ pick(shown + 1) }) else null,
                onClose = { picked = null },
            )
        } else {
            Text(
                if (hourly) "Tap a bar for its details · zoom in for half hours"
                else "Tap a bar for its details · pinch or use the buttons to zoom",
                fontSize = 12.sp,
                color = OnSurfaceVariant,
            )
        }
    }
}

private const val MAX_ZOOM = 8f
/** From this zoom the day chart shows half hours; below it, hours. */
private const val HALF_HOURS_FROM = 2f
/** The picked bar's column, behind it. */
private val PICKED = Color.White.copy(alpha = 0.13f)
/** The other bars while one is picked. */
private const val DIMMED = 0.38f

/** A small triangle under the picked bar, pointing up at it. */
private fun DrawScope.drawMarker(centerX: Float, top: Float) {
    val half = 5.dp.toPx()
    val path = Path().apply {
        moveTo(centerX, top)
        lineTo(centerX + half, top + 6.dp.toPx())
        lineTo(centerX - half, top + 6.dp.toPx())
        close()
    }
    drawPath(path, OnSurface)
}

/** A details card's title between previous and next buttons, then a close button. */
@Composable
private fun DetailsHeader(
    previousLabel: String,
    nextLabel: String,
    onPrevious: (() -> Unit)?,
    onNext: (() -> Unit)?,
    onClose: () -> Unit,
    title: @Composable RowScope.() -> Unit,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = { onPrevious?.invoke() }, enabled = onPrevious != null) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, contentDescription = previousLabel)
        }
        Row(
            Modifier.weight(1f),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
            content = title,
        )
        IconButton(onClick = { onNext?.invoke() }, enabled = onNext != null) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = nextLabel)
        }
        IconButton(onClick = onClose) { Icon(Icons.Filled.Close, contentDescription = "Close the details") }
    }
}

/** One hour or half hour, picked on the chart: its window and price, and what was bought, sold and used, in kWh and euro. */
@Composable
private fun BarDetails(
    bar: Bar,
    tariff: Tariff,
    hourly: Boolean,
    onPrevious: (() -> Unit)?,
    onNext: (() -> Unit)?,
    onClose: () -> Unit,
) {
    val band = tariff.bands.firstOrNull { it.id == bar.band }
    val used = bar.usedKwh
    Surface(shape = RoundedCornerShape(16.dp), color = SurfaceContainerHigh, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(start = 4.dp, end = 4.dp, top = 4.dp, bottom = 12.dp)) {
            DetailsHeader(
                previousLabel = if (hourly) "Previous hour" else "Previous half hour",
                nextLabel = if (hourly) "Next hour" else "Next half hour",
                onPrevious = onPrevious,
                onNext = onNext,
                onClose = onClose,
            ) {
                ColorDot(bandColor(bar.band), 10.dp)
                Spacer(Modifier.width(8.dp))
                Text(
                    "${bar.start}–${bar.end} · ${band?.name ?: bar.band}" + (band?.let { " · ${trimCents(it.centsPerKwh)}c" } ?: ""),
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp,
                    textAlign = TextAlign.Center,
                )
            }
            Column(Modifier.padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                DetailRow("Bought", bar.boughtKwh, bar.boughtEur, OnSurface)
                DetailRow("Sold", bar.soldKwh, bar.soldEur, SolarYellow)
                DetailRow("House used", used, band?.let { used * it.centsPerKwh / 100 }, OnSurfaceVariant)
                if (used > bar.boughtKwh + 0.005) {
                    Text(
                        "${kwh(used - bar.boughtKwh)} kWh of it came from the battery or solar",
                        fontSize = 12.sp,
                        color = OnSurfaceVariant,
                    )
                } else if (bar.boughtKwh > used + 0.005) {
                    Text(
                        "${kwh(bar.boughtKwh - used)} kWh more was bought than used: it went into the battery",
                        fontSize = 12.sp,
                        color = OnSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun DetailRow(label: String, kwhValue: Double, eurValue: Double?, color: Color, dot: Color? = null) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
            if (dot != null) {
                ColorDot(dot, 8.dp)
                Spacer(Modifier.width(6.dp))
            }
            Text(label, fontSize = 13.sp, color = OnSurfaceVariant)
        }
        Text("${kwh(kwhValue)} kWh", fontSize = 15.sp, fontWeight = FontWeight.ExtraBold, color = color)
        if (eurValue != null) {
            Text(
                euro(eurValue),
                fontSize = 13.sp,
                color = OnSurfaceVariant,
                textAlign = TextAlign.End,
                modifier = Modifier.width(64.dp),
            )
        } else {
            Spacer(Modifier.width(64.dp))  // the kWh stay in line with the rows above
        }
    }
}

/** The hours under the half hour each starts: every 4 hours, every 2 from 2x, every hour from 4x. */
@Composable
private fun HourLabels(halfHours: List<HalfHour>, zoom: Float, start: Float) {
    val n = halfHours.size
    val every = when {
        zoom >= 4f -> 1
        zoom >= 2f -> 2
        else -> 4
    }
    val labels = buildList<Pair<Float, String>> {
        if (n == 0) return@buildList
        val seen = mutableSetOf<String>()
        halfHours.forEachIndexed { i, h ->
            val hh = h.start.substringBefore(":")
            val hour = hh.toIntOrNull()
            if (hour != null && h.start.endsWith(":00") && hour % every == 0 && seen.add(hh)) {
                val at = (i.toFloat() / n - start) * zoom
                if (at in -0.001f..1.001f) add(at to hh)
            }
        }
        val end = (1f - start) * zoom
        if (end <= 1.001f) add(end to "24")
    }
    AxisLabels(labels)
}

/** Labels under a chart, each centred on its place (a fraction of the width) and kept inside the edges. */
@Composable
private fun AxisLabels(labels: List<Pair<Float, String>>) {
    Layout(
        content = { labels.forEach { Text(it.second, fontSize = 11.sp, color = OnSurfaceVariant) } },
        modifier = Modifier.fillMaxWidth(),
    ) { measurables, constraints ->
        val placeables = measurables.map { it.measure(constraints.copy(minWidth = 0)) }
        val width = constraints.maxWidth
        layout(width, placeables.maxOfOrNull { it.height } ?: 0) {
            placeables.forEachIndexed { i, p ->
                val x = (labels[i].first * width - p.width / 2f).roundToInt().coerceIn(0, maxOf(0, width - p.width))
                p.place(x, 0)
            }
        }
    }
}

// ------------------------------------------------------------------
// Month view
// ------------------------------------------------------------------

/** The chosen month with a bar per day, what it bought by price, and the months. */
@Composable
private fun MonthView(
    state: MonthsState,
    selectedMonth: String?,
    inEuro: Boolean,
    shownBands: Set<String>,
    onSelectMonth: (String) -> Unit,
    onToggleBand: (String) -> Unit,
    onOpenDay: (String) -> Unit,
    onRetry: () -> Unit,
) {
    val report = state.report
    if (report == null) {
        Pending(state.error, onRetry)
        return
    }
    val months = report.months
    if (months.isEmpty()) {
        Text("No readings yet", color = OnSurfaceVariant, modifier = Modifier.padding(horizontal = 16.dp))
        return
    }
    val index = months.indexOfFirst { it.month == selectedMonth }.takeIf { it >= 0 } ?: months.lastIndex
    val month = months[index]

    MonthCard(
        month = month,
        tariff = report.tariff,
        inEuro = inEuro,
        onPrevious = if (index > 0) ({ onSelectMonth(months[index - 1].month) }) else null,
        onNext = if (index < months.lastIndex) ({ onSelectMonth(months[index + 1].month) }) else null,
        onOpenDay = onOpenDay,
    )

    BandsCard(bought = month.bought, tariff = report.tariff, inEuro = inEuro)

    PeriodsCard(
        title = "Months",
        hint = if (inEuro) "€ bought · tap a month" else "kWh bought · tap a month",
        rows = months.map { Period(monthShort(it.month), it.bought, it.measuredHours > 0, monthNote(it)) },
        tariff = report.tariff,
        inEuro = inEuro,
        shownBands = shownBands,
        selectedIndex = index,
        labelWidth = 56.dp,
        onToggleBand = onToggleBand,
        onSelect = { onSelectMonth(months[it].month) },
    )

    Footer(report.tariff, state.error)
}

private fun monthLabel(month: String): String {
    val m = YearMonth.parse(month)
    return if (m == YearMonth.now(DUBLIN)) "${m.format(MONTH_LABEL)} (so far)" else m.format(MONTH_LABEL)
}

/** "Oct", or "Oct 25" for another year. */
private fun monthShort(month: String): String {
    val m = YearMonth.parse(month)
    return m.format(if (m.year == YearMonth.now(DUBLIN).year) MONTH_SHORT else MONTH_SHORT_YEAR)
}

/** Why a month's numbers are not a whole month, or null: days without readings at its start, or here and there. */
private fun monthNote(month: UsageMonth): String? {
    val days = month.days
    val read = days.count { it.measuredHours > 0 }
    if (read == days.size || read == 0) return null
    val first = days.indexOfFirst { it.measuredHours > 0 }
    return if (days.drop(first).all { it.measuredHours > 0 }) {
        "Readings from ${LocalDate.parse(days[first].date).format(DAY_MONTH)}"
    } else {
        "Partial: $read of ${days.size} days with readings"
    }
}

@Composable
private fun MonthCard(
    month: UsageMonth,
    tariff: Tariff,
    inEuro: Boolean,
    onPrevious: (() -> Unit)?,
    onNext: (() -> Unit)?,
    onOpenDay: (String) -> Unit,
) {
    Surface(shape = RoundedCornerShape(24.dp), color = SurfaceContainerLow, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            CardHeader(monthLabel(month.month), "Previous month", "Next month", onPrevious, onNext)

            Totals(
                net = month.netEur,
                bought = month.boughtTotal,
                sold = month.sold,
                usedKwh = month.usedKwh,
                measured = month.measuredHours > 0.0,
                note = monthNote(month),
                tariff = tariff,
                inEuro = inEuro,
            )

            HorizontalDivider(color = OutlineVariant)

            key(month.month) { DailyChart(month, tariff, inEuro, onOpenDay) }
        }
    }
}

/**
 * The month's days, a bar each: bought above the line, stacked in the band colours, sold below in yellow, at one
 * scale. In kWh, an outline behind of what the house used from any source; in euro there is none, as a day's use
 * has no single price. Every day of the month has its place, so this month's days so far keep theirs. A tap picks
 * a day, and its details' arrows step along.
 */
@Composable
private fun DailyChart(month: UsageMonth, tariff: Tariff, inEuro: Boolean, onOpenDay: (String) -> Unit) {
    val days = month.days
    val n = days.size
    val places = YearMonth.parse(month.month).lengthOfMonth().coerceAtLeast(n)
    val bandIds = tariff.bands.map { it.id }
    val colors = bandIds.map { bandColor(it) }
    val up = days.map { day -> bandIds.map { (day.bought[it] ?: Energy()).amount(inEuro) } }
    val used = days.map { if (inEuro) 0.0 else it.usedKwh ?: 0.0 }
    val down = days.map { it.sold.amount(inEuro) }
    val maxUp = (up.map { it.sum() } + used).maxOrNull()?.coerceAtLeast(0.0) ?: 0.0
    val maxDown = down.maxOrNull()?.coerceAtLeast(0.0) ?: 0.0
    val description = if (inEuro) {
        "Month chart: most bought in a day ${euro(maxUp)}, most sold ${euro(maxDown)}"
    } else {
        "Month chart: most bought in a day ${kwh(maxUp)} kWh, most sold ${kwh(maxDown)} kWh"
    }
    var picked by remember { mutableStateOf<Int?>(null) }
    val shown = picked?.takeIf { it < n }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Column {
            Text("Every day", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Text(if (inEuro) "euro" else "kWh", fontSize = 12.sp, color = OnSurfaceVariant)
        }
        ChartLegend(tariff, if (inEuro) null else "House used")

        Canvas(
            Modifier
                .fillMaxWidth()
                .height(192.dp)
                .semantics { contentDescription = description }
                .pointerInput(n, places) {
                    detectTapGestures { position ->
                        val i = (position.x / size.width * places).toInt()
                        if (i in 0 until n) picked = if (picked == i) null else i
                    }
                },
        ) {
            val chart = 180.dp.toPx()
            val slot = size.width / places  // px per day
            val gap = if (slot > 6.dp.toPx()) 2.dp.toPx() else 1.dp.toPx()
            val bar = (slot - gap).coerceAtLeast(1f)
            val total = maxUp + maxDown
            val scale = if (total > 0) chart / total else 0.0
            val line = if (total > 0) (maxUp * scale).toFloat() else chart / 2
            val minBar = 1.5.dp.toPx()
            val stroke = 1.dp.toPx()
            val corner = CornerRadius(2.dp.toPx())
            for (i in 0 until n) {
                val x = i * slot + gap / 2
                val alpha = if (shown != null && i != shown) DIMMED else 1f
                if (i == shown) drawRect(PICKED, Offset(i * slot, 0f), Size(slot, chart))
                val u = if (used[i] > 0) maxOf((used[i] * scale).toFloat(), minBar) else 0f
                if (u > 0f) {
                    drawRoundRect(USED_FILL, Offset(x, line - u), Size(bar, u), corner, alpha = alpha)
                    drawRoundRect(
                        USED_STROKE,
                        Offset(x + stroke / 2, line - u + stroke / 2),
                        Size((bar - stroke).coerceAtLeast(0f), (u - stroke).coerceAtLeast(0f)),
                        corner,
                        style = Stroke(stroke),
                        alpha = alpha,
                    )
                }
                // Bought: the bands stacked up from the line in the tariff's order
                val sum = up[i].sum()
                if (sum > 0) {
                    val height = maxOf((sum * scale).toFloat(), minBar)
                    var top = line
                    up[i].forEachIndexed { b, value ->
                        val h = (value / sum * height).toFloat()
                        if (h > 0f) {
                            drawRect(colors[b], Offset(x, top - h), Size(bar, h), alpha = alpha)
                            top -= h
                        }
                    }
                }
                val d = if (down[i] > 0) maxOf((down[i] * scale).toFloat(), minBar) else 0f
                if (d > 0f) drawRect(SolarYellow, Offset(x, line), Size(bar, d), alpha = alpha)
                if (i == shown) drawMarker(x + bar / 2, chart + 4.dp.toPx())
            }
            drawLine(Outline, Offset(0f, line), Offset(size.width, line), 1.dp.toPx())
        }
        AxisLabels(listOf(1, 8, 15, 22, 29).filter { it <= places }.map { (it - 0.5f) / places to "$it" })

        if (shown != null) {
            DayDetails(
                day = days[shown],
                tariff = tariff,
                onPrevious = if (shown > 0) ({ picked = shown - 1 }) else null,
                onNext = if (shown < n - 1) ({ picked = shown + 1 }) else null,
                onClose = { picked = null },
                onOpen = { onOpenDay(days[shown].date) },
            )
        } else {
            Text("Tap a day for its details", fontSize = 12.sp, color = OnSurfaceVariant)
        }
    }
}

/** One day, picked on the month chart: what it bought in each band, sold and used, its net, and a way into it. */
@Composable
private fun DayDetails(
    day: UsageDay,
    tariff: Tariff,
    onPrevious: (() -> Unit)?,
    onNext: (() -> Unit)?,
    onClose: () -> Unit,
    onOpen: () -> Unit,
) {
    Surface(shape = RoundedCornerShape(16.dp), color = SurfaceContainerHigh, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(start = 4.dp, end = 4.dp, top = 4.dp, bottom = 4.dp)) {
            DetailsHeader("Previous day", "Next day", onPrevious, onNext, onClose) {
                Text(dayLabel(day.date), fontWeight = FontWeight.Bold, fontSize = 14.sp, textAlign = TextAlign.Center)
            }
            Column(Modifier.padding(horizontal = 14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (day.measuredHours <= 0.0) {
                    Text("No readings", fontSize = 13.sp, color = OnSurfaceVariant)
                } else {
                    tariff.bands.forEach { band ->
                        val energy = day.bought[band.id] ?: Energy()
                        DetailRow(
                            "${band.name} · ${trimCents(band.centsPerKwh)}c",
                            energy.kwh,
                            energy.eur,
                            OnSurface,
                            dot = bandColor(band.id),
                        )
                    }
                    DetailRow("Sold", day.sold.kwh, day.sold.eur, SolarYellow)
                    day.usedKwh?.let { DetailRow("House used", it, null, OnSurfaceVariant) }
                    val earned = day.netEur < 0
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
                        Text(
                            if (earned) "You earned" else "You spent",
                            fontSize = 13.sp,
                            color = OnSurfaceVariant,
                            modifier = Modifier.weight(1f),
                        )
                        Text(
                            euro(abs(day.netEur)),
                            fontSize = 15.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = if (earned) BatteryGreen else OnSurface,
                        )
                    }
                    dayNote(day)?.let { Text(it, fontSize = 12.sp, color = OnSurfaceVariant) }
                }
            }
            TextButton(onClick = onOpen, modifier = Modifier.align(Alignment.End).heightIn(min = 44.dp)) {
                Text("Open day", fontWeight = FontWeight.Bold)
                Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = null)
            }
        }
    }
}

// ------------------------------------------------------------------
// What the day or month bought, by price
// ------------------------------------------------------------------

@Composable
private fun BandsCard(bought: Map<String, Energy>, tariff: Tariff, inEuro: Boolean) {
    val values = tariff.bands.map { (bought[it.id] ?: Energy()).amount(inEuro) }
    val total = values.sum()
    val top = values.maxOrNull()?.takeIf { it > 0 } ?: 1.0
    val share = { v: Double -> if (total > 0) "${(v / total * 100).roundToInt()}%" else "–" }

    Surface(shape = RoundedCornerShape(24.dp), color = SurfaceContainerLow, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("What you bought, by price", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)

            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                val ringLabel = tariff.bands.zip(values).joinToString { (b, v) -> "${b.name} ${share(v)}" }
                Box(
                    Modifier.size(128.dp).semantics { contentDescription = ringLabel },
                    contentAlignment = Alignment.Center,
                ) {
                    val colors = tariff.bands.map { bandColor(it.id) }
                    Canvas(Modifier.fillMaxSize()) {
                        val stroke = 22.dp.toPx()
                        val inset = stroke / 2
                        val arcSize = Size(size.width - stroke, size.height - stroke)
                        if (total <= 0) {
                            drawArc(SurfaceContainerHigh, 0f, 360f, false, Offset(inset, inset), arcSize, style = Stroke(stroke))
                        } else {
                            var start = -90f
                            values.forEachIndexed { i, v ->
                                val sweep = (v / total * 360).toFloat()
                                if (sweep > 0f) {
                                    drawArc(colors[i], start, sweep, false, Offset(inset, inset), arcSize, style = Stroke(stroke))
                                }
                                start += sweep
                            }
                        }
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            if (inEuro) euro(total) else kwh(total),
                            fontSize = 18.sp,
                            fontWeight = FontWeight.ExtraBold,
                        )
                        Text(if (inEuro) "bought" else "kWh bought", fontSize = 11.sp, color = OnSurfaceVariant)
                    }
                }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    tariff.bands.forEachIndexed { i, band ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            ColorDot(bandColor(band.id), 10.dp)
                            Spacer(Modifier.width(8.dp))
                            Text(band.name, fontWeight = FontWeight.Bold, fontSize = 14.sp, modifier = Modifier.weight(1f))
                            Text(share(values[i]), fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        }
                    }
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                tariff.bands.forEachIndexed { i, band ->
                    val energy = bought[band.id] ?: Energy()
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
                            Text(
                                "${band.name} ${band.hours.replace("-", "–")} · ${"%.2f".format(band.centsPerKwh)}c",
                                color = OnSurfaceVariant,
                                fontSize = 13.sp,
                                modifier = Modifier.weight(1f),
                            )
                            Text(
                                if (inEuro) euro(energy.eur) else "${kwh(energy.kwh)} kWh",
                                fontWeight = FontWeight.ExtraBold,
                                fontSize = 15.sp,
                            )
                        }
                        Box(
                            Modifier
                                .fillMaxWidth()
                                .height(8.dp)
                                .background(SurfaceContainerHigh, RoundedCornerShape(4.dp)),
                        ) {
                            val fraction = (values[i] / top).toFloat().coerceIn(0f, 1f)
                            if (fraction > 0f) {
                                Box(
                                    Modifier
                                        .fillMaxWidth(fraction)
                                        .fillMaxHeight()
                                        .background(bandColor(band.id), RoundedCornerShape(4.dp)),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ColorDot(color: Color, size: Dp) {
    Box(Modifier.size(size).background(color, RoundedCornerShape(size / 4)))
}

// ------------------------------------------------------------------
// The week or the months, by the windows picked
// ------------------------------------------------------------------

/** A row of the week or the month list: its label, what it bought by band, and why it is not whole (or null). */
private class Period(
    val label: String,
    val bought: Map<String, Energy>,
    val measured: Boolean,
    val note: String?,
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PeriodsCard(
    title: String,
    hint: String,
    rows: List<Period>,
    tariff: Tariff,
    inEuro: Boolean,
    shownBands: Set<String>,
    selectedIndex: Int,
    labelWidth: Dp,
    onToggleBand: (String) -> Unit,
    onSelect: (Int) -> Unit,
    onToday: (() -> Unit)? = null,
) {
    val picked = tariff.bands.filter { it.id in shownBands }
    val totalOf = { row: Period -> picked.sumOf { (row.bought[it.id] ?: Energy()).amount(inEuro) } }
    val max = rows.maxOfOrNull(totalOf)?.takeIf { it > 0 } ?: 1.0

    Surface(shape = RoundedCornerShape(24.dp), color = SurfaceContainerLow, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 10.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                // Days away from today: a way back to them, instead of the hint
                if (onToday != null) {
                    TextButton(onClick = onToday, modifier = Modifier.heightIn(min = 44.dp)) {
                        Text("Back to today", fontWeight = FontWeight.Bold)
                    }
                } else {
                    Text(hint, fontSize = 12.sp, color = OnSurfaceVariant)
                }
            }

            FlowRow(
                Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                tariff.bands.forEach { band ->
                    val on = band.id in shownBands
                    FilterChip(
                        selected = on,
                        onClick = { onToggleBand(band.id) },
                        label = { Text(band.name, fontWeight = FontWeight.Bold) },
                        leadingIcon = { ColorDot(bandColor(band.id).copy(alpha = if (on) 1f else 0.3f), 10.dp) },
                        modifier = Modifier.heightIn(min = 44.dp),
                        colors = FilterChipDefaults.filterChipColors(
                            containerColor = Color.Transparent,
                            labelColor = OnSurfaceVariant,
                            selectedContainerColor = SurfaceContainerHigh,
                            selectedLabelColor = OnSurface,
                        ),
                        border = FilterChipDefaults.filterChipBorder(
                            enabled = true,
                            selected = on,
                            borderColor = OutlineVariant,
                            selectedBorderColor = Outline,
                        ),
                    )
                }
            }

            // Newest first: today (this month), then back
            for (i in rows.indices.reversed()) {
                PeriodRow(
                    row = rows[i],
                    picked = picked.map { it.id },
                    inEuro = inEuro,
                    total = totalOf(rows[i]),
                    max = max,
                    selected = i == selectedIndex,
                    labelWidth = labelWidth,
                    onClick = { onSelect(i) },
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PeriodRow(
    row: Period,
    picked: List<String>,
    inEuro: Boolean,
    total: Double,
    max: Double,
    selected: Boolean,
    labelWidth: Dp,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(12.dp),
        color = if (selected) SurfaceContainerHigh else Color.Transparent,
        border = if (selected) BorderStroke(1.dp, Outline) else null,
        modifier = Modifier.fillMaxWidth().heightIn(min = 44.dp),
    ) {
        Column(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(row.label, fontWeight = FontWeight.Bold, fontSize = 13.sp, modifier = Modifier.width(labelWidth))
                Box(
                    Modifier
                        .weight(1f)
                        .height(10.dp)
                        .clip(RoundedCornerShape(5.dp))
                        .background(SurfaceContainerHigh),
                ) {
                    val fraction = (total / max).toFloat().coerceIn(0f, 1f)
                    if (fraction > 0f) {
                        Row(
                            Modifier
                                .fillMaxWidth(fraction)
                                .fillMaxHeight(),
                            horizontalArrangement = Arrangement.spacedBy(1.dp),
                        ) {
                            picked.forEach { id ->
                                val v = (row.bought[id] ?: Energy()).amount(inEuro)
                                if (v > 0) {
                                    Box(
                                        Modifier
                                            .weight((v / total).toFloat())
                                            .fillMaxHeight()
                                            .background(bandColor(id)),
                                    )
                                }
                            }
                        }
                    }
                }
                Text(
                    if (inEuro) euro(total) else kwh(total),
                    fontWeight = FontWeight.Bold,
                    fontSize = 13.sp,
                    textAlign = TextAlign.End,
                    modifier = Modifier.width(72.dp),
                )
            }
            // One row under the bar: each picked window's value
            if (!row.measured) {
                Text("No readings", fontSize = 12.sp, color = OnSurfaceVariant, modifier = Modifier.padding(start = labelWidth))
            } else {
                FlowRow(
                    Modifier.padding(start = labelWidth),
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    picked.forEach { id ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            ColorDot(bandColor(id), 8.dp)
                            Spacer(Modifier.width(5.dp))
                            Text(
                                (row.bought[id] ?: Energy()).shown(inEuro),
                                fontSize = 12.sp,
                                color = OnSurfaceVariant,
                            )
                        }
                    }
                    if (row.note != null) {
                        Text(row.note, fontSize = 12.sp, color = OnSurfaceVariant)
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------
// Error
// ------------------------------------------------------------------

@Composable
private fun UsageError(error: String, onRetry: () -> Unit) {
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = MaterialTheme.colorScheme.errorContainer,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("Could not load the electricity report: $error", style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(16.dp))
            OutlinedButton(onClick = onRetry) { Text("Retry") }
        }
    }
}
