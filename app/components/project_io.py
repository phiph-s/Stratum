from typing import Callable
from nicegui import ui, app
import base64, json

class ProjectIO:
    """Encapsulates project dialogs and save/open; asks the app for data via callbacks."""
    def __init__(self, *, get_project_data: Callable[[], dict], set_project_data: Callable[[dict], None], set_image_from_bytes: Callable[[bytes], None]):
        self.get_project_data = get_project_data
        self.set_project_data = set_project_data
        self.set_image_from_bytes = set_image_from_bytes

        self.last_saved_path = None

        with ui.dialog() as self.project_dialog:
            with ui.column():
                ui.markdown('### Open Project')
                ui.upload(on_upload=self._on_upload_project, label='Select project JSON', auto_upload=True).props('accept=".json"')

    def save(self, save_as=False):
        """Save project data - synchronous version to avoid UI context issues."""
        data = json.dumps(self.get_project_data())
        if app.native.main_window:
            # For native apps, we need to use async file dialog
            self._save_native_async(data, save_as)
        else:
            # For web, we can use download directly since we're in sync context
            ui.download.content(data, 'project.json')
            ui.notify('Project downloaded', color='green')

    async def _save_native_async(self, data: str, save_as: bool):
        """Handle native file saving asynchronously."""
        import webview
        if not save_as and self.last_saved_path:
            file = self.last_saved_path
        else:
            result = await app.native.main_window.create_file_dialog(webview.SAVE_DIALOG, save_filename='project.json')
            if not result:
                return
            file = result[0]
        try:
            with open(file, 'w') as f:
                f.write(data)
            self.last_saved_path = file
            ui.notify(f'Project saved to {file}', color='green')
        except Exception as e:
            ui.notify(f'Error saving project: {str(e)}', color='red')

    def open_dialog(self):
        self.project_dialog.open()

    async def open_native(self):
        if not app.native.main_window:
            self.open_dialog(); return
        files = await app.native.main_window.create_file_dialog(allow_multiple=False, file_types=['JSON files (*.json)'])
        if not files:
            return
        file = files[0]
        with open(file, 'r') as f:
            content = f.read()
        self.load_project(content)
        self.last_saved_path = file

    def _on_upload_project(self, files):
        content = files.content.read().decode()
        self.load_project(content)

    def load_project(self, content: str):
        project = json.loads(content)
        self.set_project_data(project)
        img_data = project.get('image')
        if img_data:
            img_bytes = base64.b64decode(img_data)
            self.set_image_from_bytes(img_bytes)
        ui.notify('Project loaded', color='green')
