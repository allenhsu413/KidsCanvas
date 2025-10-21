import type { AnchorRing, BBox, Point, Stroke } from '../types';

type StrokeCompleteCallback = (stroke: Stroke) => void;

type PatchOverlay = {
  id: string;
  anchorRing: AnchorRing;
  status: string;
  instructions?: string;
};

export class InfiniteCanvas {
  private ctx: CanvasRenderingContext2D;
  private camera = { x: 0, y: 0, scale: 1 };
  private activeStroke: Stroke | null = null;
  private strokeOrder: string[] = [];
  private strokes = new Map<string, Stroke>();
  private isPanning = false;
  private lastPointer: Point | null = null;
  private brush = { color: '#2f80ed', width: 6 };
  private patches = new Map<string, PatchOverlay>();
  private renderRequested = false;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly onStrokeComplete: StrokeCompleteCallback,
    private readonly userId: string,
  ) {
    const context = canvas.getContext('2d');
    if (!context) {
      throw new Error('Canvas 2D context not available');
    }
    this.ctx = context;
    this.setupEvents();
    this.resize();
    window.addEventListener('resize', () => this.resize());
    this.requestRender();
  }

  setBrush(color: string, width: number): void {
    this.brush = { color, width };
  }

  addStroke(stroke: Stroke): void {
    if (this.strokes.has(stroke.id)) {
      return;
    }
    this.strokes.set(stroke.id, { ...stroke, pending: false });
    this.strokeOrder.push(stroke.id);
    this.requestRender();
  }

  confirmStroke(tempId: string, persisted: Stroke): void {
    const stroke = this.strokes.get(tempId);
    if (!stroke) {
      this.addStroke(persisted);
      return;
    }
    const index = this.strokeOrder.indexOf(tempId);
    if (index >= 0) {
      this.strokeOrder[index] = persisted.id;
    } else {
      this.strokeOrder.push(persisted.id);
    }
    this.strokes.delete(tempId);
    this.strokes.set(persisted.id, { ...stroke, ...persisted, pending: false });
    this.requestRender();
  }

  setCamera(center: Point, scale: number): void {
    this.camera.x = center.x;
    this.camera.y = center.y;
    this.camera.scale = scale;
    this.requestRender();
  }

  showPatch(
    id: string,
    anchorRing: AnchorRing,
    status: string,
    instructions?: string,
  ): void {
    this.patches.set(id, { id, anchorRing, status, instructions });
    this.requestRender();
  }

  clearPatches(): void {
    this.patches.clear();
    this.requestRender();
  }

  getStrokeIds(): string[] {
    return [...this.strokeOrder];
  }

  getStroke(id: string): Stroke | undefined {
    return this.strokes.get(id);
  }

  private setupEvents(): void {
    this.canvas.addEventListener('pointerdown', (event) =>
      this.handlePointerDown(event),
    );
    this.canvas.addEventListener('pointermove', (event) =>
      this.handlePointerMove(event),
    );
    this.canvas.addEventListener('pointerup', (event) =>
      this.handlePointerUp(event),
    );
    this.canvas.addEventListener('pointercancel', (event) =>
      this.handlePointerUp(event),
    );
    this.canvas.addEventListener('wheel', (event) => this.handleWheel(event));
  }

  private handlePointerDown(event: PointerEvent): void {
    this.canvas.setPointerCapture(event.pointerId);
    const worldPoint = this.toWorld(event.offsetX, event.offsetY);
    if (event.button === 1 || event.button === 2 || event.altKey) {
      this.isPanning = true;
      this.lastPointer = { x: event.clientX, y: event.clientY };
      return;
    }

    if (event.button !== 0) {
      return;
    }

    const strokeId = crypto.randomUUID();
    this.activeStroke = {
      id: strokeId,
      authorId: this.userId,
      color: this.brush.color,
      width: this.brush.width,
      path: [worldPoint],
      pending: true,
    };
    this.strokes.set(strokeId, this.activeStroke);
    this.strokeOrder.push(strokeId);
    this.requestRender();
  }

  private handlePointerMove(event: PointerEvent): void {
    if (this.isPanning && this.lastPointer) {
      const dx = (event.clientX - this.lastPointer.x) / this.camera.scale;
      const dy = (event.clientY - this.lastPointer.y) / this.camera.scale;
      this.camera.x -= dx;
      this.camera.y -= dy;
      this.lastPointer = { x: event.clientX, y: event.clientY };
      this.requestRender();
      return;
    }

    if (!this.activeStroke) {
      return;
    }

    const worldPoint = this.toWorld(event.offsetX, event.offsetY);
    const points = this.activeStroke.path;
    const lastPoint = points[points.length - 1];
    const distance = Math.hypot(
      worldPoint.x - lastPoint.x,
      worldPoint.y - lastPoint.y,
    );
    if (distance > 1.5) {
      points.push(worldPoint);
      this.requestRender();
    }
  }

  private handlePointerUp(event: PointerEvent): void {
    this.canvas.releasePointerCapture(event.pointerId);
    if (this.isPanning) {
      this.isPanning = false;
      this.lastPointer = null;
      return;
    }

    if (!this.activeStroke) {
      return;
    }

    if (this.activeStroke.path.length > 1) {
      this.onStrokeComplete(this.activeStroke);
    } else {
      this.removeStroke(this.activeStroke.id);
    }
    this.activeStroke = null;
  }

  private handleWheel(event: WheelEvent): void {
    event.preventDefault();
    const scaleFactor = event.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.min(
      4,
      Math.max(0.2, this.camera.scale * scaleFactor),
    );

    const mouseWorld = this.toWorld(event.offsetX, event.offsetY);
    this.camera.scale = newScale;
    const newCenterScreen = this.toScreen(mouseWorld.x, mouseWorld.y);
    const dx = event.offsetX - newCenterScreen.x;
    const dy = event.offsetY - newCenterScreen.y;
    this.camera.x -= dx / newScale;
    this.camera.y -= dy / newScale;
    this.requestRender();
  }

  private removeStroke(id: string): void {
    this.strokes.delete(id);
    this.strokeOrder = this.strokeOrder.filter((strokeId) => strokeId !== id);
    this.requestRender();
  }

  private resize(): void {
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = rect.width * window.devicePixelRatio;
    this.canvas.height = rect.height * window.devicePixelRatio;
    this.ctx.setTransform(
      window.devicePixelRatio,
      0,
      0,
      window.devicePixelRatio,
      0,
      0,
    );
    this.requestRender();
  }

  private toWorld(screenX: number, screenY: number): Point {
    return {
      x:
        (screenX - this.canvas.clientWidth / 2) / this.camera.scale +
        this.camera.x,
      y:
        (screenY - this.canvas.clientHeight / 2) / this.camera.scale +
        this.camera.y,
    };
  }

  private toScreen(worldX: number, worldY: number): Point {
    return {
      x:
        (worldX - this.camera.x) * this.camera.scale +
        this.canvas.clientWidth / 2,
      y:
        (worldY - this.camera.y) * this.camera.scale +
        this.canvas.clientHeight / 2,
    };
  }

  private requestRender(): void {
    if (this.renderRequested) return;
    this.renderRequested = true;
    requestAnimationFrame(() => this.render());
  }

  private render(): void {
    this.renderRequested = false;
    const { width, height } = this.canvas;
    this.ctx.save();
    this.ctx.setTransform(
      window.devicePixelRatio,
      0,
      0,
      window.devicePixelRatio,
      0,
      0,
    );
    this.ctx.clearRect(0, 0, width, height);
    this.ctx.restore();

    this.drawGrid();

    for (const strokeId of this.strokeOrder) {
      const stroke = this.strokes.get(strokeId);
      if (!stroke) continue;
      this.drawStroke(stroke);
    }

    for (const patch of this.patches.values()) {
      this.drawPatch(patch);
    }
  }

  private drawGrid(): void {
    const ctx = this.ctx;
    const spacing = 64 * this.camera.scale;
    if (spacing < 10) {
      return;
    }
    ctx.save();
    ctx.strokeStyle = '#e0e0e0';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 12]);

    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    const origin = this.toScreen(0, 0);

    for (let x = origin.x % spacing; x < width; x += spacing) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    for (let y = origin.y % spacing; y < height; y += spacing) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    ctx.restore();
  }

  private drawStroke(stroke: Stroke): void {
    const ctx = this.ctx;
    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = stroke.color;
    ctx.lineWidth = stroke.width * this.camera.scale;
    ctx.beginPath();

    const [first, ...rest] = stroke.path;
    const firstScreen = this.toScreen(first.x, first.y);
    ctx.moveTo(firstScreen.x, firstScreen.y);
    for (const point of rest) {
      const screen = this.toScreen(point.x, point.y);
      ctx.lineTo(screen.x, screen.y);
    }
    ctx.stroke();

    ctx.restore();
  }

  private drawPatch(patch: PatchOverlay): void {
    const ctx = this.ctx;
    ctx.save();
    ctx.strokeStyle = patch.status === 'passed' ? '#6fcf97' : '#f2994a';
    ctx.lineWidth = 2;
    ctx.setLineDash([12, 8]);

    this.drawBBox(patch.anchorRing.outer);
    ctx.setLineDash([]);
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = patch.status === 'passed' ? '#6fcf97' : '#f2994a';
    this.fillBBox(patch.anchorRing.inner);
    ctx.globalAlpha = 1;
    this.drawPatchInstructions(patch);
    ctx.restore();
  }

  private drawPatchInstructions(patch: PatchOverlay): void {
    if (!patch.instructions) return;

    const ctx = this.ctx;
    const outer = patch.anchorRing.outer;
    const topLeft = this.toScreen(outer.x, outer.y);
    const boxWidth = 260;
    const padding = 12;
    const lines = this.wrapText(
      patch.instructions,
      boxWidth - padding * 2,
      '14px Nunito, sans-serif',
    );
    const boxHeight = lines.length * 18 + padding * 2;

    ctx.save();
    ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
    ctx.strokeStyle = patch.status === 'passed' ? '#6fcf97' : '#f2994a';
    ctx.lineWidth = 1.5;
    const x = topLeft.x;
    const y = topLeft.y - boxHeight - 10;
    ctx.beginPath();
    ctx.roundRect(x, y, boxWidth, boxHeight, 12);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#2f4858';
    ctx.font = '14px "Nunito", sans-serif';
    ctx.textBaseline = 'top';
    lines.forEach((line, index) => {
      ctx.fillText(line, x + padding, y + padding + index * 18);
    });
    ctx.restore();
  }

  private wrapText(text: string, maxWidth: number, font: string): string[] {
    const ctx = this.ctx;
    ctx.save();
    ctx.font = font;
    const words = text.split(/\s+/);
    const lines: string[] = [];
    let current = '';
    for (const word of words) {
      const testLine = current ? `${current} ${word}` : word;
      const metrics = ctx.measureText(testLine);
      if (metrics.width > maxWidth && current) {
        lines.push(current);
        current = word;
      } else {
        current = testLine;
      }
    }
    if (current) {
      lines.push(current);
    }
    ctx.restore();
    return lines;
  }

  private drawBBox(bbox: BBox): void {
    const ctx = this.ctx;
    const topLeft = this.toScreen(bbox.x, bbox.y);
    const bottomRight = this.toScreen(
      bbox.x + bbox.width,
      bbox.y + bbox.height,
    );
    ctx.beginPath();
    ctx.rect(
      topLeft.x,
      topLeft.y,
      bottomRight.x - topLeft.x,
      bottomRight.y - topLeft.y,
    );
    ctx.stroke();
  }

  private fillBBox(bbox: BBox): void {
    const ctx = this.ctx;
    const topLeft = this.toScreen(bbox.x, bbox.y);
    const bottomRight = this.toScreen(
      bbox.x + bbox.width,
      bbox.y + bbox.height,
    );
    ctx.beginPath();
    ctx.rect(
      topLeft.x,
      topLeft.y,
      bottomRight.x - topLeft.x,
      bottomRight.y - topLeft.y,
    );
    ctx.fill();
  }
}
