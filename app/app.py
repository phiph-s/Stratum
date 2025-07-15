from nicegui import app,ui
from lib.mask_creation import generate_shades, segment_to_shades
from PIL import Image
import io
import asyncio
import base64
import zipfile
import json

from lib.mesh_generator import analyze_position_rgb, create_layered_polygons_parallel, render_polygons_to_pil_image, \
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
        self.last_saved_path = None

        # UI components (to be set in build)
        self.cover_input = None
        self.color_input = None
        self.edit_dialog = None
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

    def show_position_info(self, analysis_result):
        self.position_info_content.clear()
        with self.position_info_content:
            pos_x, pos_y = analysis_result['position_px']
            ui.markdown(f"**Position:** {pos_x:.0f}, {pos_y:.0f} px")
            layer_info = analysis_result['layer']
            layer_idx = layer_info['layer_index']
            if self.filament_shades:
                try:
                    import numpy as np
                    all_shades_present = []
                    shade_labels = []
                    true_colors = []
                    shade = layer_info['filaments'][0]['shade_index']
                    for i in reversed(range(shade + 1)):
                        all_shades_present.append(self.filament_shades[layer_idx][i])
                        shade_labels.append(f"{layer_idx + 1}, {i + 1}")
                        true_colors.append(self.filament_shades[layer_idx][-1])
                    for i in reversed(range(layer_idx)):
                        for j in reversed(range(len(self.filament_shades[i]))):
                            all_shades_present.append(self.filament_shades[i][j])
                            shade_labels.append(f"{i + 1}, {j + 1}")
                            true_colors.append(self.filament_shades[i][-1])
                    for i in reversed(range(self.base_input.value - 1)):
                        all_shades_present.append(self.filament_shades[0][0])
                        shade_labels.append(f"1, {i + 2}")
                        true_colors.append(self.filament_shades[0][-1])
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
                except Exception as e:
                    ui.markdown(f"**Error creating plot:** {str(e)}")
            else:
                ui.markdown("**No material at this position**")

    def handle_image_click(self, e):
        if not self.rendered_image or not self.filament_shades:
            ui.notify('Generate the preview first', color='orange')
            return
        click_x = e.image_x
        click_y = e.image_y
        try:
            analysis = analyze_position_rgb(click_x, click_y, self.rendered_image, self.filament_shades)
            self.show_position_info(analysis)
        except Exception as ex:
            ui.notify(f'Error analyzing position: {str(ex)}', color='red')

    def update_filament_list(self):
        self.filament_container.clear()
        for idx, f in enumerate(reversed(self.filaments)):
            real_idx = len(self.filaments) - 1 - idx
            with self.filament_container:
                with ui.row().classes('items-center gap-2 justify-between'):
                    with ui.row().classes('items-center gap-2'):
                        ui.html(f"<div style=\"width: 70px; height:24px; border-radius: 3px; border: 1px lightgray solid; background-color:{f['color']};\"></div>")
                        ui.button(icon='edit', on_click=lambda _, i=real_idx: self.open_edit(i)).props('flat round size=sm')
                        ui.button(icon='delete', color='red', on_click=lambda _, i=real_idx: self.remove_filament(i)).props('flat round size=sm')
                    with ui.row().classes('items-center gap-1'):
                        ui.button(icon='arrow_upward', on_click=lambda _, i=real_idx: self.move_filament(i, i+1)).props('flat round size=sm')
                        ui.button(icon='arrow_downward', on_click=lambda _, i=real_idx: self.move_filament(i, i-1)).props('flat round size=sm')
        if not self.filaments:
            with self.filament_container:
                ui.markdown('**No filaments added**').classes('text-gray-500')

    def move_filament(self, old, new):
        if 0 <= new < len(self.filaments):
            item = self.filaments.pop(old)
            self.filaments.insert(new, item)
        self.update_filament_list()

    def remove_filament(self, idx):
        self.filaments.pop(idx)
        self.update_filament_list()

    def add_filament(self):
        self.filaments.append({'color': '#000000', 'cover': 0.25})
        self.update_filament_list()

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
        colors = [tuple(int(f['color'][i:i+2], 16) for i in (1,3,5)) for f in self.filaments]
        covers = [f['cover'] for f in self.filaments]

        RES_PRESETS = {
            '◔': {'simplify_tol': 1.0, 'marching_squares_level': 0.5},
            '◑': {'simplify_tol': 0.5, 'marching_squares_level': 0.25},
            '◕':  {'simplify_tol': 0.01, 'marching_squares_level': 0.05},
            "●": {'simplify_tol': 0.001, 'marching_squares_level': 0.01}
        }
        DETAIL_PRESETS = {
            '◔': {'min_area': 3},
            '◑': {'min_area': 1},
            '◕': {'min_area': 0.5},
            '●': {'min_area': 0.1}
        }
        simplify_tol, marching_squares_level = RES_PRESETS[self.resolution_mode.value].values()
        min_area = DETAIL_PRESETS[self.detail_mode.value]['min_area']

        def compute():
            shades = generate_shades(colors, covers)
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
        self.image_component.set_source(f'data:image/png;base64,{data}')
        self.progress_bar.visible = False
        self.redraw_button.enable()
        self.export_button.enable()

    def on_export(self):
        if not self.polygons:
            ui.notify('Nothing to export', color='red')
            return
        buf = io.BytesIO()
        self.progress_bar.value = 0
        self.progress_bar.visible = True
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            meshes = polygons_to_meshes_parallel(
                self.segmented_image,
                self.polygons,
                layer_height=float(self.layer_input.value),
                target_max_cm=float(self.size_input.value),
                base_layers=int(self.base_input.value),
                progress_cb=lambda v: setattr(self.progress_bar, 'value', v)
            )
            for idx, mesh in enumerate(meshes):
                stl_buf = io.BytesIO()
                mesh.export(file_obj=stl_buf, file_type='stl')
                archive.writestr(f'mesh_{idx}.stl', stl_buf.getvalue())
        buf.seek(0)
        ui.download.content(buf.getvalue(), 'meshes.zip')
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

    def build(self):
        # Edit dialog
        with ui.dialog() as self.edit_dialog:
            with ui.card():
                ui.markdown('#### Edit Filament')
                self.cover_input = ui.number(label='Cover', value=0.25, format='%.2f', min=0, max=1).style('width:100%')
                self.color_input = ui.color_input(value='#000000')
                with ui.row().classes('justify-end gap-2'):
                    ui.button('Cancel', on_click=lambda: self.edit_dialog.close())
                    ui.button('Apply', on_click=lambda: self.apply_edit())
        # Project dialog
        with ui.dialog() as self.project_dialog:
            with ui.column():
                ui.markdown('### Open Project')
                ui.upload(on_upload=self.on_upload_project, label='Select project JSON', auto_upload=True).props('accept=".json"')
        # Build main UI
        with ui.row().classes('w-full h-screen flex-nowrap'):
            # Sidebar with logo and controls
            with ui.column().classes('flex-none w-72 gap-4 overflow-y-auto h-full bg-neutral-800 text-white overflow-x-hidden'):
                # New / Open / Save row
                with ui.row().classes('fixed pt-5 p-4 w-72 top-0 left-0 right-0 bg-neutral-900 items-center gap-2'):
                    ui.image('logo.png').classes('w-10 h-10 mr-4')
                    ui.button(icon='note_add', on_click=self.new_project).props('color=warning size=sm padding="7px 7px"').tooltip('New Project')
                    ui.button(icon='folder_open', on_click=self.open_project_switch).props('color=primary size=sm padding="7px 7px"').tooltip('Open Project')
                    if app.native.main_window:
                        with ui.dropdown_button(icon='save', split=True, on_click=self.save_project).props('size=sm padding="7px 7px"'):
                            ui.button('Save as', on_click=lambda: self.save_project(True)).props('color=primary flat ')
                    else: ui.button(icon='save', on_click=self.save_project).props('color=primary size=sm padding="7px 7px"').tooltip('Save Project')
                with ui.column().classes('flex-auto p-4 gap-2 w-72 mt-16 mb-32'):
                    ui.markdown('**Filament Management**').classes('mb-0 m-1 text-gray-300')
                    with ui.scroll_area().classes("w-full m-0 p-0 h-72 bg-neutral-900"):
                        self.filament_container = ui.column().classes('gap-2 mb-4')
                        with self.filament_container:
                            ui.markdown('**No filaments added**').classes('text-gray-500')
                    ui.button("Add filament", icon='add', on_click=self.add_filament).props('size=sm').tooltip('Add Filament').classes('w-full')
                    ui.space()
                    with ui.scroll_area().classes("w-full m-0 p-0 h-64 bg-neutral-900"):
                        self.layer_input = ui.number(label='Layer height (mm)', value=0.2, format='%.2f').classes('w-full')
                        self.base_input = ui.number(label='Base layers', value=3, format='%d').props('icon=layers').classes('w-full')
                        self.size_input = ui.number(label='Max size (cm)', value=10, format='%.1f').props('icon=straighten').classes('w-full')
                with ui.column().classes("fixed pt-1 p-4 bottom-0 gap-0 left-0 right-0 bg-gray-700 border-t border-gray-900 w-72"):
                    with ui.row().classes("w-full items-center justify-between mt-3"):
                        ui.markdown('**Details**').classes('ml-1 text-gray-400')
                        self.detail_mode = ui.toggle(["◔", "◑", "◕", "●"], value="◔").props("size=lg padding='0px 10px'")
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.markdown('**Resolution**').classes('mt-2 ml-1 text-gray-400')
                        self.resolution_mode = ui.toggle(["◔", "◑", "◕", "●"], value="◔").props("size=lg padding='0px 10px'")


                    with ui.row().classes('items-center gap-2 mt-2'):
                        self.redraw_button = ui.button('Redraw', icon='refresh', on_click=lambda: asyncio.create_task(self.on_redraw())).props('color=primary')
                        self.export_button = ui.button('Export', icon='download', on_click=self.on_export).props('color=secondary')
                        self.export_button.disable()
                    self.progress_bar = ui.linear_progress(value=0).style('width:100%').classes("mt-2")
                    self.progress_bar.visible = False

            # Main area
            with ui.column().classes('flex-auto items-center justify-center p-4 overflow-y-auto h-full'):
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

                self.image_component = ui.interactive_image(cross='blue', events=['mousedown'], on_mouse=lambda e: self.handle_image_click(e)).classes('max-h-full')
                self.image_component.props('fit=scale-down')
                self.image_component.visible = False

                with self.image_component:
                    def reset_image():
                        self.original_image = None
                        self.segmented_image = None
                        self.polygons = None
                        self.rendered_image_size = None
                        self.filament_shades = None
                        self.rendered_image = None
                        self.placeholder.visible = True
                        self.image_component.visible = False

                    ui.button(icon='cleaning_services', on_click=reset_image).props('flat round').classes('fixed bottom-4 right-4 z-50').tooltip('Reset')

            # Position info card
            with ui.column().classes('flex-none top-0 right-0 p-4 w-80 h-full overflow-y-auto bg-neutral-900 border-l border-gray-900'):
                self.position_info_content = ui.column()

        # Enable dark mode and adjust padding
        ui.dark_mode().enable()
        ui.query('.nicegui-content').classes('p-0')
