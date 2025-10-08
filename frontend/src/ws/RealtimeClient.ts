import type { MessageEnvelope, Stroke, TurnEventPayload } from '../types';

type EventHandler<T> = (payload: T) => void;

type TopicHandlerMap = {
  stroke: Set<EventHandler<Stroke>>;
  object: Set<EventHandler<Record<string, unknown>>>;
  turn: Set<EventHandler<TurnEventPayload>>;
  system: Set<EventHandler<Record<string, unknown>>>;
};

const createHandlerMap = (): TopicHandlerMap => ({
  stroke: new Set(),
  object: new Set(),
  turn: new Set(),
  system: new Set(),
});

export class RealtimeClient {
  private socket: WebSocket | null = null;
  private handlers: TopicHandlerMap = createHandlerMap();
  private reconnectAttempts = 0;
  private heartbeatInterval: number | undefined;

  constructor(
    private readonly url: string,
    private readonly roomId: string,
    private readonly userId: string,
  ) {}

  connect(): void {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.socket = new WebSocket(this.url);
    this.socket.addEventListener('open', () => {
      this.reconnectAttempts = 0;
      this.sendSystem('join', { roomId: this.roomId, userId: this.userId });
      this.startHeartbeat();
    });

    this.socket.addEventListener('message', (event) => {
      try {
        const envelope = JSON.parse(event.data) as MessageEnvelope;
        this.dispatch(envelope);
      } catch (error) {
        console.warn('Failed to parse realtime message', error);
      }
    });

    this.socket.addEventListener('close', () => {
      this.stopHeartbeat();
      this.scheduleReconnect();
    });

    this.socket.addEventListener('error', () => {
      this.socket?.close();
    });
  }

  on(topic: 'stroke', handler: EventHandler<Stroke>): void;
  on(topic: 'object', handler: EventHandler<Record<string, unknown>>): void;
  on(topic: 'turn', handler: EventHandler<TurnEventPayload>): void;
  on(topic: 'system', handler: EventHandler<Record<string, unknown>>): void;
  on(topic: keyof TopicHandlerMap, handler: EventHandler<unknown>): void {
    (this.handlers[topic] as Set<EventHandler<unknown>>).add(handler as EventHandler<unknown>);
  }

  off(topic: 'stroke', handler: EventHandler<Stroke>): void;
  off(topic: 'object', handler: EventHandler<Record<string, unknown>>): void;
  off(topic: 'turn', handler: EventHandler<TurnEventPayload>): void;
  off(topic: 'system', handler: EventHandler<Record<string, unknown>>): void;
  off(topic: keyof TopicHandlerMap, handler: EventHandler<unknown>): void {
    (this.handlers[topic] as Set<EventHandler<unknown>>).delete(handler as EventHandler<unknown>);
  }

  sendStroke(stroke: Stroke): void {
    this.send({
      topic: 'stroke',
      roomId: this.roomId,
      timestamp: new Date().toISOString(),
      payload: {
        id: stroke.id,
        roomId: this.roomId,
        authorId: stroke.authorId,
        color: stroke.color,
        width: stroke.width,
        path: stroke.path,
        objectId: stroke.objectId ?? null,
      },
    });
  }

  private dispatch(envelope: MessageEnvelope): void {
    const set = this.handlers[envelope.topic as keyof TopicHandlerMap];
    if (!set) return;
    const payload = envelope.payload;
    switch (envelope.topic) {
      case 'stroke':
        for (const handler of set) {
          handler({
            id: String(payload['id']),
            authorId: String(payload['authorId'] ?? payload['author_id'] ?? ''),
            color: String(payload['color'] ?? '#000000'),
            width: Number(payload['width'] ?? 1),
            path: Array.isArray(payload['path']) ? (payload['path'] as Stroke['path']) : [],
            objectId: (payload['objectId'] ?? payload['object_id'] ?? null) as string | null,
            ts: typeof payload['ts'] === 'string' ? (payload['ts'] as string) : undefined,
          });
        }
        break;
      case 'turn':
        for (const handler of set) {
          handler({
            turnId: String(payload['turnId'] ?? payload['turn_id'] ?? ''),
            sequence: Number(payload['sequence'] ?? 0),
            status: String(payload['status'] ?? ''),
            safetyStatus: payload['safetyStatus']?.toString(),
            patch: (payload['patch'] as Record<string, unknown>) ?? undefined,
            reason: payload['reason']?.toString(),
          });
        }
        break;
      case 'system':
        if (envelope.action === 'pong') {
          return;
        }
        for (const handler of set) {
          handler(payload);
        }
        break;
      case 'object':
      default:
        for (const handler of set) {
          handler(payload);
        }
    }
  }

  private send(envelope: MessageEnvelope): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.socket.send(JSON.stringify(envelope));
  }

  private sendSystem(action: string, payload: Record<string, unknown>): void {
    this.send({
      topic: 'system',
      action,
      roomId: this.roomId,
      timestamp: new Date().toISOString(),
      payload,
    });
  }

  private scheduleReconnect(): void {
    this.reconnectAttempts += 1;
    const delay = Math.min(5000, 500 * this.reconnectAttempts);
    setTimeout(() => this.connect(), delay);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatInterval = window.setInterval(() => {
      this.sendSystem('ping', {});
    }, 10000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      window.clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = undefined;
    }
  }
}
