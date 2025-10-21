import './styles/main.css';
import { InfiniteCanvas } from './canvas/InfiniteCanvas';
import { GameServiceClient } from './api/GameServiceClient';
import { RealtimeClient } from './ws/RealtimeClient';
import { ObjectPanel } from './ui/ObjectPanel';
import { Toolbar } from './ui/Toolbar';
import { AiTurnFeed } from './ui/AiTurnFeed';
import type { AnchorRing, RoomSnapshot, Stroke } from './types';

const backendBase =
  import.meta.env.VITE_BACKEND_URL ?? 'http://localhost:8000/api';
const realtimeBase = import.meta.env.VITE_REALTIME_URL ?? 'ws://localhost:9001';

const appRoot = document.querySelector<HTMLDivElement>('#app');
if (!appRoot) {
  throw new Error('App root not found');
}

let statusTimeout: number | undefined;

const toolbar = new Toolbar();
const objectPanel = new ObjectPanel();
const aiTurnFeed = new AiTurnFeed();
const content = document.createElement('div');
content.className = 'app-content';
const canvasContainer = document.createElement('div');
canvasContainer.className = 'canvas-container';
const canvasEl = document.createElement('canvas');
canvasContainer.appendChild(canvasEl);
content.appendChild(canvasContainer);

const sidePanels = document.createElement('div');
sidePanels.className = 'side-panels';
sidePanels.appendChild(objectPanel.element);
sidePanels.appendChild(aiTurnFeed.element);
content.appendChild(sidePanels);

const statusBanner = document.createElement('div');
statusBanner.className = 'status-banner';
statusBanner.style.display = 'none';
statusBanner.textContent = 'Ready';
canvasContainer.appendChild(statusBanner);

appRoot.appendChild(toolbar.element);
appRoot.appendChild(content);

const userId = getOrCreateUserId();
const gameClient = new GameServiceClient(backendBase);

(async () => {
  const roomId = await ensureRoom(gameClient, userId);
  const snapshot = await loadSnapshot(gameClient, roomId, userId);

  const canvas = new InfiniteCanvas(canvasEl, handleStrokeComplete, userId);
  const strokeRegistry = new Map<string, Stroke>();

  const realtimeClient = new RealtimeClient(realtimeBase, roomId, userId);
  realtimeClient.on('stroke', (incoming) => {
    if (strokeRegistry.has(incoming.id)) return;
    strokeRegistry.set(incoming.id, incoming);
    canvas.addStroke(incoming);
    objectPanel.addStroke(incoming);
  });

  realtimeClient.on('turn', (payload) => {
    const patch = payload.patch as
      | { anchor?: AnchorRing; instructions?: string }
      | undefined;
    if (
      payload.status === 'ai_completed' ||
      payload.status === 'AI_COMPLETED'
    ) {
      const anchorRing = (patch?.anchor ?? patch) as AnchorRing | undefined;
      if (anchorRing) {
        canvas.showPatch(
          payload.turnId,
          anchorRing,
          payload.safetyStatus ?? 'passed',
          typeof patch?.instructions === 'string'
            ? patch.instructions
            : undefined,
        );
        showStatus(`AI added a storybook detail (turn ${payload.sequence})`);
      }
    } else if (payload.status === 'blocked') {
      const reason =
        payload.safety?.reasons?.join(', ') ?? payload.reason ?? 'safety hold';
      showStatus(`AI turn blocked: ${reason}`);
    }

    aiTurnFeed.addTurn(payload, payload.patch);
  });

  realtimeClient.connect();

  toolbar.onBrushChange(({ color, width }) => {
    canvas.setBrush(color, width);
  });
  toolbar.onResetView(() => {
    canvas.setCamera({ x: 0, y: 0 }, 1);
  });

  objectPanel.setCommitHandler(async ({ strokeIds, label }) => {
    try {
      await gameClient.commitObject(
        roomId,
        userId,
        strokeIds,
        label || undefined,
      );
      showStatus('Object committed! Waiting for AI response…');
    } catch (error) {
      console.error(error);
      showStatus('Failed to commit object');
    }
  });

  function showStatus(message: string): void {
    statusBanner.textContent = message;
    statusBanner.style.display = 'flex';
    if (statusTimeout) {
      window.clearTimeout(statusTimeout);
    }
    statusTimeout = window.setTimeout(() => {
      statusBanner.style.display = 'none';
      statusTimeout = undefined;
    }, 3000);
  }

  function addSnapshot(snapshot: RoomSnapshot): void {
    for (const stroke of snapshot.strokes) {
      const normalised: Stroke = {
        id: stroke.id,
        authorId: stroke.author_id,
        color: stroke.color,
        width: stroke.width,
        path: stroke.path,
        objectId: stroke.object_id,
        ts: stroke.ts,
      };
      strokeRegistry.set(normalised.id, normalised);
      canvas.addStroke(normalised);
      objectPanel.addStroke(normalised);
    }
  }

  addSnapshot(snapshot);

  async function handleStrokeComplete(stroke: Stroke): Promise<void> {
    const tempId = stroke.id;
    stroke.authorId = userId;
    strokeRegistry.set(tempId, stroke);
    objectPanel.addStroke(stroke);
    realtimeClient.sendStroke(stroke);
    try {
      const persisted = await gameClient.createStroke(roomId, stroke);
      strokeRegistry.delete(tempId);
      strokeRegistry.set(persisted.id, persisted);
      canvas.confirmStroke(tempId, persisted);
      objectPanel.confirmStroke(tempId, persisted);
    } catch (error) {
      console.error('Failed to persist stroke', error);
      showStatus('Failed to sync stroke');
    }
  }
})();

function getOrCreateUserId(): string {
  const key = 'kids-canvas-user-id';
  const existing = window.localStorage.getItem(key);
  if (existing) {
    return existing;
  }
  const generated = crypto.randomUUID();
  window.localStorage.setItem(key, generated);
  return generated;
}

async function ensureRoom(
  client: GameServiceClient,
  userId: string,
): Promise<string> {
  const currentHash = window.location.hash.replace('#', '');
  if (currentHash) {
    return currentHash;
  }
  const created = await client.createRoom('Storybook Room', userId);
  const roomId = created.room.id;
  window.location.hash = roomId;
  return roomId;
}

async function loadSnapshot(
  client: GameServiceClient,
  roomId: string,
  userId: string,
): Promise<RoomSnapshot> {
  try {
    const snapshot = await client.joinRoom(roomId, userId);
    return snapshot;
  } catch (error) {
    console.error('Failed to join room', error);
    throw error;
  }
}
