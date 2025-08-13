<template>
  <div
    ref="container"
    class="viewer-container w-full h-full overflow-hidden select-none relative"
    :style="containerStyle"
    @wheel="onWheel"
    @mousedown="onMouseDown"
    @click="onClick"
  >
    <!-- Raster image element -->
    <img
      v-if="!isSvg"
      ref="img"
      style="max-width: none; max-height: none;"
      :src="currentSrc"
      :style="imgStyle"
      @load="onImgLoad"
      draggable="false"
    />
    <!-- SVG container -->
    <div
      v-else
      ref="svgContainer"
      :style="imgStyle"
      v-html="svgContent"
      @load="onSvgLoad"
    ></div>
    <canvas ref="canvas" style="display:none"></canvas>
  </div>
</template>

<script>
export default {
  name: 'ZoomableImage',
  props: {
    src: { type: String, required: true },
  },
  data() {
    return {
      naturalSize: { w: 0, h: 0 },
      scale: 1,
      minScale: 0.1,
      maxScale: 10,
      translate: { x: 0, y: 0 },
      dragging: false,
      lastMouse: { x: 0, y: 0 },
      isSvg: false,
      svgContent: '',
      currentSrc: '',
    };
  },
  computed: {
    // Background checkerboard pattern
    containerStyle() {
      return {
        backgroundColor: '#8a8a8a',
        backgroundImage:
          'radial-gradient(ellipse at center, transparent 30%, rgba(0,0,0,0.2) 70%, rgba(0,0,0,0.4) 100%), ' +
          'linear-gradient(45deg, #666 25%, transparent 25%, transparent 75%, #666 75%, #666), ' +
          'linear-gradient(45deg, #666 25%, transparent 25%, transparent 75%, #666 75%, #666)',
        backgroundSize: '100% 100%, 20px 20px, 20px 20px',
        backgroundPosition: '0 0, 0 0, 10px 10px',
      };
    },
    // Transform & sizing for <img>
    imgStyle() {
      return {
        transform: `translate(${this.translate.x}px, ${this.translate.y}px) scale(${this.scale})`,
        transformOrigin: '0 0',
        userSelect: 'none',
        pointerEvents: 'none',
      };
    },
  },
  watch: {
    // When src is changed externally via prop, update internal currentSrc
    src(newVal) {
      this.currentSrc = newVal;
      this.checkContentType();
    },
  },
  mounted() {
    this.currentSrc = this.src;
    this.checkContentType();
    if (this.$refs.img && this.$refs.img.complete) this.onImgLoad();
  },
  methods: {
    /* ---------------------------------------
     * Content type detection and handling
     * -------------------------------------*/
    checkContentType() {
      if (!this.currentSrc) return;

      // Check if it's SVG data URL or inline SVG
      if (this.currentSrc.startsWith('data:image/svg+xml') || this.currentSrc.startsWith('<svg')) {
        this.isSvg = true;
        this.loadSvgContent();
      } else {
        this.isSvg = false;
      }
    },

    async loadSvgContent() {
      try {
        if (this.currentSrc.startsWith('data:image/svg+xml')) {
          // Decode data URL
          const base64Data = this.currentSrc.split(',')[1];
          this.svgContent = atob(base64Data);
        } else if (this.currentSrc.startsWith('<svg')) {
          // Direct SVG content
          this.svgContent = this.currentSrc;
        } else {
          // External SVG file
          const response = await fetch(this.currentSrc);
          this.svgContent = await response.text();
        }

        // Parse SVG dimensions
        this.$nextTick(() => {
          this.parseSvgDimensions();
        });
      } catch (error) {
        console.error('Error loading SVG:', error);
      }
    },

    parseSvgDimensions() {
      const svgElement = this.$refs.svgContainer?.querySelector('svg');
      if (svgElement) {
        // Try to get dimensions from SVG attributes
        let width = svgElement.getAttribute('width');
        let height = svgElement.getAttribute('height');

        // If no width/height, try viewBox
        if (!width || !height) {
          const viewBox = svgElement.getAttribute('viewBox');
          if (viewBox) {
            const [, , vbWidth, vbHeight] = viewBox.split(' ').map(Number);
            width = width || vbWidth;
            height = height || vbHeight;
          }
        }

        // Convert to numbers, removing units
        this.naturalSize = {
          w: parseFloat(width) || 100,
          h: parseFloat(height) || 100,
        };

        this.onContentLoad();
      }
    },

    /* ---------------------------------------
     * Utility helpers
     * -------------------------------------*/
    clamp(v, min, max) {
      return Math.min(Math.max(v, min), max);
    },
    redrawCanvas() {
      const ctx = this.$refs.canvas.getContext('2d');
      ctx.clearRect(0, 0, this.naturalSize.w, this.naturalSize.h);

      if (this.isSvg) {
        // For SVG, create an image from the SVG content
        const svgBlob = new Blob([this.svgContent], { type: 'image/svg+xml' });
        const url = URL.createObjectURL(svgBlob);
        const img = new Image();
        img.onload = () => {
          ctx.drawImage(img, 0, 0, this.naturalSize.w, this.naturalSize.h);
          URL.revokeObjectURL(url);
        };
        img.src = url;
      } else {
        ctx.drawImage(
          this.$refs.img,
          0,
          0,
          this.naturalSize.w,
          this.naturalSize.h,
        );
      }
    },
    computeClickData(evt) {
      const rect = this.$refs.container.getBoundingClientRect();
      const cx = evt.clientX - rect.left;
      const cy = evt.clientY - rect.top;
      const ix = (cx - this.translate.x) / this.scale;
      const iy = (cy - this.translate.y) / this.scale;
      if (
        ix < 0 ||
        iy < 0 ||
        ix >= this.naturalSize.w ||
        iy >= this.naturalSize.h
      )
        return null;

      // For click data, we need to render to canvas first
      if (this.isSvg) {
        this.redrawCanvas();
      }

      const pixel = this.$refs.canvas
        .getContext('2d')
        .getImageData(Math.floor(ix), Math.floor(iy), 1, 1).data;
      return {
        coords: { x: Math.floor(ix), y: Math.floor(iy) },
        rgb: { r: pixel[0], g: pixel[1], b: pixel[2], a: pixel[3] },
      };
    },
    /* ---------------------------------------
     * Fitting & centering
     * -------------------------------------*/
    fitImage() {
      const rect = this.$refs.container.getBoundingClientRect();
      // If the container has not been laid out yet (width/height 0) defer until next tick
      if (!rect.width || !rect.height) {
        // Add a guard to prevent infinite recursion when component is hidden
        if (this._fitImageRetries === undefined) this._fitImageRetries = 0;
        if (this._fitImageRetries > 10) {
          this._fitImageRetries = 0;
          return; // Stop trying after 10 attempts
        }
        this._fitImageRetries++;
        this.$nextTick(this.fitImage);
        return;
      }

      // Reset retry counter on successful execution
      this._fitImageRetries = 0;
      const paddingX = rect.width * 0.10;
      const paddingY = rect.height * 0.10;
      const innerW = rect.width - paddingX * 2;
      const innerH = rect.height - paddingY * 2;

      const scaleX = innerW / this.naturalSize.w;
      const scaleY = innerH / this.naturalSize.h;
      this.scale = Math.min(scaleX, scaleY, 1);

      // center inside the padded area
      this.translate.x = paddingX + (innerW - this.naturalSize.w * this.scale) / 2;
      this.translate.y = paddingY + (innerH - this.naturalSize.h * this.scale) / 2;
    },
    /* ---------------------------------------
     * Lifecycle
     * -------------------------------------*/
    onImgLoad() {
      this.naturalSize = {
        w: this.$refs.img.naturalWidth,
        h: this.$refs.img.naturalHeight,
      };
      this.onContentLoad();
    },
    onContentLoad() {
      this.$refs.canvas.width = this.naturalSize.w;
      this.$refs.canvas.height = this.naturalSize.h;
      this.redrawCanvas();
      // If view is untouched (initial or after reset), re‑center
      if (
        this.scale === 1 &&
        this.translate.x === 0 &&
        this.translate.y === 0
      ) {
        this.fitImage();
      }
    },
    /* ---------------------------------------
     * Interaction handlers
     * -------------------------------------*/
    onWheel(evt) {
      evt.preventDefault();
      const delta = -evt.deltaY || evt.wheelDelta || -evt.detail;
      const zoom = delta > 0 ? 1.1 : 0.9;
      const newScale = this.clamp(
        this.scale * zoom,
        this.minScale,
        this.maxScale,
      );
      const rect = this.$refs.container.getBoundingClientRect();
      const cx = evt.clientX - rect.left;
      const cy = evt.clientY - rect.top;
      this.translate.x = cx - ((cx - this.translate.x) / this.scale) * newScale;
      this.translate.y = cy - ((cy - this.translate.y) / this.scale) * newScale;
      this.scale = newScale;
    },
    onMouseDown(evt) {
      this.dragging = true;
      this.lastMouse = { x: evt.clientX, y: evt.clientY };
      window.addEventListener('mousemove', this.onMouseMove);
      window.addEventListener('mouseup', this.onMouseUp);
    },
    onMouseMove(evt) {
      if (!this.dragging) return;
      const dx = evt.clientX - this.lastMouse.x;
      const dy = evt.clientY - this.lastMouse.y;
      this.translate.x += dx;
      this.translate.y += dy;
      this.lastMouse = { x: evt.clientX, y: evt.clientY };
    },
    onMouseUp() {
      this.dragging = false;
      window.removeEventListener('mousemove', this.onMouseMove);
      window.removeEventListener('mouseup', this.onMouseUp);
    },
    onClick(evt) {
      const data = this.computeClickData(evt);
      if (data) {
        this.$refs.container.dispatchEvent(
          new CustomEvent('pixel', { detail: data }),
        );
      }
    },
    /* ---------------------------------------
     * Methods callable from Python side
     * -------------------------------------*/
    setSrc(newSrc, reset = false) {
      // Update internal currentSrc instead of modifying the prop
      this.currentSrc = newSrc;
      this.checkContentType();

      if (this.isSvg) {
        // For SVG, load content and handle reset
        this.loadSvgContent().then(() => {
          if (reset) {
            this.reset();
          }
        });
      } else {
        // For raster images, use existing logic
        if (reset) {
          const img = this.$refs.img;
          const onLoad = () => {
            this.reset();
          };
          img.addEventListener('load', onLoad, { once: true });
        }
        // The img src will update automatically via the binding to currentSrc
      }
    },
    reset() {
      this.scale = 1;
      this.translate = { x: 0, y: 0 };
      this.fitImage();
    }
  },
};
</script>

<style scoped>
.viewer-container img,
.viewer-container svg {
  display: block;
}
</style>
