from nicegui import app, ui
import json
import uuid


class FilamentManager:
    def __init__(self):
        self.filament_dialog = None
        self.edit_dialog = None
        self.filament_list_container = None
        self.filament_list_container_favs = None
        self.name_input = None
        self.color_input = None
        self.td_value_input = None
        self.favorite_checkbox = None
        # Edit dialog inputs
        self.edit_name_input = None
        self.edit_color_input = None
        self.edit_td_value_input = None
        self.edit_favorite_checkbox = None
        self.editing_filament_id = None
        self.on_add_callback = None
        self.tab_panels = None

        # Load saved filaments from storage
        self.load_filaments()

    def load_filaments(self):
        self.saved_filaments = app.storage.general.get('saved_filaments', [])

    def save_filaments(self):
        """Save filaments to NiceGUI storage"""
        app.storage.general['saved_filaments'] = self.saved_filaments

    def add_filament(self):
        """Add a new filament to the saved list"""
        filament = {
            'id': str(uuid.uuid4()),
            'name': self.name_input.value or 'Unnamed Filament',
            'color': self.color_input.value,
            'td_value': float(self.td_value_input.value),
            'favorite': self.favorite_checkbox.value
        }

        self.saved_filaments.append(filament)
        self.save_filaments()
        self.update_filament_list(container=self.filament_list_container)
        self.update_filament_list(container=self.filament_list_container_favs, favorites_only=True)

        if self.favorite_checkbox.value:
            self.tab_panels.value = 'Favorites'
        else:
            self.tab_panels.value = 'All'

        # Reset form
        self.name_input.value = ''
        self.color_input.value = '#000000'
        self.td_value_input.value = 0.5
        self.favorite_checkbox.value = False

        ui.notify('Filament added successfully', color='green')

    def find_filament_by_id(self, filament_id):
        """Find filament by ID and return both filament and index"""
        for idx, filament in enumerate(self.saved_filaments):
            if filament['id'] == filament_id:
                return filament, idx
        return None, -1

    def remove_filament(self, filament_id):
        """Remove a filament from the saved list"""
        filament, idx = self.find_filament_by_id(filament_id)
        if idx >= 0:
            self.saved_filaments.pop(idx)
            self.save_filaments()
            self.update_filament_list(container=self.filament_list_container)
            self.update_filament_list(container=self.filament_list_container_favs, favorites_only=True)
            ui.notify('Filament removed', color='info')

    def toggle_favorite(self, filament_id):
        """Toggle favorite status of a filament"""
        filament, idx = self.find_filament_by_id(filament_id)
        if idx >= 0:
            self.saved_filaments[idx]['favorite'] = not self.saved_filaments[idx]['favorite']
            self.save_filaments()
            self.update_filament_list(container=self.filament_list_container)
            self.update_filament_list(container=self.filament_list_container_favs, favorites_only=True)

    def add_to_project(self, filament_id):
        """Add a filament to the project filament list"""
        if self.on_add_callback:
            filament, _ = self.find_filament_by_id(filament_id)
            if filament:
                project_filament = {
                    'id': filament['id'],
                    # we also copy the name and td_value to save with the project (but prefer from manager)
                    'copied_data': {
                        'name': filament['name'],
                        'color': filament['color'],
                        'td_value': filament['td_value']
                    }
                }
                self.on_add_callback(project_filament)

    def update_filament_list(self, container=None, favorites_only=False):
        """Update the filament list display"""
        if not container:
            return

        container.clear()

        # Sort filaments: favorites first, then by name
        sorted_filaments = sorted(self.saved_filaments,
                                  key=lambda f: (not f['favorite'], f['name'].lower()))

        with container:
            if not sorted_filaments:
                ui.markdown('**No filaments saved**').classes('text-gray-500 p-4')
                return

            for filament in sorted_filaments:
                if favorites_only and not filament['favorite']:
                    continue

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
                            ui.label(f"TD: {filament['td_value']}").classes(
                                'text-sm text-gray-500')

                    # Action buttons
                    with ui.row().classes('gap-1'):
                        ui.button(
                            icon='add',
                            on_click=lambda _, fid=filament['id']: self.add_to_project(fid)
                        ).props('flat round size=sm color=primary').tooltip('Add to Project')

                        ui.button(
                            icon='favorite' if filament['favorite'] else 'favorite_border',
                            on_click=lambda _, fid=filament['id']: self.toggle_favorite(fid)
                        ).props('flat round size=sm color=orange').tooltip('Toggle Favorite')

                        ui.button(
                            icon='delete',
                            on_click=lambda _, fid=filament['id']: self.remove_filament(fid)
                        ).props('flat round size=sm color=red').tooltip('Delete')

                        ui.button(
                            icon='edit',
                            on_click=lambda _, fid=filament['id']: self.open_edit_dialog(fid)
                        ).props('flat round size=sm color=blue').tooltip('Edit')

    def open_dialog(self):
        """Open the filament management dialog"""
        if self.filament_dialog:
            self.filament_dialog.open()

    def open_edit_dialog(self, filament_id):
        """Open the edit dialog for a specific filament"""
        filament, _ = self.find_filament_by_id(filament_id)
        if filament:
            self.editing_filament_id = filament_id
            self.edit_name_input.value = filament['name']
            self.edit_color_input.value = filament['color']
            self.edit_td_value_input.value = filament['td_value']
            self.edit_favorite_checkbox.value = filament['favorite']
            self.edit_dialog.open()

    def build_dialog(self, on_add_callback=None):
        """Build the filament management dialog"""
        self.on_add_callback = on_add_callback

        with ui.dialog().style('z-index:80').props('position=left') as self.filament_dialog:
            with ui.card().classes('w-80 h-full ml-40 p-0').style('max-height: 600px; left: 100px;'):
                with ui.column().classes('w-full flex-auto gap-0'):
                    with ui.tabs().classes('w-full') as tabs:
                        add = ui.tab('Add')
                        fav = ui.tab('Favorites')
                        all = ui.tab('All')
                    with ui.tab_panels(tabs, value=fav).classes('w-full h-full') as self.tab_panels:
                        with ui.tab_panel(add):
                            self.name_input = ui.input(
                                label='Filament Name',
                                placeholder='e.g., PLA Red, PETG Clear...'
                            ).classes('w-full')

                            self.color_input = ui.color_input(
                                label='Color',
                                value='#000000'
                            ).classes('w-full')

                            self.td_value_input = ui.number(
                                label='TD Value',
                                value=0.5,
                                min=0.0,
                                max=500.0,
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

                        with ui.tab_panel(fav).classes('h-full p-0'):
                            with ui.scroll_area().classes('h-full p-0'):
                                self.filament_list_container_favs = ui.column().classes('w-full')
                        with ui.tab_panel(all).classes('h-full p-0'):
                            with ui.scroll_area().classes('h-full p-0'):
                                self.filament_list_container = ui.column().classes('w-full')

        with ui.dialog().style('z-index:50').props('position=left') as self.edit_dialog:
            with ui.card().classes('w-80 p-0').style('max-height: 600px; left: 100px;'):
                with ui.column().classes('w-full flex-auto gap-0'):
                    ui.label('Edit Filament').classes('text-lg font-semibold p-4')
                    self.edit_name_input = ui.input(
                        label='Filament Name',
                        placeholder='e.g., PLA Red, PETG Clear...'
                    ).classes('w-full')

                    self.edit_color_input = ui.color_input(
                        label='Color',
                        value='#000000'
                    ).classes('w-full')

                    self.edit_td_value_input = ui.number(
                        label='TD Value',
                        value=0.5,
                        min=0.0,
                        max=500.0,
                        step=0.1,
                        format='%.2f'
                    ).classes('w-full')

                    self.edit_favorite_checkbox = ui.checkbox(
                        'Mark as favorite'
                    )

                    ui.button(
                        'Save Changes',
                        icon='save',
                        on_click=self.save_edit_filament
                    ).props('color=primary').classes('w-full mt-4')

                    ui.button(
                        'Cancel',
                        on_click=self.edit_dialog.close
                    ).props('flat color=red').classes('w-full mt-2')

        # Initial load of filament list
        self.update_filament_list(container=self.filament_list_container)
        self.update_filament_list(container=self.filament_list_container_favs, favorites_only=True)

        return self.filament_dialog

    def save_edit_filament(self):
        """Save changes to an edited filament"""
        filament, idx = self.find_filament_by_id(self.editing_filament_id)
        if idx >= 0:
            # Update filament data
            filament['name'] = self.edit_name_input.value
            filament['color'] = self.edit_color_input.value
            filament['td_value'] = float(self.edit_td_value_input.value)
            filament['favorite'] = self.edit_favorite_checkbox.value

            self.save_filaments()
            self.update_filament_list(container=self.filament_list_container)
            self.update_filament_list(container=self.filament_list_container_favs, favorites_only=True)

            ui.notify('Filament updated successfully', color='green')
            self.edit_dialog.close()
