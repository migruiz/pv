package ovh.tenjo.pv.ui.theme

import android.app.Activity
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val SolarDarkColorScheme = darkColorScheme(
    primary = SolarGreen,
    onPrimary = OnSolarGreen,
    primaryContainer = SolarGreenContainer,
    onPrimaryContainer = OnSolarGreenContainer,
    secondary = EnergyOrange,
    onSecondary = OnEnergyOrange,
    secondaryContainer = EnergyOrangeContainer,
    tertiary = GridBlue,
    onTertiary = OnGridBlue,
    tertiaryContainer = GridBlueContainer,
    surface = SurfaceDark,
    surfaceDim = SurfaceDark,
    surfaceBright = SurfaceBright,
    surfaceContainerLowest = SurfaceContainerLowest,
    surfaceContainerLow = SurfaceContainerLow,
    surfaceContainer = SurfaceContainer,
    surfaceContainerHigh = SurfaceContainerHigh,
    surfaceContainerHighest = SurfaceContainerHighest,
    onSurface = OnSurface,
    onSurfaceVariant = OnSurfaceVariant,
    outline = Outline,
    outlineVariant = OutlineVariant,
    error = ErrorRed,
    errorContainer = ErrorContainer,
)

@Composable
fun PVManagerTheme(content: @Composable () -> Unit) {
    val colorScheme = SolarDarkColorScheme
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            @Suppress("DEPRECATION")
            window.statusBarColor = colorScheme.surface.toArgb()
            @Suppress("DEPRECATION")
            window.navigationBarColor = colorScheme.surface.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = Typography,
        content = content,
    )
}
