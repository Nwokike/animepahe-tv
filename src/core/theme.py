import flet as ft


# The 3-way theme (house pattern): token <-> ThemeMode in ONE place each,
# so the settings picker, the persisted name, and the header cycle cannot
# drift apart.
THEME_MODES = {
    "dark": ft.ThemeMode.DARK,
    "light": ft.ThemeMode.LIGHT,
    "system": ft.ThemeMode.SYSTEM,
}
THEME_TOKENS = {mode: token for token, mode in THEME_MODES.items()}
# The header toggle cycles in this order.
THEME_ORDER = (ft.ThemeMode.DARK, ft.ThemeMode.LIGHT, ft.ThemeMode.SYSTEM)


def mode_for_token(token: str) -> ft.ThemeMode:
    """The stored token's mode; unknown tokens fall back to SYSTEM."""
    return THEME_MODES.get(token, ft.ThemeMode.SYSTEM)


def token_for_mode(mode) -> str:
    """The persisted token for a mode; unknown modes fall back to system."""
    return THEME_TOKENS.get(mode, "system")


def next_theme_mode(mode) -> ft.ThemeMode:
    """3-way cycle: DARK -> LIGHT -> SYSTEM."""
    if mode not in THEME_ORDER:
        return ft.ThemeMode.SYSTEM
    return THEME_ORDER[(THEME_ORDER.index(mode) + 1) % len(THEME_ORDER)]


class AppColors:
    # Animepahe-TV custom premium palette
    PRIMARY = "#F43F5E"  # Rose 500
    SECONDARY = "#0EA5E9"  # Sky 500
    SUCCESS = "#10B981"  # Emerald 500
    WARNING = "#F59E0B"  # Amber 500
    ERROR = "#EF4444"  # Red 500

    # Dark Mode
    DARK_BG = "#0B0F19"
    DARK_SURFACE = "#111827"
    DARK_SURFACE_VARIANT = "#1F2937"
    DARK_TEXT = "#F9FAFB"
    DARK_TEXT_DIM = "#9CA3AF"
    DARK_TEXT_MUTED = "#6B7280"

    # Light Mode
    LIGHT_BG = "#F8FAFC"
    LIGHT_SURFACE = "#FFFFFF"
    LIGHT_SURFACE_VARIANT = "#F1F5F9"
    LIGHT_TEXT = "#0F172A"
    LIGHT_TEXT_DIM = "#64748B"
    LIGHT_TEXT_MUTED = "#94A3B8"

    SPLASH_BG = "#0B0F19"

    WHITE = ft.Colors.WHITE
    BLACK = ft.Colors.BLACK
    TRANSPARENT = ft.Colors.TRANSPARENT

    @staticmethod
    def is_dark_mode(mode: ft.ThemeMode | None, platform_brightness=None) -> bool:
        """The branch every mode-dependent decision shares: SYSTEM resolves
        through the platform brightness (dark when unknown — a TV default).

        Callers pass the values they already have; nothing reads the page
        itself, so this stays pure and testable.
        """
        if mode == ft.ThemeMode.LIGHT:
            return False
        if mode == ft.ThemeMode.DARK:
            return True
        # SYSTEM with no brightness answer yet (or a platform that refuses
        # the question) is dark — the app's own default, not a coin flip.
        if platform_brightness is None:
            return True
        try:
            return platform_brightness == ft.Brightness.DARK
        except Exception:
            return True


class AppTheme:
    # The surface-container roles must be pinned to the app's own palette:
    # unspecified roles fall back to Material's baseline (purple-tinted),
    # which would make light-mode cards disagree with the DARK_SURFACE
    # family they replaced.
    _DARK_SURFACE_ROLES = {
        "surface": AppColors.DARK_BG,
        "surface_bright": AppColors.DARK_SURFACE,
        "surface_dim": AppColors.DARK_BG,
        "surface_container_lowest": "#060A12",
        "surface_container_low": AppColors.DARK_BG,
        "surface_container": "#161F30",
        "surface_container_high": AppColors.DARK_SURFACE,
        "surface_container_highest": AppColors.DARK_SURFACE_VARIANT,
        "on_surface": AppColors.DARK_TEXT,
        "on_surface_variant": AppColors.DARK_TEXT_DIM,
        "outline": AppColors.DARK_TEXT_MUTED,
        "outline_variant": AppColors.DARK_TEXT_MUTED,
    }
    _LIGHT_SURFACE_ROLES = {
        "surface": AppColors.LIGHT_BG,
        "surface_bright": AppColors.LIGHT_SURFACE,
        "surface_dim": AppColors.LIGHT_BG,
        "surface_container_lowest": AppColors.LIGHT_SURFACE,
        "surface_container_low": AppColors.LIGHT_SURFACE,
        "surface_container": "#EDF1F7",
        "surface_container_high": AppColors.LIGHT_SURFACE_VARIANT,
        "surface_container_highest": "#E6ECF4",
        "on_surface": AppColors.LIGHT_TEXT,
        "on_surface_variant": AppColors.LIGHT_TEXT_DIM,
        "outline": AppColors.LIGHT_TEXT_MUTED,
        "outline_variant": "#CBD5E1",
    }

    # One motion everywhere: the platform defaults differ per OS, which
    # makes the same tap feel like a different app on a TV and a phone.
    _PAGE_TRANSITIONS = ft.PageTransitionsTheme(
        android=ft.PageTransitionTheme.CUPERTINO,
        ios=ft.PageTransitionTheme.CUPERTINO,
        linux=ft.PageTransitionTheme.CUPERTINO,
        macos=ft.PageTransitionTheme.CUPERTINO,
        windows=ft.PageTransitionTheme.CUPERTINO,
    )

    @staticmethod
    def get_dark_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                secondary=AppColors.SECONDARY,
                error=AppColors.ERROR,
                on_primary=ft.Colors.WHITE,
                on_secondary=ft.Colors.WHITE,
                surface_tint=AppColors.TRANSPARENT,
                **AppTheme._DARK_SURFACE_ROLES,
            ),
            focus_color=AppColors.PRIMARY,
            visual_density=ft.VisualDensity.COMFORTABLE,
            dialog_theme=ft.DialogTheme(
                bgcolor=AppColors.DARK_SURFACE,
                title_text_style=ft.TextStyle(color=AppColors.DARK_TEXT),
                content_text_style=ft.TextStyle(color=AppColors.DARK_TEXT_DIM),
            ),
            card_theme=ft.CardTheme(
                color=AppColors.DARK_SURFACE,
                shadow_color=AppColors.TRANSPARENT,
            ),
            navigation_bar_theme=ft.NavigationBarTheme(
                bgcolor=AppColors.DARK_SURFACE,
                indicator_color=AppColors.PRIMARY,
                label_text_style=ft.TextStyle(color=AppColors.DARK_TEXT_DIM),
            ),
            appbar_theme=ft.AppBarTheme(
                bgcolor=AppColors.DARK_SURFACE,
                title_text_style=ft.TextStyle(color=AppColors.DARK_TEXT),
                toolbar_text_style=ft.TextStyle(color=AppColors.DARK_TEXT_DIM),
            ),
            page_transitions=AppTheme._PAGE_TRANSITIONS,
        )

    @staticmethod
    def get_light_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                secondary=AppColors.SECONDARY,
                error=AppColors.ERROR,
                on_primary=ft.Colors.WHITE,
                on_secondary=ft.Colors.WHITE,
                surface_tint=AppColors.TRANSPARENT,
                **AppTheme._LIGHT_SURFACE_ROLES,
            ),
            focus_color=AppColors.PRIMARY,
            visual_density=ft.VisualDensity.COMFORTABLE,
            dialog_theme=ft.DialogTheme(
                bgcolor=AppColors.LIGHT_SURFACE,
                title_text_style=ft.TextStyle(color=AppColors.LIGHT_TEXT),
                content_text_style=ft.TextStyle(color=AppColors.LIGHT_TEXT_DIM),
            ),
            card_theme=ft.CardTheme(
                color=AppColors.LIGHT_SURFACE,
                shadow_color=AppColors.TRANSPARENT,
            ),
            navigation_bar_theme=ft.NavigationBarTheme(
                bgcolor=AppColors.LIGHT_SURFACE,
                indicator_color=AppColors.PRIMARY,
                label_text_style=ft.TextStyle(color=AppColors.LIGHT_TEXT_DIM),
            ),
            appbar_theme=ft.AppBarTheme(
                bgcolor=AppColors.LIGHT_SURFACE,
                title_text_style=ft.TextStyle(color=AppColors.LIGHT_TEXT),
                toolbar_text_style=ft.TextStyle(color=AppColors.LIGHT_TEXT_DIM),
            ),
            page_transitions=AppTheme._PAGE_TRANSITIONS,
        )
