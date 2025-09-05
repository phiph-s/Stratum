from typing import Callable, List, Dict, Optional
from nicegui import ui

class FilamentPanel:
    """Owns the project filament list and all related UI (list, dialogs, reordering)."""
    def __init__(self, *, filament_manager, on_change: Optional[Callable[[List[dict]], None]] = None):
        self.filament_manager = filament_manager
        self.on_change = on_change or (lambda filaments: None)
        self.filaments: List[Dict] = []
        self._editing_idx: Optional[int] = None
        self.is_multimaterial_mode = False
        self.base_color_index = 0  # Index of filament selected as base color
        self.base_color_radio_group = None  # Radio group for base color selection

        # UI refs
        self.container = None
        self._edit_max_layers_dialog = None
        self._edit_max_layers_input = None

        self._build()

    # ---- Public API -----------------------------------------------------
    def get_filaments(self) -> List[Dict]:
        return self.filaments

    def set_filaments(self, filaments: List[Dict]):
        self.filaments = list(filaments)
        self._refresh()
        self.on_change(self.filaments)

    def add_from_manager(self, filament: Dict):
        filament = dict(filament)
        filament.setdefault('max_layers', 5)
        self.filaments.append(filament)
        self._refresh()
        ui.notify('Filament added to project', color='green')
        self.on_change(self.filaments)

    # ---- UI & internal logic -------------------------------------------
    def _build(self):
        # dialogs
        with ui.dialog() as self._edit_max_layers_dialog:
            with ui.card():
                ui.markdown('#### Edit Filament Max Layers')
                self._edit_max_layers_input = ui.number(label='Max Layers', value=5, format='%d', min=1, max=999).style('width:100%')
                with ui.row().classes('justify-end gap-2'):
                    ui.button('Cancel', on_click=self._edit_max_layers_dialog.close)
                    ui.button('Apply', on_click=self._apply_edit_max_layers)

        # panel
        with ui.column().classes('flex-auto gap-0 w-64 mt-16'):
            with ui.row().classes('items-center justify-between mb-2 mt-6 ml-4'):
                ui.markdown('**Filament List**').classes('text-gray-300')
                ui.button('Create', icon='add', on_click=self._open_manager).props('size=sm flat').tooltip('Manage Filaments')

            with ui.scroll_area().classes('w-full m-0 p-0 bg-neutral-900 flex-auto'):
                self.container = ui.column().classes('gap-2 mb-4 w-full')
                with self.container:
                    ui.markdown('**No filaments added**').classes('text-gray-500')

    def _open_manager(self):
        self.filament_manager.open_dialog()

    def _refresh(self):
        self.container.clear()

        if not self.filaments:
            with self.container:
                ui.markdown('**No filaments added**').classes('text-gray-500')
            return


        # In multimaterial mode, create a radio group for base color selection
        if self.is_multimaterial_mode:
            # Create options for the radio group (one for each filament)
            radio_options = [str(i) for i in range(len(self.filaments))]
            with self.container:
                ui.label(
                    "In Multimaterial mode there is no filament ordering, and one filament is selected as 'base color'.").classes(
                    'text-xs text-gray-500 mx-2 mb-2').tooltip(
                    'The base color serves as the foundation for multimaterial prints. It has only effect when face down printing is disabled in Export settings and base layers are greater then 0.')

                self.base_color_radio_group = ui.radio(
                    options=radio_options,
                    value=str(self.base_color_index),
                    on_change=lambda e: self._set_base_color(int(e.value))
                ).style('display: none;')  # Hide the actual radio group UI

        for idx, f in enumerate(reversed(self.filaments)):
            real_idx = len(self.filaments) - 1 - idx

            manager_id = f.get('id')
            data = f.get('copied_data', {})
            if manager_id is not None:
                f_data, _ = self.filament_manager.find_filament_by_id(manager_id)
                if f_data:
                    data = f_data

            instance_max_layers = f.get('max_layers', data.get('max_layers', 5))
            color_hex = data.get('color', '#000000')
            try:
                r = int(color_hex[1:3], 16); g = int(color_hex[3:5], 16); b = int(color_hex[5:7], 16)
                is_bright = (r + g + b) / 3 > 128
            except Exception:
                is_bright = False
            color = 'black' if is_bright else 'white'
            color_rev = 'white' if is_bright else 'black'
            with self.container:
                row_classes = 'items-center gap-1 p-1 rounded'
                row_classes += ' text-black' if is_bright else ' text-white border border-gray-400'
                with ui.row().classes('w-full ' + row_classes).style(f'background-color:{data.get("color", "#000000")};'):
                    if self.is_multimaterial_mode:
                        # In multimaterial mode, show clickable radio button for base color selection
                        with ui.column().classes('gap-1 flex-shrink-0'):
                            is_selected = self.base_color_index == real_idx
                            # Use functools.partial or a method to avoid lambda closure issues
                            radio_btn = ui.button(
                                icon='radio_button_checked' if is_selected else 'radio_button_unchecked',
                                on_click=self._create_base_color_handler(real_idx)
                            ).props('flat round size=xs').style(f'min-width: 20px; min-height: 20px;').tooltip('Set as base color').classes(row_classes)
                    else:
                        # In normal mode, show order buttons
                        with ui.column().classes('gap-1 flex-shrink-0'):
                            ui.button(icon='keyboard_arrow_up', on_click=self._create_move_handler(real_idx, real_idx+1)).props('flat round size=xs').style(f'min-width: 20px; min-height: 20px;').classes(row_classes)
                            ui.button(icon='keyboard_arrow_down', on_click=self._create_move_handler(real_idx, real_idx-1)).props('flat round size=xs').style(f'min-width: 20px; min-height: 20px;').classes(row_classes)

                    with ui.column().classes('flex-grow gap-0 min-w-0'):
                        with ui.row().classes('items-center gap-2 w-full justify-between'):
                            project_specific = f.get('id') is None
                            add = '* ' if project_specific else ''
                            tooltip = data.get('name', 'Filament') + (' (not in library)' if project_specific else '')
                            ui.label(add + data.get('name', 'Filament')).classes('text-sm font-semibold w-32 truncate').tooltip(tooltip)
                            with ui.button(icon='more_vert').props('flat round size=sm').style('min-width: 32px;'):
                                with ui.menu():
                                    if not self.is_multimaterial_mode:
                                        ui.menu_item('Edit max layers', on_click=self._create_edit_layers_handler(real_idx))
                                    ui.menu_item('Remove', on_click=self._create_remove_handler(real_idx))

                        if self.is_multimaterial_mode:
                            # In multimaterial mode, show base color indicator
                            if real_idx == self.base_color_index:
                                with ui.row().classes('items-center gap-1 w-full flex-nowrap'):
                                    ui.icon('stars').classes('text-xs flex-shrink-0 pr-1')
                                    ui.label('Base color').classes('text-xs').tooltip('This color serves as the base for multimaterial printing')
                        else:
                            # In normal mode, show layer configuration
                            if real_idx == 0:
                                with ui.row().classes('items-center gap-1 w-full flex-nowrap'):
                                    ui.icon('vertical_align_bottom').classes('text-xs flex-shrink-0 pr-1')
                                    ui.label('First layer').classes('text-xs').tooltip('Bottom layers set in Export settings')
                            else:
                                with ui.row().classes('items-center gap-1 w-full flex-nowrap'):
                                    slider = ui.slider(
                                        value=instance_max_layers, min=1, max=20,
                                        on_change=self._create_slider_handler(real_idx)
                                    ).classes('flex-1 min-w-0 mr-1').props(f'dense outlined size=sm label markers color="{color}" label-text-color="{color_rev}"').style('font-size: 0.75rem;')
                                    ui.label().bind_text_from(slider, 'value').classes('text-xs flex-shrink-0 text-center')
                                    ui.icon('layers').classes('text-xs flex-shrink-0 pr-2')

    def _move(self, old: int, new: int):
        if 0 <= new < len(self.filaments):
            self.filaments.insert(new, self.filaments.pop(old))
            self._refresh()
            self.on_change(self.filaments)

    def _remove(self, idx: int):
        self.filaments.pop(idx)
        self._refresh()
        self.on_change(self.filaments)

    def _open_edit_max_layers(self, idx: int):
        self._editing_idx = idx
        cur = self.filaments[idx].get('max_layers', 5)
        self._edit_max_layers_input.value = cur
        self._edit_max_layers_dialog.open()

    def _apply_edit_max_layers(self):
        if self._editing_idx is None:
            return
        self.filaments[self._editing_idx]['max_layers'] = int(self._edit_max_layers_input.value)
        self._edit_max_layers_dialog.close()
        self._refresh()
        ui.notify('Filament updated', color='green')
        self.on_change(self.filaments)

    def _update_max_layers(self, idx: int, value: int):
        if 0 <= idx < len(self.filaments):
            self.filaments[idx]['max_layers'] = value
            self.on_change(self.filaments)

    def set_multimaterial_mode(self, is_multimaterial: bool):
        """Set the multimaterial mode and refresh UI accordingly."""
        self.is_multimaterial_mode = is_multimaterial
        if is_multimaterial and self.filaments:
            # Reset base color to first filament when switching to multimaterial
            self.base_color_index = 0
        self._refresh()

    def get_base_color_index(self) -> int:
        """Get the index of the filament selected as base color."""
        return self.base_color_index

    def _set_base_color(self, idx: int):
        """Set the base color filament index."""
        self.base_color_index = idx
        self._refresh()  # Force a refresh to update the UI
        self.on_change(self.filaments)

    def _create_move_handler(self, real_idx: int, new_idx: int):
        """Create a handler for moving a filament up or down."""
        def handler(*args):
            self._move(real_idx, new_idx)
        return handler

    def _create_base_color_handler(self, real_idx: int):
        """Create a handler for setting the base color."""
        def handler(*args):
            self._set_base_color(real_idx)
        return handler

    def _create_edit_layers_handler(self, real_idx: int):
        """Create a handler for opening the edit max layers dialog."""
        def handler(*args):
            self._open_edit_max_layers(real_idx)
        return handler

    def _create_remove_handler(self, real_idx: int):
        """Create a handler for removing a filament."""
        def handler(*args):
            self._remove(real_idx)
        return handler

    def _create_slider_handler(self, real_idx: int):
        """Create a handler for slider value changes."""
        def handler(e):
            self._update_max_layers(real_idx, int(e.value))
        return handler
