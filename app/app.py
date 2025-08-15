from nicegui import ui, app
from PIL import Image
import io, base64, asyncio, zipfile

from lib.mask_creation import segment_to_shades, generate_shades_td
from lib.filament_manager import FilamentManager
from lib.mesh_generator import create_layered_polygons_parallel, render_polygons_to_pil_image, polygons_to_meshes_parallel
from lib.render_utils import render_polygons_to_svg

from app.components import (
    FilamentPanel, ControlsPanel, StatusBanner, ImageViewer,
    PositionInfo, ProjectIO, LivePreviewController
)

class StratumApp:
    def __init__(self):
        # Services
        self.filament_manager = FilamentManager()

        # Core state shared across components
        self.original_image: Image.Image | None = None
        self.segmented_image = None
        self.rendered_image = None
        self.rendered_image_size = None
        self.polygons = None
        self.filament_shades = None
        self.last_input_colors = []

        # Components -------------------------------------------------------
        self.banner = StatusBanner()
        with ui.row().classes('w-full h-screen flex-nowrap gap-0'):
            # Sidebar
            with ui.column().classes('flex-none w-64 gap-4 overflow-y-auto h-full bg-neutral-800 text-white overflow-x-hidden'):
                with ui.row().classes('fixed pt-5 p-4 w-64 top-0 left-0 right-0 bg-neutral-900 items-center gap-2'):
                    ui.image('logo.png').classes('w-10 h-10 mr-4')
                    ui.button(icon='note_add', on_click=self.new_project).props('color=warning size=sm padding="7px 7px"').tooltip('New Project')
                    # Project IO
                    self.project_io = ProjectIO(
                        get_project_data=self._gather_project_data,
                        set_project_data=self._apply_project_data,
                        set_image_from_bytes=self._set_image_from_bytes,
                    )
                    ui.button(icon='folder_open', on_click=self.project_io.open_native).props('color=primary size=sm padding="7px 7px"').tooltip('Open Project')
                    if app.native.main_window:
                        with ui.dropdown_button(icon='save', split=True, on_click=lambda: asyncio.create_task(self.project_io.save(False))).props('size=sm padding="7px 7px"'):
                            ui.button('Save as', on_click=lambda: asyncio.create_task(self.project_io.save(True))).props('color=primary flat ')
                    else:
                        ui.button(icon='save', on_click=lambda: asyncio.create_task(self.project_io.save(False))).props('color=primary size=sm padding="7px 7px"').tooltip('Save Project')

                # Filaments panel
                self.filaments_panel = FilamentPanel(
                    filament_manager=self.filament_manager,
                    on_change=lambda _: asyncio.create_task(self._on_filaments_changed()),
                )
                # Controls panel
                self.controls = ControlsPanel(
                    on_redraw=lambda: asyncio.create_task(self._on_redraw()),
                    on_export=lambda: asyncio.create_task(self._on_export()),
                    on_settings_change=lambda: asyncio.create_task(self._maybe_live_preview()),
                )

            # Main area
            with ui.column().classes('flex-auto items-center justify-center overflow-y-auto h-full'):
                self.viewer = ImageViewer(on_pixel=self._on_pixel_click, on_upload_image=self._on_upload_image)
                with ui.row().classes('fixed top-4 left-64 right-72 ml-4 mr-4'):
                    with ui.row().classes('z-50 text-white rounded').style('background-color: rgba(0, 0, 0, 0.75);'):
                        self.live_preview_checkbox = ui.checkbox('Live Preview', value=True, on_change=lambda e: self._toggle_live_preview(e.value)).tooltip('Enable live preview mode for faster updates')
                        ui.button(icon='fit_screen', on_click=self.viewer.reset_transform).tooltip('Recenter preview').props('flat round')
                        with ui.dropdown_button(icon='image', auto_close=True).props('flat round').tooltip('Image tools'):
                            ui.item('Replace Image', on_click=self._reset_image)

                self.position_info = PositionInfo()

        ui.dark_mode().enable(); ui.query('.nicegui-content').classes('p-0')

        # Live preview controller (pulls state via lambdas)
        self.live = LivePreviewController(
            get_image=lambda: self.original_image,
            get_filaments=self.filaments_panel.get_filaments,
            get_layer_height=lambda: float(self.controls.layer_input.value),
            compute_shades=generate_shades_td,
            segment_image=segment_to_shades,
            on_render=self._apply_live_render,
            on_status_live=lambda: self.banner.show('Live preview', color='background-color: rgba(204, 102, 0,0.75); color:white;', tooltip="Preview may be approximate; use 'Redraw' for final."),
            on_after_change=lambda: self.controls.enable_export(False),
        )

    # ---------------------- Image & clicks --------------------------------
    def _on_upload_image(self, img: Image.Image):
        self.original_image = img
        self.viewer.set_pil(img, reset=True)
        self.viewer.set_max_size(self.controls.size_input.value)
        self.viewer.show_placeholder(False)
        asyncio.create_task(self._maybe_live_preview())

    def _set_image_from_bytes(self, data: bytes):
        img = Image.open(io.BytesIO(data)).convert('RGBA')
        self._on_upload_image(img)

    def _reset_image(self):
        self.original_image = None
        self.segmented_image = None
        self.polygons = None
        self.rendered_image_size = None
        self.filament_shades = None
        self.rendered_image = None
        self.viewer.show_placeholder(True)

    def _on_pixel_click(self, e):
        if not self.rendered_image or not self.filament_shades:
            ui.notify('Generate the preview first', color='orange'); return
        r,g,b = e.args['detail']['rgb']['r'], e.args['detail']['rgb']['g'], e.args['detail']['rgb']['b']
        x,y = e.args['detail']['coords']['x'], e.args['detail']['coords']['y']
        shade = layer = None
        for layer_idx, shades in enumerate(self.filament_shades):
            for shade_idx, s in enumerate(shades):
                if s == (r,g,b):
                    shade, layer = shade_idx, layer_idx; break
        if layer is None:
            return
        self.position_info.show((x,y), shade, layer, self.filament_shades, self.last_input_colors, int(self.controls.base_input.value))

    # ---------------------- Project IO ------------------------------------
    def _gather_project_data(self) -> dict:
        project = {
            'filaments': self.filaments_panel.get_filaments(),
            'settings': self.controls.get_settings(),
        }
        if self.original_image:
            buf = io.BytesIO(); self.original_image.save(buf, format='PNG')
            project['image'] = base64.b64encode(buf.getvalue()).decode()
        return project

    def _apply_project_data(self, project: dict):
        self.filaments_panel.set_filaments(project.get('filaments', []))
        s = project.get('settings', {})
        self.controls.layer_input.value = s.get('layer_height', 0.2)
        self.controls.base_input.value = s.get('base_layers', 3)
        self.controls.size_input.value = s.get('max_size_cm', 10.0)
        self.controls.resolution_mode.value = s.get('resolution_mode', '◔')
        self.controls.detail_mode.value = s.get('detail_mode', '◔')
        asyncio.create_task(self._maybe_live_preview())

    # ---------------------- Live preview hooks ----------------------------
    async def _maybe_live_preview(self):
        if self.live.enabled:
            await self.live.update()

    async def _on_filaments_changed(self):
        await self._maybe_live_preview()

    def _toggle_live_preview(self, enabled: bool):
        self.live.set_enabled(enabled)
        if not enabled:
            if self.rendered_image:
                self.viewer.set_pil(self.rendered_image)
                if self.polygons:
                    self.controls.enable_export(True)
            elif self.original_image:
                self.viewer.set_pil(self.original_image)

    def _apply_live_render(self, png_bytes: bytes):
        self.rendered_image = Image.open(io.BytesIO(png_bytes))
        self.viewer.set_pil(self.rendered_image)
        self.viewer.set_max_size(self.controls.size_input.value)

    # ---------------------- Heavy redraw/export ---------------------------
    async def _on_redraw(self):
        if self.original_image is None or len(self.filaments_panel.get_filaments()) < 2:
            ui.notify('Load image and add at least two filaments', color='red'); return
        self.controls.set_busy(True)

        # collect inputs
        colors, max_layers, td_values = [], [], []
        self.last_input_colors = []
        for f in self.filaments_panel.get_filaments():
            data = f.get('copied_data', {})
            color = tuple(int(data.get('color', '#000000')[i:i+2], 16) for i in (1,3,5))
            self.last_input_colors.append(color)
            colors.append(color)
            max_layers.append(f.get('max_layers', data.get('max_layers', 5)))
            td_values.append(data.get('td_value', 0.5))

        img_width, img_height = self.original_image.size
        total_pixels = img_width * img_height
        base_pixels = 1000 * 1000
        resolution_scale = (total_pixels / base_pixels) ** 0.5
        BASE_RES_PRESETS = {
            '◔': {'simplify_tol': 1.0, 'marching_squares_level': 0.5},
            '◑': {'simplify_tol': 0.5, 'marching_squares_level': 0.25},
            '◕': {'simplify_tol': 0.1, 'marching_squares_level': 0.05},
            '●': {'simplify_tol': 0.01, 'marching_squares_level': 0.5},
        }
        BASE_DETAIL_PRESETS = {
            '◔': {'min_area': 3},
            '◑': {'min_area': 1},
            '◕': {'min_area': 0.5},
            '●': {'min_area': 0.1},
        }
        base_res = BASE_RES_PRESETS[self.controls.resolution_mode.value]
        base_detail = BASE_DETAIL_PRESETS[self.controls.detail_mode.value]
        simplify_tol = max(0.001, min(10.0, base_res['simplify_tol'] / resolution_scale))
        marching_squares_level = max(0.005, min(1.0, base_res['marching_squares_level'] / resolution_scale))
        min_area = max(0.01, min(100.0, base_detail['min_area'] * resolution_scale))

        def compute():
            shades = generate_shades_td(colors, td_values, max_layers, float(self.controls.layer_input.value))
            segmented = segment_to_shades(self.original_image, shades)
            polys = create_layered_polygons_parallel(
                segmented, shades,
                progress_cb=lambda v: setattr(self.controls.progress_bar, 'value', v * 0.5),
                min_area=min_area, simplify_tol=simplify_tol, marching_squares_level=marching_squares_level,
            )
            img = render_polygons_to_pil_image(
                polys, shades, segmented.size, max_size=self.controls.size_input.value,
                progress_cb=lambda v: setattr(self.controls.progress_bar, 'value', 0.5 + 0.5 * v),
            )
            return segmented, polys, img, shades

        loop = asyncio.get_running_loop()
        self.segmented_image, self.polygons, img, self.filament_shades = await loop.run_in_executor(None, compute)
        self.rendered_image = img
        self.rendered_image_size = img.size
        self.viewer.set_pil(img, reset=True)
        self.viewer.set_max_size(self.controls.size_input.value)

        self.controls.set_busy(False)
        self.controls.enable_export(True)
        self.banner.show('Fully rendered preview', color='background-color: rgba(0,204,0,0.75); color:black;', tooltip='This preview is fully rendered and ready for export.')

    async def _on_export(self):
        if not self.polygons:
            ui.notify('Nothing to export', color='red'); return
        self.controls.set_busy(True)

        def compute_meshes():
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                meshes = polygons_to_meshes_parallel(
                    self.segmented_image,
                    self.polygons,
                    layer_height=float(self.controls.layer_input.value),
                    target_max_cm=float(self.controls.size_input.value),
                    base_layers=int(self.controls.base_input.value),
                    progress_cb=lambda v: setattr(self.controls.progress_bar, 'value', v),
                )
                for idx, mesh in enumerate(meshes):
                    stl_buf = io.BytesIO(); mesh.export(file_obj=stl_buf, file_type='stl')
                    archive.writestr(f'mesh_{idx}.stl', stl_buf.getvalue())
            return buf

        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(None, compute_meshes)
        buf.seek(0)
        self.controls.set_busy(False)
        self.controls.enable_export(True)
        if app.native.main_window:
            import webview
            result = await app.native.main_window.create_file_dialog(webview.SAVE_DIALOG, save_filename='meshes.zip')
            if not result:
                return
            file = result[0]
            try:
                with open(file, 'wb') as f:
                    f.write(buf.getvalue())
                ui.notify(f'Meshes exported to {file}', color='green')
            except Exception as e:
                ui.notify(f'Error exporting meshes: {str(e)}', color='red')
        else:
            ui.download.content(buf.getvalue(), 'meshes.zip')

    # ---------------------- Utilities ------------------------------------
    def new_project(self):
        self.filaments_panel.set_filaments([])
        self.original_image = None
        self.segmented_image = None
        self.polygons = None
        self.viewer.show_placeholder(True)
