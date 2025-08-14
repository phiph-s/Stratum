from typing import Tuple, List, Optional
from nicegui import ui
import numpy as np

class PositionInfo:
    def __init__(self):
        with ui.column().classes('fixed top-4 right-4 p-1 rounded w-72 overflow-y-auto').style('background-color: rgba(0, 0, 0, 0.75);') as wrapper:
            ui.button(icon='close', on_click=lambda: setattr(wrapper, 'visible', False)).classes('absolute top-4 right-4 z-50').props('flat round size=sm').tooltip('Close position info')
            self.content = ui.column()
        self.wrapper = wrapper
        self.wrapper.visible = False

    def show(self, pos: Tuple[int, int], shade: Optional[int], layer_idx: Optional[int], filament_shades: Optional[List[List[tuple]]], last_input_colors: List[tuple], base_layers: int):
        self.content.clear()
        self.wrapper.visible = True
        with self.content:
            pos_x, pos_y = pos
            ui.markdown(f"**Position:** {pos_x:.0f}, {pos_y:.0f} px").classes('ml-3 mt-1 text-sm').style('margin-bottom: -20px;')
            if filament_shades:
                all_shades_present = []
                shade_labels = []
                true_colors = []
                for i in reversed(range(shade + 1)):
                    all_shades_present.append(filament_shades[layer_idx][i])
                    shade_labels.append(f"{layer_idx + 1}, {i + 1}")
                    true_colors.append(last_input_colors[layer_idx])
                for i in reversed(range(layer_idx)):
                    for j in reversed(range(len(filament_shades[i]))):
                        all_shades_present.append(filament_shades[i][j])
                        shade_labels.append(f"{i + 1}, {j + 1}")
                        true_colors.append(last_input_colors[i])
                for i in reversed(range(base_layers - 1)):
                    all_shades_present.append(filament_shades[0][0])
                    shade_labels.append(f"1, {i + 2}")
                    true_colors.append(last_input_colors[0])
                if all_shades_present:
                    with ui.matplotlib(figsize=(3, 3.5), facecolor=(0,0,0,0)).figure as fig:
                        ax = fig.gca()
                        y_positions = np.arange(len(all_shades_present))
                        shaded_norm = [(r/255, g/255, b/255) for r,g,b in all_shades_present]
                        true_norm = [(r/255, g/255, b/255) for r,g,b in true_colors]
                        bar_w = 0.5
                        ax.barh(y_positions, [bar_w]*len(all_shades_present), left=[0]*len(all_shades_present), color=shaded_norm, edgecolor='black', linewidth=0.5, label='calculated color')
                        ax.barh(y_positions, [bar_w]*len(all_shades_present), left=[bar_w]*len(all_shades_present), color=true_norm, edgecolor='black', linewidth=0.5, label='true filament color')
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
                                ax.text(0.25, i, str(tuple(shaded_rgb)), ha='center', va='center', fontweight='bold', fontsize=8, color='white' if sum(shaded_rgb) < 384 else 'black')
                                ax.text(0.75, i, str(tuple(true_rgb)), ha='center', va='center', fontweight='bold', fontsize=8, color='white' if sum(true_rgb) < 384 else 'black')
                        fig.tight_layout()
            else:
                ui.markdown('**No material at this position**')
