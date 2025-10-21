import type { SafetySummary, TurnEventPayload } from '../types';

const MAX_ENTRIES = 5;

const statusLabels: Record<string, string> = {
  ai_completed: 'Delivered',
  blocked: 'Blocked',
  waiting_for_ai: 'Waiting',
};

const badgeClassForStatus = (status: string): string => {
  switch (status) {
    case 'ai_completed':
      return 'ai-feed__badge--success';
    case 'blocked':
      return 'ai-feed__badge--warning';
    default:
      return 'ai-feed__badge--neutral';
  }
};

const normaliseStatus = (status: string): string => status.toLowerCase();

const extractInstructions = (
  patch: Record<string, unknown> | undefined,
): string | undefined => {
  if (!patch) return undefined;
  const instructions = patch['instructions'];
  return typeof instructions === 'string' && instructions.trim().length > 0
    ? instructions.trim()
    : undefined;
};

const extractPalette = (
  patch: Record<string, unknown> | undefined,
): string[] => {
  if (!patch) return [];
  const palette = patch['palette'];
  if (!Array.isArray(palette)) return [];
  return palette.filter((value): value is string => typeof value === 'string');
};

export class AiTurnFeed {
  readonly element: HTMLElement;
  private readonly list: HTMLUListElement;

  constructor() {
    this.element = document.createElement('section');
    this.element.className = 'ai-feed';

    const header = document.createElement('div');
    header.className = 'ai-feed__header';

    const title = document.createElement('h2');
    title.textContent = 'AI Turns';
    header.appendChild(title);

    const subtitle = document.createElement('p');
    subtitle.className = 'ai-feed__subtitle';
    subtitle.textContent = 'Latest storybook suggestions and safety checks';
    header.appendChild(subtitle);

    this.list = document.createElement('ul');
    this.list.className = 'ai-feed__list';

    this.element.appendChild(header);
    this.element.appendChild(this.list);
  }

  addTurn(
    event: TurnEventPayload,
    patch: Record<string, unknown> | undefined,
  ): void {
    const status = normaliseStatus(event.status);
    const instructions = extractInstructions(patch);
    const palette = extractPalette(patch);

    const item = document.createElement('li');
    item.className = 'ai-feed__item';
    item.dataset.status = status;

    const header = document.createElement('div');
    header.className = 'ai-feed__item-header';

    const turnLabel = document.createElement('span');
    turnLabel.className = 'ai-feed__turn';
    turnLabel.textContent = `Turn ${event.sequence}`;
    header.appendChild(turnLabel);

    const badge = document.createElement('span');
    badge.className = `ai-feed__badge ${badgeClassForStatus(status)}`;
    badge.textContent = statusLabels[status] ?? status.replace('_', ' ');
    header.appendChild(badge);

    item.appendChild(header);

    if (instructions) {
      const instructionEl = document.createElement('p');
      instructionEl.className = 'ai-feed__instructions';
      instructionEl.textContent = instructions;
      item.appendChild(instructionEl);
    }

    if (palette.length > 0) {
      const paletteRow = document.createElement('div');
      paletteRow.className = 'ai-feed__palette';
      for (const swatchColor of palette.slice(0, 5)) {
        const swatch = document.createElement('span');
        swatch.className = 'ai-feed__palette-swatch';
        swatch.style.backgroundColor = swatchColor;
        swatch.title = swatchColor;
        paletteRow.appendChild(swatch);
      }
      item.appendChild(paletteRow);
    }

    const safety = event.safety as SafetySummary | undefined;
    if (safety) {
      const safetySummary = document.createElement('div');
      safetySummary.className = 'ai-feed__safety';
      safetySummary.textContent = safety.passed
        ? 'Content safety passed'
        : 'Requires moderator review';

      if (!safety.passed && safety.reasons.length > 0) {
        const reasonList = document.createElement('ul');
        reasonList.className = 'ai-feed__reasons';
        for (const reason of safety.reasons) {
          const li = document.createElement('li');
          li.textContent = reason;
          reasonList.appendChild(li);
        }
        safetySummary.appendChild(reasonList);
      }

      item.appendChild(safetySummary);
    } else if (event.reason) {
      const reason = document.createElement('p');
      reason.className = 'ai-feed__reason';
      reason.textContent = event.reason;
      item.appendChild(reason);
    }

    this.list.prepend(item);

    while (this.list.children.length > MAX_ENTRIES) {
      this.list.removeChild(this.list.lastElementChild as HTMLElement);
    }
  }
}
