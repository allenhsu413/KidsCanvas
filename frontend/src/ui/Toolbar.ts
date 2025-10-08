type BrushChangeHandler = (options: { color: string; width: number }) => void;

type ActionHandler = () => void;

export class Toolbar {
  readonly element: HTMLElement;
  private readonly colorInput: HTMLInputElement;
  private readonly widthInput: HTMLInputElement;
  private readonly resetViewButton: HTMLButtonElement;
  private brushHandler: BrushChangeHandler | null = null;
  private resetHandler: ActionHandler | null = null;

  constructor() {
    this.element = document.createElement('header');
    this.element.className = 'toolbar';

    const title = document.createElement('h1');
    title.textContent = 'Infinite Kids Canvas';
    this.element.appendChild(title);

    const controls = document.createElement('div');
    controls.className = 'toolbar__controls';

    this.colorInput = document.createElement('input');
    this.colorInput.type = 'color';
    this.colorInput.value = '#2f80ed';
    this.colorInput.addEventListener('input', () => this.emitBrushChange());

    this.widthInput = document.createElement('input');
    this.widthInput.type = 'range';
    this.widthInput.min = '2';
    this.widthInput.max = '24';
    this.widthInput.value = '6';
    this.widthInput.addEventListener('input', () => this.emitBrushChange());

    this.resetViewButton = document.createElement('button');
    this.resetViewButton.textContent = 'Center Canvas';
    this.resetViewButton.addEventListener('click', () => this.resetHandler?.());

    controls.appendChild(this.createControlLabel('Color', this.colorInput));
    controls.appendChild(this.createControlLabel('Size', this.widthInput));
    controls.appendChild(this.resetViewButton);
    this.element.appendChild(controls);
  }

  onBrushChange(handler: BrushChangeHandler): void {
    this.brushHandler = handler;
    this.emitBrushChange();
  }

  onResetView(handler: ActionHandler): void {
    this.resetHandler = handler;
  }

  private emitBrushChange(): void {
    if (!this.brushHandler) return;
    this.brushHandler({
      color: this.colorInput.value,
      width: Number(this.widthInput.value),
    });
  }

  private createControlLabel(label: string, input: HTMLElement): HTMLElement {
    const wrapper = document.createElement('label');
    wrapper.className = 'toolbar__label';
    wrapper.textContent = label;
    wrapper.appendChild(input);
    return wrapper;
  }
}
