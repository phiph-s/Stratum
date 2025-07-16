from nicegui import app, ui
import json


class FilamentManager:
    def __init__(self):
        self.filament_dialog = None
        self.filament_list_container = None
        self.name_input = None
        self.color_input = None
        self.max_layers_input = None
        self.td_value_input = None
        self.favorite_checkbox = None
        self.on_add_callback = None

        # Load saved filaments from storage
        self.load_filaments()

    def load_filaments(self):
        """Load filaments from NiceGUI storage"""
        try:
            self.saved_filaments = app.storage.general.get('saved_filaments', [])
        except:
            self.saved_filaments = []

    def save_filaments(self):
        """Save filaments to NiceGUI storage"""
        app.storage.general['saved_filaments'] = self.saved_filaments

    def add_filament(self):
        """Add a new filament to the saved list"""
        filament = {
            'name': self.name_input.value or 'Unnamed Filament',
            'color': self.color_input.value,
            'max_layers': int(self.max_layers_input.value),
            'td_value': float(self.td_value_input.value),
            'favorite': self.favorite_checkbox.value
        }

        self.saved_filaments.append(filament)
        self.save_filaments()
        self.update_filament_list()

        # Reset form
        self.name_input.value = ''
        self.color_input.value = '#000000'
        self.max_layers_input.value = 5
        self.td_value_input.value = 0.5
        self.favorite_checkbox.value = False

        ui.notify('Filament added successfully', color='green')

    def remove_filament(self, idx):
        """Remove a filament from the saved list"""
        self.saved_filaments.pop(idx)
        self.save_filaments()
        self.update_filament_list()
        ui.notify('Filament removed', color='info')

    def toggle_favorite(self, idx):
        """Toggle favorite status of a filament"""
        self.saved_filaments[idx]['favorite'] = not self.saved_filaments[idx]['favorite']
        self.save_filaments()
        self.update_filament_list()

    def add_to_project(self, idx):
        """Add a filament to the project filament list"""
        if self.on_add_callback:
            filament = self.saved_filaments[idx]
            # Convert to old format with default coverage for now
            project_filament = {
                'color': filament['color'],
                'cover': 0.33  # Default coverage as requested
            }
            self.on_add_callback(project_filament)

    def update_filament_list(self):
        """Update the filament list display"""
        if not self.filament_list_container:
            return

        self.filament_list_container.clear()

        # Sort filaments: favorites first, then by name
        sorted_filaments = sorted(self.saved_filaments,
                                  key=lambda f: (not f['favorite'], f['name'].lower()))

        with self.filament_list_container:
            if not sorted_filaments:
                ui.markdown('**No filaments saved**').classes('text-gray-500 p-4')
                return

            for idx, filament in enumerate(sorted_filaments):
                # Find original index for operations
                orig_idx = self.saved_filaments.index(filament)

                with ui.card().classes('w-full mb-2'):
                    with ui.row().classes('items-center justify-between w-full'):
                        with ui.row().classes('items-center gap-3'):
                            # Color indicator
                            ui.html(
                                f"<div style=\"width: 30px; height: 30px; border-radius: 50%; border: 2px solid #ccc; background-color: {filament['color']};\"></div>")

                            # Filament info
                            with ui.column().classes('gap-0'):
                                name_text = filament['name']
                                if filament['favorite']:
                                    name_text = f"⭐ {name_text}"
                                ui.label(name_text).classes('font-semibold')
                                ui.label(f"Max layers: {filament['max_layers']}, TD: {filament['td_value']}").classes(
                                    'text-sm text-gray-500')

                        # Action buttons
                        with ui.row().classes('gap-1'):
                            ui.button(
                                icon='favorite' if filament['favorite'] else 'favorite_border',
                                on_click=lambda _, i=orig_idx: self.toggle_favorite(i)
                            ).props('flat round size=sm color=orange').tooltip('Toggle Favorite')

                            ui.button(
                                icon='add',
                                on_click=lambda _, i=orig_idx: self.add_to_project(i)
                            ).props('flat round size=sm color=primary').tooltip('Add to Project')

                            ui.button(
                                icon='delete',
                                on_click=lambda _, i=orig_idx: self.remove_filament(i)
                            ).props('flat round size=sm color=red').tooltip('Delete')

    def open_dialog(self):
        """Open the filament management dialog"""
        if self.filament_dialog:
            self.filament_dialog.open()

    def build_dialog(self, on_add_callback=None):
        """Build the filament management dialog"""
        self.on_add_callback = on_add_callback

        with ui.dialog().props('maximized') as self.filament_dialog:
            with ui.card().classes('w-full h-full'):
                with ui.row().classes('items-center justify-between mb-4'):
                    ui.markdown('## Filament Management')
                    ui.button(icon='close', on_click=lambda: self.filament_dialog.close()).props('flat round')

                with ui.row().classes('w-full h-full gap-6'):
                    # Left side: Add new filament
                    with ui.column().classes('flex-none w-80 gap-4'):
                        ui.markdown('### Add New Filament')

                        with ui.card().classes('w-full'):
                            self.name_input = ui.input(
                                label='Filament Name',
                                placeholder='e.g., PLA Red, PETG Clear...'
                            ).classes('w-full')

                            self.color_input = ui.color_input(
                                label='Color',
                                value='#000000'
                            ).classes('w-full')

                            self.max_layers_input = ui.number(
                                label='Max Layers',
                                value=5,
                                min=1,
                                max=100,
                                format='%d'
                            ).classes('w-full')

                            self.td_value_input = ui.number(
                                label='TD Value',
                                value=0.5,
                                min=0.0,
                                max=1.0,
                                step=0.1,
                                format='%.2f'
                            ).classes('w-full')

                            self.favorite_checkbox = ui.checkbox(
                                'Mark as favorite'
                            )

                            ui.button(
                                'Add Filament',
                                icon='add',
                                on_click=self.add_filament
                            ).props('color=primary').classes('w-full mt-4')

                    # Right side: Saved filaments list
                    with ui.column().classes('flex-auto'):
                        ui.markdown('### Saved Filaments')

                        with ui.scroll_area().classes('h-full border rounded'):
                            self.filament_list_container = ui.column().classes('w-full p-2')

        # Initial load of filament list
        self.update_filament_list()

        return self.filament_dialog
