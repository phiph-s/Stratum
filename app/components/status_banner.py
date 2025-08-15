from nicegui import ui

class StatusBanner:
    def __init__(self):
        with ui.row().classes('fixed top-2'):
            with ui.row().classes('flex-grow justify-center p-2'):
                self.label = ui.label().classes('z-50 text-sm rounded p-2')
                self.label.set_visibility(False)

    def show(self, text: str, *, color: str, tooltip: str = ''):
        self.label.set_text(text)
        self.label.clear()
        if tooltip:
            with self.label:
                ui.tooltip(tooltip)
        self.label.style(color)
        self.label.set_visibility(True)

    def hide(self):
        self.label.set_visibility(False)
