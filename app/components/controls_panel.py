from typing import Callable, Optional
from nicegui import ui

class ControlsPanel:
    """Owns export-related numeric settings + detail/resolution toggles, buttons & progress bar."""
    def __init__(self, *, on_redraw: Callable[[], None], on_export: Callable[[], None], on_settings_change: Optional[Callable[[], None]] = None):
        self.on_redraw = on_redraw
        self.on_export = on_export
        self.on_settings_change = on_settings_change or (lambda: None)

        # state owned here
        self.layer_input = None
        self.base_input = None
        self.size_input = None
        self.resolution_mode = None
        self.detail_mode = None
        self.progress_bar = None
        self.redraw_button = None
        self.export_button = None

        self._build()

    def get_settings(self):
        return dict(
            layer_height=float(self.layer_input.value),
            base_layers=int(self.base_input.value),
            max_size_cm=float(self.size_input.value),
            resolution_mode=self.resolution_mode.value,
            detail_mode=self.detail_mode.value,
        )

    def set_busy(self, busy: bool):
        if busy:
            self.progress_bar.value = 0
            self.progress_bar.visible = True
            self.redraw_button.disable()
            self.export_button.disable()
        else:
            self.progress_bar.visible = False
            self.redraw_button.enable()

    def enable_export(self, enabled: bool):
        (self.export_button.enable if enabled else self.export_button.disable)()

    def _build(self):
        with ui.column().classes('bg-gray-700 border-t border-gray-900  w-64 flex-none'):
            with ui.column().classes('pt-1 pb-0 p-4 gap-0'):
                with ui.row().classes('w-full items-center justify-between mt-3'):
                    ui.markdown('**Details**').classes('ml-1 text-gray-400')
                    self.detail_mode = ui.toggle(['◔', '◑', '◕', '●'], value='◔').props("size=lg padding='0px 10px'")
                with ui.row().classes('w-full items-center justify-between'):
                    ui.markdown('**Resolution**').classes('mt-2 ml-1 text-gray-400')
                    self.resolution_mode = ui.toggle(['◔', '◑', '◕', '●'], value='◔').props("size=lg padding='0px 10px'")

                with ui.row().classes('items-center mt-2 justify-center'):
                    self.redraw_button = ui.button('Redraw', icon='refresh', on_click=self.on_redraw).props('color=primary size=sm')
                    self.export_button = ui.button('Export', icon='download', on_click=self.on_export).props('color=secondary size=sm')
                    self.export_button.disable()
                self.progress_bar = ui.linear_progress(value=0).style('width:100%').classes('mt-2')
                self.progress_bar.visible = False

            with ui.expansion('Export settings', icon='settings').classes('bg-gray-700 border-t border-gray-900  w-64 p-0'):
                self.layer_input = ui.number(label='Layer height (mm)', value=0.12, format='%.2f', step=0.02, min=0.001, max=10, on_change=lambda _: self.on_settings_change()).classes('w-full')
                self.base_input = ui.number(label='Base layers', value=3, format='%d', min=1, max=999).props('icon=layers').classes('w-full')
                self.size_input = ui.number(label='Max size (cm)', value=10, format='%.1f', min=0.1, max=1000000).props('icon=straighten').classes('w-full')
