from nicegui import ui, app

from lib.mask_creation import generate_shades, segment_to_shades
from lib.mesh_generator import (
    create_layered_polygons_parallel,
    render_polygons_to_pil_image,
    polygons_to_meshes_parallel
)
from PIL import Image
import io
import asyncio
import base64
import zipfile

# Application state
filaments = []
original_image = None
segmented_image = None
polygons = None

# Helper functions

def update_filament_list(container):
    container.clear()
    for idx, f in enumerate(filaments):
        with container:
            with ui.row().classes('items-center gap-2'):
                ui.html(f'<div style="width:24px; height:24px; background-color:{f['color']}; '
                        f'border-radius:50%; border:1px solid #444;"></div>')
                ui.button(icon='arrow_upward', on_click=lambda _, i=idx: move_filament(i, i-1))
                ui.button(icon='arrow_downward', on_click=lambda _, i=idx: move_filament(i, i+1))
                ui.number(label='Cover', value=f['cover'], format='%.2f', min=0, max=1,
                          on_change=lambda e, i=idx: set_cover(i, float(e.value))).style('width:80px')
                ui.color_picker(value=f['color'], on_pick=lambda e, i=idx: set_color(i, e.color))
                ui.button('Remove', on_click=lambda _, i=idx: remove_filament(i))


def move_filament(old, new):
    if 0 <= new < len(filaments):
        item = filaments.pop(old)
        filaments.insert(new, item)
    update_filament_list(filament_container)


def set_cover(idx, value):
    filaments[idx]['cover'] = value


def set_color(idx, value):
    filaments[idx]['color'] = value
    update_filament_list(filament_container)


def remove_filament(idx):
    filaments.pop(idx)
    update_filament_list(filament_container)


def new_project():
    global filaments, original_image, segmented_image, polygons
    filaments = []
    original_image = None
    segmented_image = None
    polygons = None
    update_filament_list(filament_container)
    placeholder.visible = True
    image_component.visible = False


def handle_upload(files, image_component):
    global original_image
    content = files.content
    original_image = Image.open(content).convert('RGB')
    buf = io.BytesIO()
    original_image.save(buf, format='PNG')
    data = base64.b64encode(buf.getvalue()).decode()
    placeholder.visible = False
    image_component.visible = True
    image_component.set_source(f'data:image/png;base64,{data}')

async def on_redraw(image_component, progress_bar, spinner):
    global segmented_image, polygons
    if original_image is None or len(filaments) < 2:
        ui.notify('Load image and add at least two filaments', color='red')
        return

    progress_bar.value = 0
    progress_bar.visible = True
    spinner.visible = True

    colors = [tuple(int(f['color'][i:i+2], 16) for i in (1,3,5)) for f in filaments]
    covers = [f['cover'] for f in filaments]

    def compute():
        shades = generate_shades(colors, covers)
        segmented = segment_to_shades(original_image, shades)
        polys = create_layered_polygons_parallel(
            segmented, shades,
            progress_cb=lambda v: setattr(progress_bar, 'value', v * 0.5)
        )
        img = render_polygons_to_pil_image(
            polys, shades, segmented.size,
            progress_cb=lambda v: setattr(progress_bar, 'value', 0.5 + 0.5 * v)
        )
        return segmented, polys, img

    loop = asyncio.get_running_loop()
    segmented_image, polygons, img = await loop.run_in_executor(None, compute)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    data = base64.b64encode(buf.getvalue()).decode()
    image_component.set_source(f'data:image/png;base64,{data}')
    spinner.visible = False
    progress_bar.visible = False


def on_export(layer_in, size_in, base_in):
    if not polygons:
        ui.notify('Nothing to export', color='red')
        return
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        meshes = polygons_to_meshes_parallel(
            segmented_image,
            polygons[1:],
            layer_height=float(layer_in.value),
            target_max_cm=float(size_in.value),
            base_layers=int(base_in.value)
        )
        for idx, mesh in enumerate(meshes):
            stl_buf = io.BytesIO()
            mesh.export(file_obj=stl_buf, file_type='stl')
            archive.writestr(f'mesh_{idx}.stl', stl_buf.getvalue())
    buf.seek(0)
    ui.download(buf.getvalue(), 'meshes.zip')

# Build UI
with ui.row().classes('w-full h-screen flex-nowrap'):
    # Sidebar with logo and controls
    with ui.column().classes('flex-none w-72 p-6 gap-4 overflow-y-auto bg-gray-100'):
        ui.image('logo.png').classes('w-16 h-16')
        ui.markdown('#### Project Controls')
        ui.button('New Project', on_click=new_project).props('color=warning')
        ui.separator()
        ui.upload(on_upload=lambda files: handle_upload(files, image_component)).props('label="Load Image" accept="image/*"')
        ui.separator()
        ui.markdown('#### Filaments')
        add_btn = ui.button('Add Filament', on_click=lambda: (filaments.append({'color':'#000000','cover':0.25}), update_filament_list(filament_container)))
        filament_container = ui.column().classes('gap-2')
        ui.separator()
        ui.markdown('#### Settings')
        layer_input = ui.number(label='Layer height (mm)', value=0.2, format='%.2f')
        base_input = ui.number(label='Base layers', value=3, format='%d')
        size_input = ui.number(label='Max size (cm)', value=10, format='%.1f')
        ui.separator()
        ui.button('Redraw', on_click=lambda: on_redraw(image_component, progress_bar, spinner)).props('color=primary')
        ui.button('Export Meshes', on_click=lambda: on_export(layer_input, size_input, base_input)).props('color=secondary')
        spinner = ui.spinner()
        spinner.visible = False
        progress_bar = ui.linear_progress(value=0).style('width:100%')
        progress_bar.visible = False

    # Main area
    with ui.column().classes('flex-auto items-center justify-center p-4'):
        placeholder = ui.markdown('**No image loaded**').classes('text-gray-500')
        image_component = ui.image().style('max-width:100vw; max-height:100vh; object-fit:contain;')
        image_component.props('fit=scale-down')
        image_component.visible = False

ui.run(title='Drucken3d NiceGUI')
