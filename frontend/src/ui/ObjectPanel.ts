import type { Stroke } from '../types';

type CommitHandler = (selection: {
  strokeIds: string[];
  label: string;
}) => void;

type StrokeMeta = {
  id: string;
  color: string;
  width: number;
  selected: boolean;
};

export class ObjectPanel {
  readonly element: HTMLElement;
  private readonly list: HTMLElement;
  private readonly labelInput: HTMLInputElement;
  private readonly commitButton: HTMLButtonElement;
  private strokes = new Map<string, StrokeMeta>();
  private commitHandler: CommitHandler | null = null;

  constructor() {
    this.element = document.createElement('section');
    this.element.className = 'object-panel';

    const header = document.createElement('div');
    header.className = 'object-panel__header';
    header.innerHTML = '<h2>Objects</h2>';
    this.element.appendChild(header);

    this.list = document.createElement('ul');
    this.list.className = 'object-panel__list';
    this.element.appendChild(this.list);

    const controls = document.createElement('div');
    controls.className = 'object-panel__controls';
    this.labelInput = document.createElement('input');
    this.labelInput.type = 'text';
    this.labelInput.placeholder = 'Describe this object (optional)';
    this.commitButton = document.createElement('button');
    this.commitButton.textContent = 'Commit Object';
    this.commitButton.addEventListener('click', () => this.handleCommit());

    controls.appendChild(this.labelInput);
    controls.appendChild(this.commitButton);
    this.element.appendChild(controls);
  }

  setCommitHandler(handler: CommitHandler): void {
    this.commitHandler = handler;
  }

  addStroke(stroke: Stroke): void {
    if (this.strokes.has(stroke.id)) {
      return;
    }
    this.strokes.set(stroke.id, {
      id: stroke.id,
      color: stroke.color,
      width: stroke.width,
      selected: false,
    });
    this.renderList();
  }

  confirmStroke(tempId: string, persisted: Stroke): void {
    const entry = this.strokes.get(tempId);
    if (!entry) {
      this.addStroke(persisted);
      return;
    }
    this.strokes.delete(tempId);
    this.strokes.set(persisted.id, {
      id: persisted.id,
      color: persisted.color,
      width: persisted.width,
      selected: entry.selected,
    });
    this.renderList();
  }

  setSelection(strokeIds: string[]): void {
    for (const entry of this.strokes.values()) {
      entry.selected = strokeIds.includes(entry.id);
    }
    this.renderList();
  }

  private handleCommit(): void {
    if (!this.commitHandler) {
      return;
    }
    const selected = [...this.strokes.values()]
      .filter((stroke) => stroke.selected)
      .map((stroke) => stroke.id);
    if (selected.length === 0) {
      return;
    }
    const label = this.labelInput.value.trim();
    this.commitHandler({ strokeIds: selected, label });
    this.labelInput.value = '';
    this.clearSelection();
  }

  private clearSelection(): void {
    for (const entry of this.strokes.values()) {
      entry.selected = false;
    }
    this.renderList();
  }

  private renderList(): void {
    this.list.innerHTML = '';
    for (const stroke of this.strokes.values()) {
      const item = document.createElement('li');
      item.className = 'object-panel__item';
      if (stroke.selected) {
        item.classList.add('object-panel__item--selected');
      }
      const swatch = document.createElement('span');
      swatch.className = 'object-panel__swatch';
      swatch.style.backgroundColor = stroke.color;
      const label = document.createElement('span');
      label.textContent = stroke.id.slice(0, 6);
      const toggle = document.createElement('input');
      toggle.type = 'checkbox';
      toggle.checked = stroke.selected;
      toggle.addEventListener('change', () => {
        stroke.selected = toggle.checked;
        this.renderList();
      });

      item.appendChild(toggle);
      item.appendChild(swatch);
      item.appendChild(label);
      this.list.appendChild(item);
    }
  }
}
