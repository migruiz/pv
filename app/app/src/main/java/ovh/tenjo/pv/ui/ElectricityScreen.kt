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
import androidx.compose.ui.geometry.isSpecified
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ovh.tenjo.pv.SolarViewModel
import ovh.tenjo.pv.api.Energy
import ovh.tenjo.pv.api.HalfHour
import ovh.tenjo.pv.api.Tariff
import ovh.tenjo.pv.api.UsageDay
import ovh.tenjo.pv.ui.theme.*
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

private val DUBLIN = ZoneId.of("Europe/Dublin")
private val DAY_LABEL = DateTimeFormatter.ofPattern("EEE d MMM", Locale.ENGLISH)
private val DAY_SHORT = DateTimeFormatter.ofPattern("EEE", Locale.ENGLISH)

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
 * Electricity bought and sold, by the tariff's price windows: the chosen day (net, bought, sold),
 * what it bought at each price, and the week with the windows picked by the chips.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ElectricityScreen(
    viewModel: SolarViewModel,
    onBack: () -> Unit,
) {
    val state by viewModel.usage.collectAsState()

    DisposableEffect(Unit) {
        viewModel.openUsage()
        onDispose { viewModel.closeUsage() }
    }

    var inEuro by remember { mutableStateOf(true) }
    // null: the latest day (today), so the screen follows midnight
    var selectedDate by remember { mutableStateOf<String?>(null) }
    // null: every band
    var shownBands by remember { mutableStateOf<Set<String>?>(null) }

    val report = state.report

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Electricity")
                        if (report != null) {
                            Text(
                                report.tariff.name,
                                style = MaterialTheme.typography.labelMedium,
                                color = OnSurfaceVariant,
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    UnitToggle(inEuro = inEuro, onChange = { inEuro = it })
                    Spacer(Modifier.width(12.dp))
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
            if (report == null || report.days.isEmpty()) {
                if (state.error != null) {
                    UsageError(state.error!!) { viewModel.loadUsage() }
                } else {
                    Box(Modifier.fillMaxWidth().height(300.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                    }
                }
                return@Column
            }

            val days = report.days
            val index = days.indexOfFirst { it.date == selectedDate }.takeIf { it >= 0 } ?: days.lastIndex
            val day = days[index]
            val bands = shownBands ?: report.tariff.bands.map { it.id }.toSet()

            DayCard(
                day = day,
                tariff = report.tariff,
                inEuro = inEuro,
                onPrevious = if (index > 0) ({ selectedDate = days[index - 1].date }) else null,
                onNext = if (index < days.lastIndex) ({ selectedDate = days[index + 1].date }) else null,
            )

            BandsCard(day = day, tariff = report.tariff, inEuro = inEuro)

            WeekCard(
                days = days,
                tariff = report.tariff,
                inEuro = inEuro,
                shownBands = bands,
                selectedIndex = index,
                onToggleBand = { id ->
                    val next = if (id in bands) bands - id else bands + id
                    if (next.isNotEmpty()) shownBands = next  // at least one stays on
                },
                onSelectDay = { selectedDate = days[it].date },
            )

            Text(
                "Standing charge (${euro(report.tariff.standingChargeEurPerDay)} a day) not included.",
                style = MaterialTheme.typography.bodySmall,
                color = OnSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp),
            )

            if (state.error != null) {
                Text(
                    "Could not refresh: ${state.error}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(horizontal = 16.dp),
                )
            }
        }
    }
}

// ------------------------------------------------------------------
// Header
// ------------------------------------------------------------------

@Composable
private fun UnitToggle(inEuro: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier
            .background(SurfaceContainerLow, RoundedCornerShape(50))
            .padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        UnitButton("kWh", selected = !inEuro) { onChange(false) }
        UnitButton("€", selected = inEuro) { onChange(true) }
    }
}

@Composable
private fun UnitButton(label: String, selected: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(50),
        color = if (selected) SolarYellow else Color.Transparent,
        contentColor = if (selected) OnSolarYellow else OnSurfaceVariant,
        modifier = Modifier.heightIn(min = 36.dp).widthIn(min = 52.dp),
    ) {
        Box(Modifier.padding(horizontal = 14.dp, vertical = 8.dp), contentAlignment = Alignment.Center) {
            Text(label, fontWeight = if (selected) FontWeight.ExtraBold else FontWeight.Bold, fontSize = 14.sp)
        }
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
            // -- Header: the day, and its net, bought and sold --
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                DayArrow(Icons.AutoMirrored.Filled.KeyboardArrowLeft, "Previous day", onPrevious)
                Text(
                    dayLabel(day.date),
                    modifier = Modifier.weight(1f),
                    textAlign = TextAlign.Center,
                    style = MaterialTheme.typography.titleMedium,
                    color = OnSurfaceVariant,
                )
                DayArrow(Icons.AutoMirrored.Filled.KeyboardArrowRight, "Next day", onNext)
            }

            Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                if (day.measuredHours <= 0.0) {
                    Text("No readings", style = MaterialTheme.typography.headlineMedium, color = OnSurfaceVariant)
                } else {
                    val earned = day.netEur < 0
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
                            if (inEuro) euro(abs(day.netEur)) else kwh(day.boughtTotal.kwh),
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
                        CompactValue("Bought", day.boughtTotal.shown(inEuro), inEuro, OnSurface)
                        CompactValue(
                            "Sold · ${trimCents(tariff.exportCentsPerKwh)}c",
                            day.sold.shown(inEuro),
                            inEuro,
                            SolarYellow,
                        )
                    }
                    // Whatever the source (grid, battery or solar): always kWh
                    day.usedKwh?.let { used ->
                        Spacer(Modifier.height(4.dp))
                        Text("House used ${kwh(used)} kWh", fontSize = 12.sp, color = OnSurfaceVariant)
                    }
                    val note = dayNote(day)
                    if (note != null) {
                        Spacer(Modifier.height(6.dp))
                        Text(note, style = MaterialTheme.typography.bodySmall, color = OnSurfaceVariant)
                    }
                }
            }

            HorizontalDivider(color = OutlineVariant)

            // -- Every half hour: bought above the line by price band, sold below, at one scale --
            key(day.date) { HalfHourChart(day.halfHours.orEmpty(), tariff, inEuro) }
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
private fun DayArrow(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, onClick: (() -> Unit)?) {
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
private fun HalfHourLegend(tariff: Tariff, inEuro: Boolean) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        tariff.bands.forEach { LegendItem(bandColor(it.id), it.name) }
        LegendItem(SolarYellow, "Sold (below the line)")
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(10.dp)
                    .background(USED_FILL, RoundedCornerShape(2.5.dp))
                    .border(1.dp, USED_STROKE, RoundedCornerShape(2.5.dp)),
            )
            Spacer(Modifier.width(6.dp))
            Text(
                if (inEuro) "House used, at that time's price" else "House used",
                fontSize = 12.sp,
                color = OnSurfaceVariant,
            )
        }
    }
}

/** The outline of what the house used, behind each half hour's bought bar. */
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

/**
 * The day's half hours: a title with zoom buttons, the legend, the chart, the hours and, for a tapped
 * half hour, its details. One bar per half hour: bought above the line in its band colour, sold below in
 * yellow, at one scale, then a strip of the band colours. Behind each bought bar, an outline of what the
 * house used from any source (in euro: at that half hour's price), so the hours the battery runs the house
 * still show their use. Pinch or the buttons zoom into the day (up to 8x), a sideways drag moves along it
 * once zoomed, a tap picks a half hour. Positions come from each entry index, so the 46 or 50 half hours of
 * a clock-change day still fill the width.
 */
@Composable
private fun HalfHourChart(halfHours: List<HalfHour>, tariff: Tariff, inEuro: Boolean) {
    val rates = tariff.bands.associate { it.id to it.centsPerKwh / 100 }
    val up = halfHours.map { if (inEuro) it.boughtEur else it.boughtKwh }
    val used = halfHours.map { h ->
        val kwh = h.usedKwh ?: 0.0
        if (inEuro) kwh * (rates[h.band] ?: 0.0) else kwh
    }
    val down = halfHours.map { if (inEuro) it.soldEur else it.soldKwh }
    val colors = halfHours.map { bandColor(it.band) }
    val maxUp = (up + used).maxOrNull()?.coerceAtLeast(0.0) ?: 0.0
    val maxDown = down.maxOrNull()?.coerceAtLeast(0.0) ?: 0.0
    val n = halfHours.size
    val description = if (inEuro) {
        "Half-hour chart: most bought in a half hour ${euro(maxUp)}, most sold ${euro(maxDown)}"
    } else {
        "Half-hour chart: most bought in a half hour ${kwh(maxUp)} kWh, most sold ${kwh(maxDown)} kWh"
    }

    // The visible part of the day: from `start` (a fraction of the day) for 1 / zoom of it
    var zoom by remember { mutableFloatStateOf(1f) }
    var start by remember { mutableFloatStateOf(0f) }
    var picked by remember { mutableStateOf<Int?>(null) }

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

    /** Where the buttons zoom around: the picked half hour if it is in view, else the middle. */
    fun focus(): Float {
        val i = picked ?: return 0.5f
        val at = ((i + 0.5f) / n - start) * zoom
        return if (at in 0f..1f) at else 0.5f
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Every half hour", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
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
        HalfHourLegend(tariff, inEuro)

        Canvas(
            Modifier
                .fillMaxWidth()
                .height(194.dp)
                .clipToBounds()
                .semantics { contentDescription = description }
                // Two fingers zoom (and move); once zoomed, one finger dragging sideways moves along the day.
                // Anything else is left alone, so the screen still scrolls up and down over the chart.
                .pointerInput(n) {
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
                .pointerInput(n) {
                    detectTapGestures { position ->
                        if (n == 0) return@detectTapGestures
                        val day = start + position.x / size.width / zoom
                        val i = (day * n).toInt().coerceIn(0, n - 1)
                        picked = if (picked == i) null else i
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
            val slot = size.width * zoom / n  // px per half hour
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
                if (i == picked) drawRect(PICKED, Offset(x - gap / 2, 0f), Size(slot, chart))
                // The house's use first, as a faint outline; the bought bar covers it where it is bigger
                val u = if (used[i] > 0) maxOf((used[i] * scale).toFloat(), minBar) else 0f
                if (u > 0f) {
                    drawRoundRect(USED_FILL, Offset(x, line - u), Size(bar, u), corner)
                    drawRoundRect(
                        USED_STROKE,
                        Offset(x + stroke / 2, line - u + stroke / 2),
                        Size((bar - stroke).coerceAtLeast(0f), (u - stroke).coerceAtLeast(0f)),
                        corner,
                        style = Stroke(stroke),
                    )
                }
                val h = if (up[i] > 0) maxOf((up[i] * scale).toFloat(), minBar) else 0f
                if (h > 0f) drawRect(colors[i], Offset(x, line - h), Size(bar, h))
                val d = if (down[i] > 0) maxOf((down[i] * scale).toFloat(), minBar) else 0f
                if (d > 0f) drawRect(SolarYellow, Offset(x, line), Size(bar, d))
                drawRect(colors[i], Offset(x, stripTop), Size(slot, strip))
            }
            drawLine(Outline, Offset(0f, line), Offset(size.width, line), 1.dp.toPx())
        }
        HourLabels(halfHours, zoom, start)

        val i = picked
        if (i != null && i < n) {
            HalfHourDetails(halfHours, i, tariff) { picked = null }
        } else {
            Text("Tap a bar for its details · pinch or use the buttons to zoom", fontSize = 12.sp, color = OnSurfaceVariant)
        }
    }
}

private const val MAX_ZOOM = 8f
private val PICKED = Color.White.copy(alpha = 0.10f)

/** One half hour, picked on the chart: its window and price, and what was bought, sold and used, in kWh and euro. */
@Composable
private fun HalfHourDetails(halfHours: List<HalfHour>, index: Int, tariff: Tariff, onClose: () -> Unit) {
    val h = halfHours[index]
    val end = halfHours.getOrNull(index + 1)?.start ?: "24:00"
    val band = tariff.bands.firstOrNull { it.id == h.band }
    val used = h.usedKwh ?: 0.0
    Surface(shape = RoundedCornerShape(16.dp), color = SurfaceContainerHigh, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(start = 14.dp, end = 4.dp, top = 4.dp, bottom = 12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                ColorDot(bandColor(h.band), 10.dp)
                Spacer(Modifier.width(8.dp))
                Text(
                    "${h.start}–$end · ${band?.name ?: h.band}" + (band?.let { " · ${trimCents(it.centsPerKwh)}c" } ?: ""),
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp,
                    modifier = Modifier.weight(1f),
                )
                IconButton(onClick = onClose) { Icon(Icons.Filled.Close, contentDescription = "Close the details") }
            }
            Column(Modifier.padding(end = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                DetailRow("Bought", h.boughtKwh, h.boughtEur, OnSurface)
                DetailRow("Sold", h.soldKwh, h.soldEur, SolarYellow)
                DetailRow("House used", used, band?.let { used * it.centsPerKwh / 100 }, OnSurfaceVariant)
                if (used > h.boughtKwh + 0.005) {
                    Text(
                        "${kwh(used - h.boughtKwh)} kWh of it came from the battery or solar",
                        fontSize = 12.sp,
                        color = OnSurfaceVariant,
                    )
                } else if (h.boughtKwh > used + 0.005) {
                    Text(
                        "${kwh(h.boughtKwh - used)} kWh more was bought than used: it went into the battery",
                        fontSize = 12.sp,
                        color = OnSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun DetailRow(label: String, kwhValue: Double, eurValue: Double?, color: Color) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
        Text(label, fontSize = 13.sp, color = OnSurfaceVariant, modifier = Modifier.weight(1f))
        Text("${kwh(kwhValue)} kWh", fontSize = 15.sp, fontWeight = FontWeight.ExtraBold, color = color)
        if (eurValue != null) {
            Text(
                euro(eurValue),
                fontSize = 13.sp,
                color = OnSurfaceVariant,
                textAlign = TextAlign.End,
                modifier = Modifier.width(64.dp),
            )
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
// What the day bought, by price
// ------------------------------------------------------------------

@Composable
private fun BandsCard(day: UsageDay, tariff: Tariff, inEuro: Boolean) {
    val values = tariff.bands.map { (day.bought[it.id] ?: Energy()).amount(inEuro) }
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
                    val energy = day.bought[band.id] ?: Energy()
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
private fun ColorDot(color: Color, size: androidx.compose.ui.unit.Dp) {
    Box(Modifier.size(size).background(color, RoundedCornerShape(size / 4)))
}

// ------------------------------------------------------------------
// The week, by the windows picked
// ------------------------------------------------------------------

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun WeekCard(
    days: List<UsageDay>,
    tariff: Tariff,
    inEuro: Boolean,
    shownBands: Set<String>,
    selectedIndex: Int,
    onToggleBand: (String) -> Unit,
    onSelectDay: (Int) -> Unit,
) {
    val picked = tariff.bands.filter { it.id in shownBands }
    val totalOf = { day: UsageDay -> picked.sumOf { (day.bought[it.id] ?: Energy()).amount(inEuro) } }
    val max = days.maxOfOrNull(totalOf)?.takeIf { it > 0 } ?: 1.0

    Surface(shape = RoundedCornerShape(24.dp), color = SurfaceContainerLow, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 10.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 8.dp),
                verticalAlignment = Alignment.Bottom,
            ) {
                Text(
                    if (days.size == 7) "This week" else "Last ${days.size} days",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                Text(
                    if (inEuro) "€ bought · tap a day" else "kWh bought · tap a day",
                    fontSize = 12.sp,
                    color = OnSurfaceVariant,
                )
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

            // Newest first: today, yesterday, ...
            for (i in days.indices.reversed()) {
                val day = days[i]
                WeekRow(
                    day = day,
                    picked = picked.map { it.id },
                    inEuro = inEuro,
                    total = totalOf(day),
                    max = max,
                    selected = i == selectedIndex,
                    onClick = { onSelectDay(i) },
                )
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun WeekRow(
    day: UsageDay,
    picked: List<String>,
    inEuro: Boolean,
    total: Double,
    max: Double,
    selected: Boolean,
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
                Text(dayShort(day.date), fontWeight = FontWeight.Bold, fontSize = 13.sp, modifier = Modifier.width(44.dp))
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
                                val v = (day.bought[id] ?: Energy()).amount(inEuro)
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
            if (day.measuredHours <= 0.0) {
                Text("No readings", fontSize = 12.sp, color = OnSurfaceVariant, modifier = Modifier.padding(start = 44.dp))
            } else {
                FlowRow(
                    Modifier.padding(start = 44.dp),
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    picked.forEach { id ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            ColorDot(bandColor(id), 8.dp)
                            Spacer(Modifier.width(5.dp))
                            Text(
                                (day.bought[id] ?: Energy()).shown(inEuro),
                                fontSize = 12.sp,
                                color = OnSurfaceVariant,
                            )
                        }
                    }
                    val note = dayNote(day)
                    if (note != null) {
                        Text(note, fontSize = 12.sp, color = OnSurfaceVariant)
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
