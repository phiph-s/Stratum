from nicegui import app,ui
from lib.mask_creation import segment_to_shades, generate_shades_td
from lib.filament_manager import FilamentManager
from PIL import Image
from app.components.zoomable_image import ZoomableImage
import io
import asyncio
import base64
import zipfile
import json
import matplotlib.backends.backend_svg

from lib.mesh_generator import create_layered_polygons_parallel, render_polygons_to_pil_image, \
    polygons_to_meshes_parallel


class StratumApp:
    def __init__(self):
        # Application state
        self.native = False
        self.filaments = []
        self.editing_idx = None
        self.original_image = None
        self.segmented_image = None
        self.polygons = None
        self.rendered_image_size = None
        self.filament_shades = None
        self.rendered_image = None
        self.status_banner = None
        self.position_info_wrapper = None
        self.last_input_colors = []
        # Live preview state
        self.live_preview_enabled = True
        self.live_preview_segmented = None
        self.live_preview_updating = False
        self.live_preview_restart_pending = False
        # Initialize filament manager
        self.filament_manager = FilamentManager()

        self.last_saved_path = None

        # UI components (to be set in build)
        self.cover_input = None
        self.color_input = None
        self.edit_dialog = None
        self.filament_edit_dialog = None
        self.filament_edit_max_layers_input = None
        self.position_info_content = None
        self.filament_container = None
        self.placeholder = None
        self.image_component = None
        self.progress_bar = None
        self.project_dialog = None
        self.layer_input = None
        self.size_input = None
        self.base_input = None
        self.resolution_mode = None
        self.detail_mode = None
        self.redraw_button = None
        self.export_button = None
        self.live_preview_checkbox = None

    def open_edit(self, idx):
        self.editing_idx = idx
        self.cover_input.value = self.filaments[idx]['cover']
        self.color_input.value = self.filaments[idx]['color']
        self.edit_dialog.open()

    def apply_edit(self):
        if self.editing_idx is None:
            return
        self.filaments[self.editing_idx]['cover'] = float(self.cover_input.value)
        self.filaments[self.editing_idx]['color'] = self.color_input.value
        self.update_filament_list()
        self.edit_dialog.close()

    def show_position_info(self, pos, shade, layer_idx):
        self.position_info_content.clear()
        self.position_info_wrapper.visible = True
        with self.position_info_content:
            pos_x, pos_y = pos
            ui.markdown(f"**Position:** {pos_x:.0f}, {pos_y:.0f} px")
            if self.filament_shades:
                import numpy as np
                all_shades_present = []
                shade_labels = []
                true_colors = []

                for i in reversed(range(shade + 1)):
                    all_shades_present.append(self.filament_shades[layer_idx][i])
                    shade_labels.append(f"{layer_idx + 1}, {i + 1}")
                    true_colors.append(self.last_input_colors[layer_idx])
                for i in reversed(range(layer_idx)):
                    for j in reversed(range(len(self.filament_shades[i]))):
                        all_shades_present.append(self.filament_shades[i][j])
                        shade_labels.append(f"{i + 1}, {j + 1}")
                        true_colors.append(self.last_input_colors[i])
                for i in reversed(range(self.base_input.value - 1)):
                    all_shades_present.append(self.filament_shades[0][0])
                    shade_labels.append(f"1, {i + 2}")
                    true_colors.append(self.last_input_colors[0])
                if all_shades_present:
                    with ui.matplotlib(figsize=(3, 3.5), facecolor=(0,0,0,0)).figure as fig:
                        ax = fig.gca()
                        y_positions = np.arange(len(all_shades_present))
                        shaded_colors_normalized = [(r/255, g/255, b/255) for r, g, b in all_shades_present]
                        true_colors_normalized = [(r/255, g/255, b/255) for r, g, b in true_colors]
                        bar_width = 0.5
                        ax.barh(y_positions, [bar_width]*len(all_shades_present), left=[0]*len(all_shades_present), color=shaded_colors_normalized, edgecolor='black', linewidth=0.5, label='calculated color')
                        ax.barh(y_positions, [bar_width]*len(all_shades_present), left=[bar_width]*len(all_shades_present), color=true_colors_normalized, edgecolor='black', linewidth=0.5, label='true filament color')
                        ax.set_yticks(y_positions)
                        ax.set_yticklabels(shade_labels)
                        ax.set_xlim(0, 1)
                        ax.set_xticks([0.25, 0.75])
                        ax.set_xticklabels(['Calculated', 'True Color'])
                        ax.set_facecolor((0, 0, 0, 0))
                        ax.spines['top'].set_visible(False)
                        ax.spines['right'].set_visible(False)
                        ax.spines['left'].set_color('white')
                        ax.spines['bottom'].set_visible(False)
                        ax.tick_params(axis='y', colors='white')
                        ax.tick_params(axis='x', colors='white')
                        ax.invert_yaxis()
                        if len(all_shades_present) <= 15:
                            for i, (shaded_rgb, true_rgb) in enumerate(zip(all_shades_present, true_colors)):
                                shaded_text = f"({shaded_rgb[0]}, {shaded_rgb[1]}, {shaded_rgb[2]})"
                                ax.text(0.25, i, shaded_text, ha='center', va='center', fontweight='bold', fontsize=8, color='white' if sum(shaded_rgb) < 384 else 'black')
                                true_text = f"({true_rgb[0]}, {true_rgb[1]}, {true_rgb[2]})"
                                ax.text(0.75, i, true_text, ha='center', va='center', fontweight='bold', fontsize=8, color='white' if sum(true_rgb) < 384 else 'black')
                        fig.tight_layout()
            else:
                ui.markdown("**No material at this position**")

    def handle_image_click(self, e):
        if not self.rendered_image or not self.filament_shades:
            ui.notify('Generate the preview first', color='orange')
            return
        r,g,b = e.args['detail']['rgb']['r'], e.args['detail']['rgb']['g'], e.args['detail']['rgb']['b']
        x,y = e.args['detail']['coords']['x'], e.args['detail']['coords']['y']

        def get_layer_and_shade(r,g,b):
            # get shade with rgb value
            for layer_idx, shades in enumerate(self.filament_shades):
                for shade_idx, shade in enumerate(shades):
                    if shade == (r, g, b):
                        clicked_shadeid = shade_idx
                        clicked_layerid = layer_idx
                        return clicked_shadeid , clicked_layerid
            return None, None

        clicked_shadeid, clicked_layerid = get_layer_and_shade(r,g,b)

        self.show_position_info((x, y), clicked_shadeid, clicked_layerid)

    def update_filament_list(self):
        self.filament_container.clear()
        for idx, f in enumerate(reversed(self.filaments)):
            real_idx = len(self.filaments) - 1 - idx

            # Retrieve filament data from manager if available
            manager_id = f.get('id', None)
            data = f.get('copied_data', {})
            project_specific = True
            if manager_id is not None:
                f_data, _ = self.filament_manager.find_filament_by_id(manager_id)  # Ensure the filament is in the manager
                if f_data:
                    data = f_data
                    project_specific = False

            # Get instance max_layers value (takes precedence over manager value)
            instance_max_layers = f.get('max_layers', data.get('max_layers', 5))

            # Check if color is brighter than (128,128,128)
            color_hex = data.get('color', '#000000')
            # Parse hex color to RGB
            try:
                r = int(color_hex[1:3], 16)
                g = int(color_hex[3:5], 16)
                b = int(color_hex[5:7], 16)
                is_bright = (r + g + b) / 3 > 128
            except (ValueError, IndexError):
                is_bright = False

            with self.filament_container:
                row_classes = 'items-center gap-1 p-1 rounded'
                if is_bright:
                    row_classes += ' text-black'
                else:
                    row_classes += ' text-white border border-gray-400'

                with ui.row().classes('w-full ' + row_classes).style(f'background-color:{data["color"]};'):
                    # Left side: Up/Down buttons stacked
                    with ui.column().classes('gap-1 flex-shrink-0'):
                        ui.button(icon='keyboard_arrow_up', on_click=lambda _, i=real_idx: self.move_filament(i, i+1)).props('flat round size=xs').style('min-width: 20px; min-height: 20px;').classes(row_classes)
                        ui.button(icon='keyboard_arrow_down', on_click=lambda _, i=real_idx: self.move_filament(i, i-1)).props('flat round size=xs').style('min-width: 20px; min-height: 20px;').classes(row_classes)

                    # Middle: Name and max_layers input - takes all available space
                    with ui.column().classes('flex-grow gap-0 min-w-0'):
                        # First row: Name with context menu
                        with ui.row().classes('items-center gap-2 w-full justify-between'):
                            add = "* " if project_specific else ""
                            tooltip = data["name"]
                            if project_specific:
                                tooltip += " (not in library)"
                            ui.label(add + data['name']).classes('text-sm font-semibold w-32 truncate').tooltip(tooltip)
                            # Right side: Context menu - fixed size
                            with ui.button(icon='more_vert').props('flat round size=sm').style('min-width: 32px;').classes(row_classes + ' flex-shrink-0'):
                                with ui.menu():
                                    ui.menu_item('Remove', on_click=lambda _, i=real_idx: self.remove_filament(i))

                        # Second row: Slider with icons
                        color = 'black' if is_bright else 'white'
                        color_rev = 'white' if is_bright else 'black'
                        # check for last filament, if so, don't show max_layers slider
                        if real_idx == 0:
                            with ui.row().classes('items-center gap-1 w-full flex-nowrap'):
                                ui.icon('vertical_align_bottom').classes('text-xs flex-shrink-0 pr-1')
                                ui.label("First layer").classes('text-xs').tooltip("The layers of the bottom layer is set in the export settings")
                        else:
                            with ui.row().classes('items-center gap-1 w-full flex-nowrap'):
                                slider = ui.slider(
                                    value=instance_max_layers,
                                    min=1,
                                    max=20,
                                    on_change=lambda e, i=real_idx: self.update_max_layers(i, int(e.value))
                                ).classes('flex-1 min-w-0 mr-1').props(f'dense outlined size=sm label markers color="{color}" label-text-color="{color_rev}"').style('font-size: 0.75rem;')
                                ui.label().bind_text_from(slider, 'value').classes('text-xs flex-shrink-0 text-center')
                                ui.icon('layers').classes('text-xs flex-shrink-0 pr-2')


        if not self.filaments:
            with self.filament_container:
                ui.markdown('**No filaments added**').classes('text-gray-500')

    def move_filament(self, old, new):
        if 0 <= new < len(self.filaments):
            item = self.filaments.pop(old)
            self.filaments.insert(new, item)
        self.update_filament_list()
        # Trigger live preview update
        if self.live_preview_enabled:
            asyncio.create_task(self.update_live_preview())

    def remove_filament(self, idx):
        self.filaments.pop(idx)
        self.update_filament_list()
        # Trigger live preview update
        if self.live_preview_enabled:
            asyncio.create_task(self.update_live_preview())

    def add_filament_from_manager(self, filament):
        """Add a filament from the filament manager to the project"""
        # Add max_layers as an instance attribute with default value of 5
        # since max_layers is now project-specific and not stored in the manager
        filament['max_layers'] = 5  # Default value for new project filaments
        self.filaments.append(filament)
        self.update_filament_list()
        ui.notify('Filament added to project', color='green')
        # Trigger live preview update
        if self.live_preview_enabled:
            asyncio.create_task(self.update_live_preview())

    def open_filament_edit(self, idx):
        """Open edit dialog for filament max_layers"""
        self.editing_idx = idx
        # Get current max_layers value (instance attribute takes precedence)
        current_max_layers = self.filaments[idx].get('max_layers', 5)
        self.filament_edit_max_layers_input.value = current_max_layers
        self.filament_edit_dialog.open()

    def apply_filament_edit(self):
        """Apply changes to filament max_layers"""
        if self.editing_idx is None:
            return
        self.filaments[self.editing_idx]['max_layers'] = int(self.filament_edit_max_layers_input.value)
        self.update_filament_list()
        self.filament_edit_dialog.close()
        ui.notify('Filament updated', color='green')

    def new_project(self):
        self.filaments = []
        self.original_image = None
        self.segmented_image = None
        self.polygons = None
        self.update_filament_list()
        self.placeholder.visible = True
        self.image_component.visible = False

    async def save_project(self, save_as=False):
        project = {
            'filaments': self.filaments,
            'settings': {
                'layer_height': float(self.layer_input.value),
                'base_layers': int(self.base_input.value),
                'max_size_cm': float(self.size_input.value),
                'resolution_mode': self.resolution_mode.value,
                'detail_mode': self.detail_mode.value
            }
        }
        if self.original_image:
            buf = io.BytesIO()
            self.original_image.save(buf, format='PNG')
            project['image'] = base64.b64encode(buf.getvalue()).decode()

        data = json.dumps(project)

        if app.native.main_window:
            print("Saving project in native mode")
            import webview
            if not save_as and self.last_saved_path:
                file = self.last_saved_path
            else:
                result = await app.native.main_window.create_file_dialog(
                    webview.SAVE_DIALOG, save_filename='project.json'
                )
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
        else: ui.download.content(data, 'project.json')

    def on_upload_project(self, files):
        content = files.content.read().decode()
        self.load_project(content)

    def load_project(self, content):
        project = json.loads(content)
        self.filaments = project.get('filaments', [])
        self.update_filament_list()
        img_data = project.get('image')
        if img_data:
            img_bytes = base64.b64decode(img_data)
            self.original_image = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
            buf = io.BytesIO()
            self.original_image.save(buf, format='PNG')
            b64 = base64.b64encode(buf.getvalue()).decode()
            self.placeholder.visible = False
            self.image_component.visible = True
            self.image_component.set_source(f'data:image/png;base64,{b64}')
        settings = project.get('settings', {})
        self.layer_input.value = settings.get('layer_height', 0.2)
        self.base_input.value = settings.get('base_layers', 3)
        self.size_input.value = settings.get('max_size_cm', 10.0)
        self.resolution_mode.value = settings.get('resolution_mode', '◔')
        self.detail_mode.value = settings.get('detail_mode', '◔')
        self.project_dialog.close()
        ui.notify('Project loaded', color='green')

        # check for live preview
        if self.live_preview_enabled and not self.live_preview_updating:
            asyncio.create_task(self.update_live_preview())
        elif self.live_preview_enabled and self.live_preview_updating:
            self.live_preview_restart_pending = True

    def handle_upload(self, files):
        self.original_image = Image.open(files.content).convert('RGBA')
        buf = io.BytesIO()
        self.original_image.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        self.placeholder.visible = False
        self.image_component.visible = True
        self.image_component.set_source(f'data:image/png;base64,{b64}')
        self.upload_image.reset()

    async def on_redraw(self):
        if self.original_image is None or len(self.filaments) < 2:
            ui.notify('Load image and add at least two filaments', color='red')
            return
        self.progress_bar.value = 0
        self.progress_bar.visible = True
        self.redraw_button.disable()
        self.export_button.disable()

        #colors = [tuple(int(f['color'][i:i + 2], 16) for i in (1, 3, 5)) for f in self.filaments]
        colors = []
        max_layers = []
        td_values = []
        self.last_input_colors = []
        for f in self.filaments:
            manager_id = f.get('id', None)
            data = f.get('copied_data', {})
            if manager_id is not None:
                f_data, _ = self.filament_manager.find_filament_by_id(manager_id)  # Ensure the filament is in the manager
                if f_data: data = f_data
            color = data.get('color', '#000000')
            color = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
            self.last_input_colors.append(color)
            colors.append(color)
            # Use instance max_layers (takes precedence over manager value)
            instance_max_layers = f.get('max_layers', data.get('max_layers', 5))
            max_layers.append(instance_max_layers)
            td_values.append(data.get('td_value', 0.5))

        # Calculate resolution scale factor based on image size
        img_width, img_height = self.original_image.size
        total_pixels = img_width * img_height
        # Base scale on 1000x1000 image (1M pixels)
        base_pixels = 1000 * 1000
        resolution_scale = (total_pixels / base_pixels) ** 0.5  # Square root for better scaling

        # Base presets (for 1000x1000 image)
        BASE_RES_PRESETS = {
            '◔': {'simplify_tol': 1.0, 'marching_squares_level': 0.5},
            '◑': {'simplify_tol': 0.5, 'marching_squares_level': 0.25},
            '◕': {'simplify_tol': 0.1, 'marching_squares_level': 0.05},
            "●": {'simplify_tol': 0.01, 'marching_squares_level': 0.5}
        }
        BASE_DETAIL_PRESETS = {
            '◔': {'min_area': 3},
            '◑': {'min_area': 1},
            '◕': {'min_area': 0.5},
            '●': {'min_area': 0.1}
        }

        # Scale presets based on image resolution
        base_res = BASE_RES_PRESETS[self.resolution_mode.value]
        base_detail = BASE_DETAIL_PRESETS[self.detail_mode.value]

        # Scale tolerances - smaller for higher resolution
        simplify_tol = base_res['simplify_tol'] / resolution_scale
        marching_squares_level = base_res['marching_squares_level'] / resolution_scale

        # Scale min_area - larger for higher resolution to avoid tiny artifacts
        min_area = base_detail['min_area'] * resolution_scale

        # Clamp values to reasonable ranges
        simplify_tol = max(0.001, min(10.0, simplify_tol))
        marching_squares_level = max(0.005, min(1.0, marching_squares_level))
        min_area = max(0.01, min(100.0, min_area))

        def compute():
            shades = generate_shades_td(colors, td_values, max_layers, float(self.layer_input.value))
            segmented = segment_to_shades(self.original_image, shades)
            polys = create_layered_polygons_parallel(
                segmented, shades,
                progress_cb=lambda v: setattr(self.progress_bar, 'value', v * 0.5),
                min_area=min_area, simplify_tol=simplify_tol, marching_squares_level=marching_squares_level
            )
            img = render_polygons_to_pil_image(
                polys, shades, segmented.size, max_size=self.size_input.value,
                progress_cb=lambda v: setattr(self.progress_bar, 'value', 0.5 + 0.5 * v)
            )
            return segmented, polys, img, shades
        loop = asyncio.get_running_loop()
        self.segmented_image, self.polygons, img, self.filament_shades = await loop.run_in_executor(None, compute)
        self.rendered_image = img
        self.rendered_image_size = img.size
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        data = base64.b64encode(buf.getvalue()).decode()
        self.image_component.set_source(f'data:image/png;base64,{data}', True)
        self.progress_bar.visible = False
        self.redraw_button.enable()
        self.export_button.enable()
        self.status_banner.set_text("Fully rendered preview")
        self.status_banner.clear()
        with self.status_banner:
            ui.tooltip("This preview is fully rendered and ready for export.")
        self.status_banner.style('background-color: rgba(0,204,0,0.75); color:black;')
        self.status_banner.set_visibility(True)

    async def on_export(self):
        if not self.polygons:
            ui.notify('Nothing to export', color='red')
            return

        self.progress_bar.value = 0
        self.progress_bar.visible = True
        self.redraw_button.disable()
        self.export_button.disable()

        def compute_meshes():
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                print(f"polygons: {len(self.polygons)}")
                meshes = polygons_to_meshes_parallel(
                    self.segmented_image,
                    self.polygons,
                    layer_height=float(self.layer_input.value),
                    target_max_cm=float(self.size_input.value),
                    base_layers=int(self.base_input.value),
                    progress_cb=lambda v: setattr(self.progress_bar, 'value', v)
                )
                print(f"meshes: {len(meshes)}")
                for idx, mesh in enumerate(meshes):
                    stl_buf = io.BytesIO()
                    mesh.export(file_obj=stl_buf, file_type='stl')
                    archive.writestr(f'mesh_{idx}.stl', stl_buf.getvalue())
            return buf

        # Run in executor to avoid blocking the UI
        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(None, compute_meshes)

        buf.seek(0)
        self.redraw_button.enable()
        self.export_button.enable()
        if app.native.main_window:
            print("Exporting meshes in native mode")
            import webview
            result = await app.native.main_window.create_file_dialog(
                webview.SAVE_DIALOG, save_filename='meshes.zip'
            )
            if not result:
                return
            file = result[0]
            try:
                with open(file, 'wb') as f:
                    f.write(buf.getvalue())
                ui.notify(f'Meshes exported to {file}', color='green')
            except Exception as e:
                ui.notify(f'Error exporting meshes: {str(e)}', color='red')
        else: ui.download.content(buf.getvalue(), 'meshes.zip')
        self.progress_bar.visible = False


    async def open_project_switch(self):
        if app.native.main_window:
            files = await app.native.main_window.create_file_dialog(allow_multiple=False,
                                                                    file_types=['JSON files (*.json)'])
            if not files:
                return
            file = files[0]
            with open(file, 'r') as f:
                content = f.read()
                self.load_project(content)
                self.last_saved_path = file
            return
        self.project_dialog.open()

    def reset_image(self):
        self.original_image = None
        self.segmented_image = None
        self.polygons = None
        self.rendered_image_size = None
        self.filament_shades = None
        self.rendered_image = None
        self.live_preview_segmented = None
        self.placeholder.visible = True
        self.image_component.style('display: none;')

    def build(self):
        # Initialize filament manager with callback
        self.filament_manager.build_dialog(on_add_callback=self.add_filament_from_manager)

        # Edit dialog
        with ui.dialog() as self.edit_dialog:
            with ui.card():
                ui.markdown('#### Edit Filament')
                self.cover_input = ui.number(label='Cover', value=0.25, format='%.2f', min=0, max=1).style('width:100%')
                self.color_input = ui.color_input(value='#000000')
                with ui.row().classes('justify-end gap-2'):
                    ui.button('Cancel', on_click=lambda: self.edit_dialog.close())
                    ui.button('Apply', on_click=lambda: self.apply_edit())
        # Filament edit dialog
        with ui.dialog() as self.filament_edit_dialog:
            with ui.card():
                ui.markdown('#### Edit Filament Max Layers')
                self.filament_edit_max_layers_input = ui.number(label='Max Layers', value=5, format='%d', min=1, max=999).style('width:100%')
                with ui.row().classes('justify-end gap-2'):
                    ui.button('Cancel', on_click=lambda: self.filament_edit_dialog.close())
                    ui.button('Apply', on_click=lambda: self.apply_filament_edit())
        # Project dialog
        with ui.dialog() as self.project_dialog:
            with ui.column():
                ui.markdown('### Open Project')
                ui.upload(on_upload=self.on_upload_project, label='Select project JSON', auto_upload=True).props('accept=".json"')
        # Build main UI
        with ui.row().classes('w-full h-screen flex-nowrap gap-0'):
            # Sidebar with logo and controls
            with ui.column().classes('flex-none w-64 gap-4 overflow-y-auto h-full bg-neutral-800 text-white overflow-x-hidden'):
                # New / Open / Save row
                with ui.row().classes('fixed pt-5 p-4 w-64 top-0 left-0 right-0 bg-neutral-900 items-center gap-2'):
                    ui.image('logo.png').classes('w-10 h-10 mr-4')
                    ui.button(icon='note_add', on_click=self.new_project).props('color=warning size=sm padding="7px 7px"').tooltip('New Project')
                    ui.button(icon='folder_open', on_click=self.open_project_switch).props('color=primary size=sm padding="7px 7px"').tooltip('Open Project')
                    if app.native.main_window:
                        with ui.dropdown_button(icon='save', split=True, on_click=self.save_project).props('size=sm padding="7px 7px"'):
                            ui.button('Save as', on_click=lambda: self.save_project(True)).props('color=primary flat ')
                    else: ui.button(icon='save', on_click=self.save_project).props('color=primary size=sm padding="7px 7px"').tooltip('Save Project')
                with ui.column().classes('flex-auto gap-0 w-64 mt-16'):
                    with ui.row().classes('items-center justify-between mb-2 mt-6 ml-4'):
                        ui.markdown('**Filament List**').classes('text-gray-300')
                        ui.button("Create", icon='add', on_click=self.filament_manager.open_dialog).props('size=sm flat').tooltip('Manage Filaments')
                    # expand able scroll area for filaments
                    with ui.scroll_area().classes("w-full m-0 p-0 bg-neutral-900 flex-auto"):
                        self.filament_container = ui.column().classes('gap-2 mb-4 w-full')
                        with self.filament_container:
                            ui.markdown('**No filaments added**').classes('text-gray-500')

                    with ui.column().classes("bg-gray-700 border-t border-gray-900  w-64 flex-none"):
                        with ui.column().classes("pt-1 pb-0 p-4 gap-0"):
                            with ui.row().classes("w-full items-center justify-between mt-3"):
                                ui.markdown('**Details**').classes('ml-1 text-gray-400')
                                self.detail_mode = ui.toggle(["◔", "◑", "◕", "●"], value="◔").props("size=lg padding='0px 10px'")
                            with ui.row().classes("w-full items-center justify-between"):
                                ui.markdown('**Resolution**').classes('mt-2 ml-1 text-gray-400')
                                self.resolution_mode = ui.toggle(["◔", "◑", "◕", "●"], value="◔").props("size=lg padding='0px 10px'")


                            with ui.row().classes('items-center mt-2 justify-center'):
                                self.redraw_button = ui.button('Redraw', icon='refresh', on_click=lambda: asyncio.create_task(self.on_redraw())).props('color=primary size=sm')
                                self.export_button = ui.button('Export', icon='download', on_click=self.on_export).props('color=secondary size=sm')
                                self.export_button.disable()
                            self.progress_bar = ui.linear_progress(value=0).style('width:100%').classes("mt-2")
                            self.progress_bar.visible = False

                        with ui.expansion('Export settings', icon='settings').classes('bg-gray-700 border-t border-gray-900  w-64 p-0'):
                            self.layer_input = ui.number(label='Layer height (mm)', value=0.12, format='%.2f', step=0.02, min=0.001, max=10, on_change=self.on_layer_height_change).classes(
                                'w-full')
                            self.base_input = ui.number(label='Base layers', value=3, format='%d', min=1, max=999).props(
                                'icon=layers').classes('w-full')
                            self.size_input = ui.number(label='Max size (cm)', value=10, format='%.1f', min=0.1, max=1000000).props(
                                'icon=straighten').classes('w-full')



            # Main area
            with ui.column().classes('flex-auto items-center justify-center overflow-y-auto h-full') as main_area:
                self.placeholder = ui.column().classes('items-center justify-center h-full gap-4 w-80').style('display: flex;')
                with self.placeholder:
                    ui.markdown('**No image loaded**').classes('text-gray-500')
                    self.upload_image = ui.upload(max_files=1, auto_upload=True, on_upload=lambda files: self.handle_upload(files)).props(
                        'label="Load Image" accept="image/*"').classes('w-full')

                    # floating tutorial in bottom left corner
                    infotext_start = ui.column().classes('absolute bottom-4 left-80 text-gray-500 text-sm')
                    with infotext_start:
                        # arrow to the left
                        ui.icon('arrow_right').classes('text-gray-500 text-2xl')

                self.image_component = ZoomableImage(
                    src='/static/photo.jpg',
                    on_pixel=self.handle_image_click,
                ).classes('w-full h-full')

                with ui.row().classes("fixed top-4 left-64 right-72 ml-4 mr-4"):
                    # Live preview checkbox in top left corner
                    with ui.row().classes("z-50 text-white p-2 rounded").style("background-color: rgba(0, 0, 0, 0.75);"):
                        self.live_preview_checkbox = ui.checkbox('Live Preview', value=True, on_change=lambda e: self.toggle_live_preview(e.value)).tooltip('Enable live preview mode for faster updates')
                        ui.button(icon='fit_screen', on_click=self.image_component.reset_transform).tooltip("Recenter preview").props("flat round")

                with ui.row().classes("fixed top-4 "):
                    with ui.row().classes("flex-grow justify-center p-2"):
                        self.status_banner = ui.label().classes('z-50 text-sm rounded p-2')
                        self.status_banner.set_visibility(False)

                ui.button(icon='cleaning_services', on_click=self.reset_image).props('flat round').classes('fixed bottom-4 right-4 z-50').tooltip('Reset')

            # Position info card
            with ui.column().classes('flex-none top-0 right-0 p-4 w-72 h-full overflow-y-auto bg-neutral-900 border-l border-gray-900') as self.position_info_wrapper:
                ui.button(
                    icon='close',
                    on_click=lambda: setattr(self.position_info_wrapper, 'visible', False)
                ).classes('absolute top-4 right-4 z-50').props('flat round size=sm').tooltip('Close position info')
                self.position_info_content = ui.column()
            self.position_info_wrapper.visible = False

        # Enable dark mode and adjust padding
        ui.dark_mode().enable()
        ui.query('.nicegui-content').classes('p-0')

    def update_max_layers(self, idx, new_value):
        """Update max_layers value for a filament directly from the UI input"""
        if 0 <= idx < len(self.filaments):
            self.filaments[idx]['max_layers'] = new_value
            # Trigger live preview update
            if self.live_preview_enabled:
                asyncio.create_task(self.update_live_preview())

    async def update_live_preview(self):
        """Update live preview using only generate_shades_td and segment_to_shades"""
        if self.original_image is None or len(self.filaments) < 2:
            return

        # If already updating, mark restart as pending and return
        if self.live_preview_updating:
            self.live_preview_restart_pending = True
            return

        # Start updating
        self.live_preview_updating = True

        while True:
            # Clear restart pending flag at start of each iteration
            self.live_preview_restart_pending = False

            try:
                # Extract filament data
                colors = []
                max_layers = []
                td_values = []
                self.last_input_colors = []
                for f in self.filaments:
                    manager_id = f.get('id', None)
                    data = f.get('copied_data', {})
                    if manager_id is not None:
                        f_data, _ = self.filament_manager.find_filament_by_id(manager_id)
                        if f_data:
                            data = f_data
                    color = data.get('color', '#000000')
                    color = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
                    colors.append(color)
                    self.last_input_colors.append(color)
                    instance_max_layers = f.get('max_layers', data.get('max_layers', 5))
                    max_layers.append(instance_max_layers)
                    td_values.append(data.get('td_value', 0.5))

                def compute_live_preview():
                    shades = generate_shades_td(colors, td_values, max_layers, float(self.layer_input.value))
                    segmented = segment_to_shades(self.original_image, shades)
                    return segmented, shades

                loop = asyncio.get_running_loop()
                self.live_preview_segmented, self.filament_shades = await loop.run_in_executor(None, compute_live_preview)

                # Update image display
                buf = io.BytesIO()
                self.live_preview_segmented.save(buf, format='PNG')
                data = base64.b64encode(buf.getvalue()).decode()
                self.image_component.set_source(f'data:image/png;base64,{data}')
                self.rendered_image = self.live_preview_segmented

                # Keep export button disabled for live preview
                self.export_button.disable()

                self.status_banner.set_text("Live preview")
                self.status_banner.clear()
                with self.status_banner:
                    ui.tooltip("The preview you see might not be fully accurate, use 'Redraw' to generate a full preview.")
                self.status_banner.style('background-color: rgba(204, 102, 0,0.75); color:white;')
                self.status_banner.set_visibility(True)

            except Exception as e:
                ui.notify(f'Live preview error: {str(e)}', color='orange')

            # Check if restart is needed
            if not self.live_preview_restart_pending:
                break

        # Mark update as finished
        self.live_preview_updating = False

    def toggle_live_preview(self, enabled):
        """Toggle live preview mode"""
        self.live_preview_enabled = enabled
        if enabled:
            # Switch to live preview mode
            if self.original_image and len(self.filaments) >= 2:
                asyncio.create_task(self.update_live_preview())
            # Disable export button in live preview mode
            self.export_button.disable()
        else:
            # Switch back to original image or last full render
            if self.rendered_image:
                # Show last full render
                buf = io.BytesIO()
                self.rendered_image.save(buf, format='PNG')
                data = base64.b64encode(buf.getvalue()).decode()
                self.image_component.set_source(f'data:image/png;base64,{data}')
                # Enable export if we have polygons
                if self.polygons:
                    self.export_button.enable()
            elif self.original_image:
                # Show original image
                buf = io.BytesIO()
                self.original_image.save(buf, format='PNG')
                data = base64.b64encode(buf.getvalue()).decode()
                self.image_component.set_source(f'data:image/png;base64,{data}')

    def on_layer_height_change(self, e):
        """Handle layer height changes and trigger live preview"""
        if self.live_preview_enabled:
            asyncio.create_task(self.update_live_preview())
