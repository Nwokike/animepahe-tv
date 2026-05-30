import flet as ft


class FocusManager:
    def __init__(self, page: ft.Page):
        self.page = page
        self._back_handler = None
        page.on_keyboard_event = self._handle_keyboard

    def set_back_handler(self, handler: callable):
        self._back_handler = handler

    def _handle_keyboard(self, e: ft.KeyboardEvent):
        if e.key in ("Escape", "Go Back", "Browser Back", "Backspace"):
            if self._back_handler:
                self._back_handler()

    @staticmethod
    def make_scroll_on_focus(scrollable: ft.ListView | ft.Column):
        async def _on_focus(e):
            control_key = getattr(e.control, "key", None)
            if control_key and hasattr(scrollable, "scroll_to"):
                try:
                    await scrollable.scroll_to(scroll_key=control_key, duration=200)
                except Exception:
                    pass

        return _on_focus

    @staticmethod
    def focus_style(
        control: ft.Container, focused: bool, primary_color: str = "#E94560"
    ):
        if focused:
            control.scale = 1.08
            control.bgcolor = ft.Colors.with_opacity(0.25, primary_color)
            control.border = ft.Border.all(4, primary_color)
            control.shadow = ft.BoxShadow(
                spread_radius=8,
                blur_radius=35,
                color=ft.Colors.with_opacity(0.85, primary_color),
                offset=ft.Offset(0, 12),
            )
        else:
            control.scale = 1.0
            control.bgcolor = ft.Colors.TRANSPARENT
            control.border = ft.Border.all(4, ft.Colors.TRANSPARENT)
            control.shadow = None
        try:
            control.update()
        except Exception:
            pass
