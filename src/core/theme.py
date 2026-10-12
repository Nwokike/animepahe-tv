import flet as ft


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
    def _is_dark(page: ft.Page) -> bool:
        if page.theme_mode == ft.ThemeMode.LIGHT:
            return False
        if page.theme_mode == ft.ThemeMode.DARK:
            return True
        try:
            return page.platform_brightness == ft.Brightness.DARK
        except Exception:
            return True

    @staticmethod
    def is_dark_mode(mode: ft.ThemeMode | None, platform_brightness=None) -> bool:
        """The branch every accessor shares: SYSTEM resolves through the
        platform brightness (dark when unknown — a TV default)."""
        if mode == ft.ThemeMode.LIGHT:
            return False
        if mode == ft.ThemeMode.DARK:
            return True
        try:
            return platform_brightness == ft.Brightness.DARK
        except Exception:
            return True

    @staticmethod
    def get_text(page: ft.Page):
        """The on-surface text color for the page's effective mode."""
        try:
            mode = getattr(page, "theme_mode", None)
            brightness = getattr(page, "platform_brightness", None)
        except Exception:
            mode, brightness = None, None
        return AppColors.DARK_TEXT if AppColors.is_dark_mode(mode, brightness) else AppColors.LIGHT_TEXT

    @staticmethod
    def get_text_dim(page: ft.Page):
        try:
            mode = getattr(page, "theme_mode", None)
            brightness = getattr(page, "platform_brightness", None)
        except Exception:
            mode, brightness = None, None
        return (
            AppColors.DARK_TEXT_DIM
            if AppColors.is_dark_mode(mode, brightness)
            else AppColors.LIGHT_TEXT_DIM
        )

    @staticmethod
    def get_glass_bg(page: ft.Page):
        return ft.Colors.with_opacity(
            0.05, ft.Colors.WHITE if AppColors._is_dark(page) else ft.Colors.BLACK
        )

    @staticmethod
    def get_hover_bg(page: ft.Page):
        return ft.Colors.with_opacity(
            0.1, ft.Colors.WHITE if AppColors._is_dark(page) else ft.Colors.BLACK
        )

    @staticmethod
    def get_surface_variant(page: ft.Page):
        if page.theme_mode == ft.ThemeMode.LIGHT:
            return AppColors.LIGHT_SURFACE_VARIANT
        if page.theme_mode == ft.ThemeMode.DARK:
            return AppColors.DARK_SURFACE_VARIANT
        try:
            is_dark = page.platform_brightness == ft.Brightness.DARK
            return (
                AppColors.DARK_SURFACE_VARIANT
                if is_dark
                else AppColors.LIGHT_SURFACE_VARIANT
            )
        except Exception:
            return AppColors.DARK_SURFACE_VARIANT


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
                shadow_color=ft.Colors.TRANSPARENT,
            ),
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
                shadow_color=ft.Colors.TRANSPARENT,
            ),
        )
