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
            surface = page.dark_theme.color_scheme.surface
            return surface and str(surface).lower().startswith(("#0", "#1"))
        except Exception:
            return True

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
            surface = page.dark_theme.color_scheme.surface
            is_dark = surface and str(surface).lower().startswith(("#0", "#1"))
            return (
                AppColors.DARK_SURFACE_VARIANT
                if is_dark
                else AppColors.LIGHT_SURFACE_VARIANT
            )
        except Exception:
            return AppColors.DARK_SURFACE_VARIANT


class AppTheme:
    @staticmethod
    def get_dark_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                secondary=AppColors.SECONDARY,
                surface=AppColors.DARK_BG,
                on_surface=AppColors.DARK_TEXT,
                on_surface_variant=AppColors.DARK_TEXT_DIM,
                error=AppColors.ERROR,
                on_primary=ft.Colors.WHITE,
                on_secondary=ft.Colors.WHITE,
                outline=AppColors.DARK_TEXT_MUTED,
                surface_tint=AppColors.TRANSPARENT,
            ),
            focus_color=AppColors.PRIMARY,
            visual_density=ft.VisualDensity.COMFORTABLE,
        )

    @staticmethod
    def get_light_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=AppColors.PRIMARY,
                secondary=AppColors.SECONDARY,
                surface=AppColors.LIGHT_BG,
                on_surface=AppColors.LIGHT_TEXT,
                on_surface_variant=AppColors.LIGHT_TEXT_DIM,
                error=AppColors.ERROR,
                on_primary=ft.Colors.WHITE,
                on_secondary=ft.Colors.WHITE,
                outline=AppColors.LIGHT_TEXT_MUTED,
                surface_tint=AppColors.TRANSPARENT,
            ),
            focus_color=AppColors.PRIMARY,
            visual_density=ft.VisualDensity.COMFORTABLE,
        )
