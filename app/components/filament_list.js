import "Sortable";

export default {
  template: `
    <div class="filament-list-container">
      <div v-if="filaments.length === 0" class="text-gray-500">
        <strong>No filaments added</strong>
      </div>
      <div v-else ref="sortableContainer" class="filament-items">
        <div 
          v-for="(filament, displayIdx) in reversedFilaments" 
          :key="filament.id || displayIdx"
          :data-real-idx="filament.realIdx"
          class="filament-item w-full mb-2"
          :class="getRowClasses(filament)"
          :style="getRowStyle(filament)"
        >
          <!-- Drag handle -->
          <div class="drag-handle flex-shrink-0 cursor-move p-1" style="display: flex; align-items: center;">
            <q-icon name="drag_indicator" class="text-current opacity-60" />
          </div>

          <!-- Main content area -->
          <div class="flex-grow gap-0 min-w-0" style="display: flex; flex-direction: column;">
            <!-- First row: Name with context menu -->
            <div class="items-center gap-2 w-full justify-between" style="display: flex;">
              <div 
                class="text-sm font-semibold w-32 truncate" 
                :title="getTooltip(filament)"
              >
                {{ getDisplayName(filament) }}
              </div>
              <!-- Right side: Context menu - fixed size -->
              <q-btn 
                icon="more_vert" 
                flat 
                round 
                size="sm"
                :class="getRowClasses(filament) + ' flex-shrink-0'"
                style="min-width: 32px;"
              >
                <q-menu>
                  <q-list>
                    <q-item clickable v-close-popup @click="removeFilament(filament.realIdx)">
                      <q-item-section>Remove</q-item-section>
                    </q-item>
                  </q-list>
                </q-menu>
              </q-btn>
            </div>

            <!-- Second row: Slider with icons -->
            <div v-if="filament.realIdx === 0" class="items-center gap-1 w-full flex-nowrap" style="display: flex;">
              <q-icon name="vertical_align_bottom" class="text-xs flex-shrink-0" style="padding-right: 4px;" />
              <span class="text-xs" title="The layers of the bottom layer is set in the export settings">
                First layer
              </span>
            </div>
            <div v-else class="items-center gap-1 w-full flex-nowrap" style="display: flex;">
              <q-slider
                :model-value="filament.max_layers"
                :min="1"
                :max="20"
                :color="getSliderColor(filament)"
                :label-text-color="getSliderLabelColor(filament)"
                dense
                label
                markers
                class="flex-1 min-w-0"
                style="margin-right: 4px; font-size: 0.75rem;"
                @update:model-value="updateMaxLayers(filament.realIdx, $event)"
              />
              <span class="text-xs flex-shrink-0 text-center">{{ filament.max_layers }}</span>
              <q-icon name="layers" class="text-xs flex-shrink-0" style="padding-right: 8px;" />
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  props: {
    filaments: {
      type: Array,
      default: () => []
    }
  },
  data() {
    return {
      sortable: null
    };
  },
  computed: {
    reversedFilaments() {
      return this.filaments.map((f, idx) => {
        const realIdx = this.filaments.length - 1 - idx;
        const reversedFilament = this.filaments[realIdx];
        
        // Process filament data - use copied_data if available, otherwise use direct properties
        const data = reversedFilament.copied_data || {
          name: reversedFilament.name || 'Unnamed',
          color: reversedFilament.color || '#000000',
          td_value: reversedFilament.td_value || 0.5
        };

        // Determine if this is project-specific (no id means it's project-only)
        const projectSpecific = !reversedFilament.id;

        // Get instance max_layers value (takes precedence over manager value)
        const instanceMaxLayers = reversedFilament.max_layers || data.max_layers || 5;

        return {
          ...reversedFilament,
          realIdx,
          data,
          projectSpecific,
          max_layers: instanceMaxLayers
        };
      });
    }
  },
  mounted() {
    this.initSortable();
  },
  updated() {
    this.initSortable();
  },
  beforeUnmount() {
    if (this.sortable) {
      this.sortable.destroy();
    }
  },
  methods: {
    initSortable() {
      if (this.sortable) {
        this.sortable.destroy();
      }
      
      const container = this.$refs.sortableContainer;
      if (container && this.filaments.length > 0) {
        this.sortable = new Sortable(container, {
          animation: 150,
          ghostClass: 'sortable-ghost',
          chosenClass: 'sortable-chosen',
          dragClass: 'sortable-drag',
          handle: '.drag-handle',
          onEnd: (evt) => {
            const oldIndex = evt.oldIndex;
            const newIndex = evt.newIndex;
            
            // Convert display indices to real indices
            const realOldIdx = this.reversedFilaments[oldIndex].realIdx;
            const realNewIdx = this.reversedFilaments[newIndex].realIdx;
            
            this.$emit('reorder', { oldIndex: realOldIdx, newIndex: realNewIdx });
          }
        });
      }
    },
    getRowClasses(filament) {
      let classes = 'items-center gap-1 p-1 rounded';
      if (this.isBright(filament.data.color)) {
        classes += ' text-black';
      } else {
        classes += ' text-white border border-gray-400';
      }
      return classes;
    },
    getRowStyle(filament) {
      return {
        backgroundColor: filament.data.color || '#000000',
        display: 'flex',
        width: '100%'
      };
    },
    getDisplayName(filament) {
      const add = filament.projectSpecific ? "* " : "";
      return add + (filament.data.name || 'Unnamed');
    },
    getTooltip(filament) {
      let tooltip = filament.data.name || 'Unnamed';
      if (filament.projectSpecific) {
        tooltip += " (not in library)";
      }
      return tooltip;
    },
    getSliderColor(filament) {
      return this.isBright(filament.data.color) ? 'black' : 'white';
    },
    getSliderLabelColor(filament) {
      return this.isBright(filament.data.color) ? 'white' : 'black';
    },
    isBright(colorHex) {
      try {
        const r = parseInt(colorHex.slice(1, 3), 16);
        const g = parseInt(colorHex.slice(3, 5), 16);
        const b = parseInt(colorHex.slice(5, 7), 16);
        return (r + g + b) / 3 > 128;
      } catch {
        return false;
      }
    },
    moveFilament(oldIdx, newIdx) {
      this.$emit('move', { oldIndex: oldIdx, newIndex: newIdx });
    },
    removeFilament(idx) {
      this.$emit('remove', idx);
    },
    updateMaxLayers(idx, value) {
      this.$emit('update-max-layers', { index: idx, value: parseInt(value) });
    }
  }
};
