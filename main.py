from nicegui import ui, app

from lib.mask_creation import generate_shades, segment_to_shades
from lib.mesh_generator import (
    create_layered_polygons_parallel,
    render_polygons_to_pil_image,
    polygons_to_meshes_parallel,
    analyze_position_rgb
)
from PIL import Image
import io
import asyncio
import base64
import zipfile
import json

@ui.page('/')
def main():
    # Application state
    filaments = []
    editing_idx = None
    original_image = None
    segmented_image = None
    polygons = None
    upload_image = None
    editing_idx = None
    quality_mode = None
    size_input = None
    rendered_image_size = None  # Store rendered image dimensions
    filament_shades = None  # Store current shades
    rendered_image = None  # Store the rendered PIL image for RGB analysis

    # Edit dialog components (defined once)
    with ui.dialog() as edit_dialog:
        with ui.card():
            ui.markdown('#### Edit Filament')
            cover_input = ui.number(label='Cover', value=0.25, format='%.2f', min=0, max=1).style('width:100%')
            color_input = ui.color_input(value='#000000')
            with ui.row().classes('justify-end gap-2'):
                ui.button('Cancel', on_click=lambda: edit_dialog.close())
                ui.button('Apply', on_click=lambda: apply_edit())

    # Position info dialog
    with ui.dialog() as position_dialog:
        with ui.card():
            ui.markdown('#### Position Information')
            position_info_content = ui.column().classes('gap-2')
            with ui.row().classes('justify-end'):
                ui.button('Close', on_click=lambda: position_dialog.close())

    def open_edit(idx):
        nonlocal editing_idx
        editing_idx = idx
        # preload values
        cover_input.value = filaments[idx]['cover']
        color_input.value = filaments[idx]['color']
        edit_dialog.open()

    def apply_edit():
        nonlocal editing_idx
        if editing_idx is None:
            return
        filaments[editing_idx]['cover'] = float(cover_input.value)
        filaments[editing_idx]['color'] = color_input.value
        update_filament_list(filament_container)
        edit_dialog.close()

    def show_position_info(analysis_result):
        """Display detailed position analysis in a dialog with enhanced visualization"""
        position_info_content.clear()
        print(analysis_result)
        with position_info_content:
            # Handle RGB-based analysis result format
            if 'position_px' in analysis_result:
                # New RGB-based analysis
                pos_x, pos_y = analysis_result['position_px']
                ui.markdown(f"**Position:** {pos_x:.0f}, {pos_y:.0f} px")

                if 'rgb_value' in analysis_result and analysis_result['rgb_value']:
                    rgb = analysis_result['rgb_value']
                    rgb_str = f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"
                    ui.markdown(f"**RGB Value:** {rgb_str}")

                    # Color swatch for the actual RGB value
                    with ui.row().classes('items-center gap-2'):
                        ui.html(f'<div style="width: 20px; height: 20px; background-color: {rgb_str}; border: 1px solid #ccc; border-radius: 3px;"></div>')
                        ui.label(f"Pixel color: {rgb_str}")

                if 'error' in analysis_result:
                    ui.markdown(f"**Error:** {analysis_result['error']}")

            else:
                # Old coordinate-based analysis (fallback)
                pos_x, pos_y = analysis_result['position_cm']
                ui.markdown(f"**Position:** {pos_x:.2f} cm, {pos_y:.2f} cm")

            if analysis_result['has_material']:
                ui.markdown(f"**Total Layers:** {analysis_result['total_layers']}")

                # Find the topmost filament and show its real (unshaded) color
                topmost_layer = None
                topmost_filament_idx = -1

                layer_info = analysis_result['layer']
                layer_idx = layer_info['layer_index']
                if layer_idx > topmost_filament_idx:
                    topmost_filament_idx = layer_idx
                    topmost_layer = layer_info

                # Show real color of topmost filament
                if topmost_layer:  # Skip base layer
                    real_color = filaments[topmost_filament_idx]['color']  # Convert to 0-based index
                    real_rgb = tuple(int(real_color[i:i+2], 16) for i in (1,3,5))
                    real_rgb_str = f"rgb({real_rgb[0]}, {real_rgb[1]}, {real_rgb[2]})"

                    ui.markdown(f"**Topmost Filament #{topmost_filament_idx} Real Color:**")
                    with ui.row().classes('items-center gap-2'):
                        ui.html(f'<div style="width: 30px; height: 30px; background-color: {real_rgb_str}; border: 2px solid #333; border-radius: 5px;"></div>')
                        ui.label(f"Unshaded color: {real_rgb_str}")

                # Create matplotlib plot showing all shades underneath
                if filament_shades:
                    print (filament_shades)
                    try:
                        import numpy as np

                        # Collect all shades that would be present at this position
                        all_shades_present = []
                        shade_labels = []

                        layer_info = analysis_result['layer']
                        layer_idx = layer_info['layer_index']

                        # Get with index lower to current layer
                        shade = layer_info['filaments'][0]['shade_index']
                        for i in range(shade + 1):
                            all_shades_present.append(filament_shades[layer_idx][i])
                            shade_labels.append(f"Layer {layer_idx + 1} Shade {i + 1}")
                        # add all shades from layers with lower index
                        for i in reversed(range(layer_idx)):
                            # add all shades from lower layers
                            for j in reversed(range(len(filament_shades[i]))):
                                all_shades_present.append(filament_shades[i][j])
                                shade_labels.append(f"Layer {i + 1} Shade {j + 1}")


                        if all_shades_present:
                            # Create the plot using NiceGUI's matplotlib context manager
                            plot_height = max(2, len(all_shades_present) * 0.3)
                            with ui.matplotlib(figsize=(8, plot_height)).figure as fig:
                                ax = fig.gca()

                                # Create horizontal bars for each shade
                                y_positions = np.arange(len(all_shades_present))
                                colors_normalized = [(r/255, g/255, b/255) for r, g, b in all_shades_present]

                                bars = ax.barh(y_positions, [1] * len(all_shades_present),
                                             color=colors_normalized, edgecolor='black', linewidth=0.5)

                                # Customize the plot
                                ax.set_yticks(y_positions)
                                ax.set_yticklabels(shade_labels)
                                ax.set_xlabel('Shade Colors at This Position')
                                ax.set_title('Layer Stack Visualization (Bottom to Top)', fontweight='bold')
                                ax.set_xlim(0, 1)
                                ax.set_xticks([])

                                # Invert y-axis so bottom layers are at bottom
                                ax.invert_yaxis()

                                # Add RGB values as text on bars
                                for i, (bar, rgb) in enumerate(zip(bars, all_shades_present)):
                                    rgb_text = f"({rgb[0]}, {rgb[1]}, {rgb[2]})"
                                    ax.text(0.5, i, rgb_text, ha='center', va='center',
                                           fontweight='bold', color='white' if sum(rgb) < 384 else 'black')

                                fig.tight_layout()

                    except Exception as e:
                        ui.markdown(f"**Error creating plot:** {str(e)}")

                # Show detailed layer information (existing code)
                layer_info = analysis_result['layer']
                layer_idx = layer_info['layer_index']
                if layer_idx == 0:
                    ui.markdown("**Base Layer**")
                else:
                    ui.markdown(f"**Filament {layer_idx}:**")

                for filament_info in layer_info['filaments']:
                    color = filament_info['color']
                    rgb_str = f"rgb({color[0]}, {color[1]}, {color[2]})"

                    with ui.row().classes('items-center gap-2'):
                        # Color swatch
                        ui.html(f'<div style="width: 20px; height: 20px; background-color: {rgb_str}; border: 1px solid #ccc; border-radius: 3px;"></div>')
                        ui.label(f"Shade {filament_info['shade_index'] + 1}: {rgb_str}")
            else:
                ui.markdown("**No material at this position**")

        position_dialog.open()

    def handle_image_click(e):
        """Handle clicks on the interactive image using simplified RGB analysis"""
        if not rendered_image or not filament_shades:
            ui.notify('Generate the preview first', color='orange')
            return

        # Get click coordinates
        click_x = e.image_x
        click_y = e.image_y

        try:
            # Use the new simplified RGB-based analysis
            analysis = analyze_position_rgb(
                click_x, click_y,
                rendered_image,
                filament_shades
            )

            # Show the information
            show_position_info(analysis)

        except Exception as ex:
            ui.notify(f'Error analyzing position: {str(ex)}', color='red')

    # Helper functions
    def update_filament_list(container):
        container.clear()
        for idx, f in enumerate(reversed(filaments)):
            idx = len(filaments) - 1 - idx  # Reverse index to match original order
            with container:
                with ui.row().classes('items-center gap-2'):
                    ui.html(
                        f'''<div style="width: 32px; height:32px; border-radius: 50%; border: 2px lightgray solid; background-color:{f['color']}; "
                        f"border-radius:50%; border:1px solid #444;"></div>'''
                    )
                    #round
                    ui.button(icon='arrow_upward', on_click=lambda _, i=idx: move_filament(i, i + 1)).props('flat round')
                    ui.button(icon='arrow_downward', on_click=lambda _, i=idx: move_filament(i, i - 1)).props('flat round')
                    # Open edit dialog instead of inline inputs
                    ui.button(icon='edit', on_click=lambda _, i=idx: open_edit(i)).props('flat round')
                    ui.button(icon='delete', on_click=lambda _, i=idx: remove_filament(i)).props('flat round')
        if len(filaments) == 0:
            with container:
               ui.markdown('**No filaments added**').classes('text-gray-500')

    def move_filament(old, new):
        if 0 <= new < len(filaments):
            item = filaments.pop(old)
            filaments.insert(new, item)
        update_filament_list(filament_container)

    def remove_filament(idx):
        filaments.pop(idx)
        update_filament_list(filament_container)

    def new_project():
        nonlocal filaments, original_image, segmented_image, polygons
        filaments = []
        original_image = None
        segmented_image = None
        polygons = None
        update_filament_list(filament_container)
        placeholder.visible = True
        image_component.visible = False

    def save_project():
        project = {'filaments': filaments}
        if original_image:
            buf = io.BytesIO()
            original_image.save(buf, format='PNG')
            project['image'] = base64.b64encode(buf.getvalue()).decode()
        data = json.dumps(project)
        ui.download.content(data, 'project.json')

    def load_project(files):
        nonlocal filaments, original_image
        content = files.content.read().decode()
        project = json.loads(content)
        filaments = project.get('filaments', [])
        update_filament_list(filament_container)
        img_data = project.get('image')
        if img_data:
            img_bytes = base64.b64decode(img_data)
            original_image = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            buf = io.BytesIO()
            original_image.save(buf, format='PNG')
            b64 = base64.b64encode(buf.getvalue()).decode()
            placeholder.visible = False
            image_component.visible = True
            image_component.set_source(f'data:image/png;base64,{b64}')
        ui.notify('Project loaded', color='green')

    def handle_upload(files, image_component):
        nonlocal original_image
        original_image = Image.open(files.content).convert('RGB')
        buf = io.BytesIO()
        original_image.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        placeholder.visible = False
        image_component.visible = True
        image_component.set_source(f'data:image/png;base64,{b64}')
        upload_image.reset()

    async def on_redraw(image_component, progress_bar, spinner):
        nonlocal segmented_image, polygons, original_image, rendered_image_size, filament_shades, rendered_image
        if original_image is None or len(filaments) < 2:
            ui.notify('Load image and add at least two filaments', color='red')
            return
        progress_bar.value = 0
        progress_bar.visible = True
        spinner.visible = True

        colors = [tuple(int(f['color'][i:i+2], 16) for i in (1,3,5)) for f in filaments]
        covers = [f['cover'] for f in filaments]

        QUALITY_PRESETS = {
            'Fast': {'min_area': 2, 'simplify_tol': 1.0, 'marching_squares_level': 0.5},
            'Medium': {'min_area': 0.5, 'simplify_tol': 0.5, 'marching_squares_level': 0.25},
            'Best':  {'min_area': 0.1, 'simplify_tol': 0.01, 'marching_squares_level': 0.05}
        }

        print("q", QUALITY_PRESETS[quality_mode.value])

        min_area, simplify_tol, marching_squares_level  = QUALITY_PRESETS[quality_mode.value].values()

        def compute():
            shades = generate_shades(colors, covers)
            segmented = segment_to_shades(original_image, shades)
            polys = create_layered_polygons_parallel(
                segmented, shades,
                progress_cb=lambda v: setattr(progress_bar, 'value', v * 0.5),
                min_area=min_area, simplify_tol=simplify_tol, marching_squares_level=marching_squares_level
            )
            img = render_polygons_to_pil_image(
                polys, shades, segmented.size, max_size=size_input.value,
                progress_cb=lambda v: setattr(progress_bar, 'value', 0.5 + 0.5 * v)
            )
            return segmented, polys, img, shades

        loop = asyncio.get_running_loop()
        segmented_image, polygons, img, filament_shades = await loop.run_in_executor(None, compute)

        # Store rendered image and its size for RGB analysis
        rendered_image = img
        rendered_image_size = img.size

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
        progress_bar.value = 0
        progress_bar.visible = True
        spinner.visible = True
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            meshes = polygons_to_meshes_parallel(
                segmented_image,
                polygons[1:],
                layer_height=float(layer_in.value),
                target_max_cm=float(size_in.value),
                base_layers=int(base_in.value),
                progress_cb = lambda v: setattr(progress_bar, 'value', v)
            )
            for idx, mesh in enumerate(meshes):
                stl_buf = io.BytesIO()
                mesh.export(file_obj=stl_buf, file_type='stl')
                archive.writestr(f'mesh_{idx}.stl', stl_buf.getvalue())
        buf.seek(0)
        ui.download.content(buf.getvalue(), 'meshes.zip')
        spinner.visible = False
        progress_bar.visible = False

    # Build UI
    with ui.row().classes('w-full h-screen flex-nowrap'):
        # Sidebar with logo and controls
        with ui.column().classes('flex-none w-96 p-6 gap-4 overflow-y-auto h-full bg-gray-800 text-white'):
            # New / Open / Save row
            with ui.row().classes('items-center gap-2'):
                ui.image('logo.png').classes('w-16 h-16 mr-5')

                ui.button(icon='note_add', on_click=new_project).props('color=warning').tooltip('New Project')
                ui.button(icon='folder_open', on_click=lambda: project_dialog.open()).props('color=primary').tooltip('Open Project')
                ui.button(icon='save', on_click=save_project).props('color=primary').tooltip('Save Project')

            ui.separator()

            upload_image = ui.upload(max_files=1, auto_upload=True, on_upload=lambda files: handle_upload(files, image_component)).props('label="Load Image" accept="image/*"').classes('w-full')


            # Filament section
            ui.markdown('###### Filaments').classes('text-lg font-bold')

            with ui.card().tight().classes("w-full"):

                with ui.card_section():

                    filament_container = ui.column().classes('gap-2 mb-4')
                    with filament_container:
                        ui.markdown('**No filaments added**').classes('text-gray-500')

                    ui.button("Add filament", icon='add', on_click=lambda: (filaments.append({'color': '#000000', 'cover': 0.25}),
                                                            update_filament_list(filament_container))).props(
                        'size=sm').tooltip('Add Filament')

            # Settings
            ui.markdown('###### Settings')
            with ui.card().tight().classes("w-full"):
                with ui.card_section():
                    layer_input = ui.number(label='Layer height (mm)', value=0.2, format='%.2f').props('icon=height').props("input-style='width:19rem'")
                    base_input = ui.number(label='Base layers', value=3, format='%d').props('icon=layers').classes('w-full')
                    size_input = ui.number(label='Max size (cm)', value=10, format='%.1f').props('icon=straighten').classes('w-full')

            quality_mode = ui.toggle(["Fast", "Medium", "Best"], value="Fast").classes("mt-4")
            with ui.row().classes('items-center gap-2'):
                ui.button('Redraw', icon='refresh', on_click=lambda: on_redraw(image_component, progress_bar, spinner)).props('color=primary')
                ui.button('Export STLs', icon='download', on_click=lambda: on_export(layer_input, size_input, base_input)).props('color=secondary')

            spinner = ui.spinner()
            spinner.visible = False
            progress_bar = ui.linear_progress(value=0).style('width:100%')
            progress_bar.visible = False

        # Main area
        with ui.column().classes('flex-auto items-center justify-center p-4 overflow-y-auto h-full'):
            placeholder = ui.markdown('**No image loaded**').classes('text-gray-500')
            image_component = ui.interactive_image(cross='blue',events=['mousedown'], on_mouse=handle_image_click)
            image_component.props('fit=scale-down')
            image_component.visible = False

    # Project open dialog
    def on_project_upload(files):
        load_project(files)
        project_dialog.close()

    with ui.dialog() as project_dialog:
        with ui.column():
            ui.markdown('### Open Project')
            ui.upload(on_upload=on_project_upload, label='Select project JSON', auto_upload=True).props('accept=".json"')

    # Enable dark mode and adjust padding
    ui.dark_mode().enable()
    ui.query('.nicegui-content').classes('p-0')

ui.run(title='Stratum', reload=True)
