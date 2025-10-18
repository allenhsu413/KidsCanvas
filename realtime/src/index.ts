import { WebSocketServer, WebSocket, RawData } from 'ws';
import { loadConfig } from './config.js';

type Topic = 'stroke' | 'object' | 'turn' | 'system';

type MessageEnvelope<T = Record<string, unknown>> = {
  topic: Topic;
  roomId: string;
  timestamp: string;
  payload: T;
  action?: string;
};

type SystemPayload = {
  roomId?: string;
  userId?: string;
  message?: string;
};

type RateLimiter = {
  tokens: number;
  capacity: number;
  refillIntervalMs: number;
  lastRefill: number;
};

type ConnectionContext = {
  roomId: string;
  userId?: string;
  joinedAt: number;
  lastSeen: number;
  isAlive: boolean;
  rateLimiter: RateLimiter;
};

const config = loadConfig();

const server = new WebSocketServer({ host: config.host, port: config.port });

const rooms = new Map<string, Set<WebSocket>>();
const context = new WeakMap<WebSocket, ConnectionContext>();
const eventEndpoint = new URL('/api/internal/events/next', config.gameServiceUrl).toString();
let running = true;

const nowIso = () => new Date().toISOString();
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const createRateLimiter = (): RateLimiter => ({
  capacity: config.rateLimit.burst,
  tokens: config.rateLimit.burst,
  refillIntervalMs: config.rateLimit.refillIntervalMs,
  lastRefill: Date.now(),
});

const consumeRateLimit = (limiter: RateLimiter): boolean => {
  const now = Date.now();
  if (now - limiter.lastRefill >= limiter.refillIntervalMs) {
    const intervals = Math.floor((now - limiter.lastRefill) / limiter.refillIntervalMs);
    limiter.tokens = Math.min(
      limiter.capacity,
      limiter.tokens + intervals * limiter.capacity,
    );
    limiter.lastRefill += intervals * limiter.refillIntervalMs;
  }
  if (limiter.tokens <= 0) {
    return false;
  }
  limiter.tokens -= 1;
  return true;
};

const sendEnvelope = <T>(socket: WebSocket, envelope: MessageEnvelope<T>) => {
  if (socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(envelope));
  }
};

const ensureRoom = (roomId: string) => {
  if (!rooms.has(roomId)) {
    rooms.set(roomId, new Set());
  }
};

const payloadSize = (data: RawData): number => {
  if (typeof data === 'string') {
    return Buffer.byteLength(data);
  }
  if (Array.isArray(data)) {
    return data.reduce((total, chunk) => total + payloadSize(chunk), 0);
  }
  if (Buffer.isBuffer(data)) {
    return data.byteLength;
  }
  return Buffer.from(data).byteLength;
};

const bufferFromRawData = (data: RawData): Buffer => {
  if (typeof data === 'string') {
    return Buffer.from(data);
  }
  if (Array.isArray(data)) {
    return Buffer.concat(data.map((chunk) => bufferFromRawData(chunk)));
  }
  if (Buffer.isBuffer(data)) {
    return data;
  }
  return Buffer.from(data);
};

const announcePresence = (
  roomId: string,
  action: 'presence.join' | 'presence.leave' | 'presence.resume',
  payload: SystemPayload,
  sender?: WebSocket,
) => {
  broadcast(
    roomId,
    {
      topic: 'system',
      action,
      roomId,
      timestamp: nowIso(),
      payload,
    },
    sender,
  );
};

const joinRoom = (socket: WebSocket, roomId: string, userId?: string) => {
  const existing = context.get(socket);
  if (existing) {
    if (existing.roomId !== roomId) {
      leaveRoom(socket, 'switch');
    } else {
      existing.userId = userId;
      existing.isAlive = true;
      existing.lastSeen = Date.now();
      ensureRoom(roomId);
      rooms.get(roomId)?.add(socket);
      return existing;
    }
  }
  ensureRoom(roomId);
  rooms.get(roomId)?.add(socket);
  const meta: ConnectionContext = {
    roomId,
    userId,
    joinedAt: Date.now(),
    lastSeen: Date.now(),
    isAlive: true,
    rateLimiter: createRateLimiter(),
  };
  context.set(socket, meta);
  return meta;
};

const leaveRoom = (socket: WebSocket, reason: 'leave' | 'disconnect' | 'switch' = 'leave') => {
  const meta = context.get(socket);
  if (!meta) return;
  const roomSockets = rooms.get(meta.roomId);
  roomSockets?.delete(socket);
  if (roomSockets && roomSockets.size === 0) {
    rooms.delete(meta.roomId);
  }
  context.delete(socket);
  if (reason !== 'switch') {
    announcePresence(
      meta.roomId,
      'presence.leave',
      {
        roomId: meta.roomId,
        userId: meta.userId,
        message: reason,
      },
      socket,
    );
  }
};

const broadcast = (roomId: string, message: MessageEnvelope, sender?: WebSocket) => {
  const roomSockets = rooms.get(roomId);
  if (!roomSockets) return;
  const raw = JSON.stringify(message);
  for (const socket of roomSockets) {
    if (socket !== sender && socket.readyState === WebSocket.OPEN) {
      socket.send(raw);
    }
  }
};

const pollBackendEvents = async () => {
  while (running) {
    try {
      const response = await fetch(eventEndpoint, {
        headers: { Accept: 'application/json' },
      });
      if (response.status === 204) {
        await sleep(config.eventPollIntervalMs);
        continue;
      }
      if (!response.ok) {
        console.error('[gateway] Failed to fetch backend event', response.status, response.statusText);
        await sleep(1000);
        continue;
      }
      const parsed = (await response.json()) as MessageEnvelope | null;
      if (parsed && typeof parsed.roomId === 'string') {
        broadcast(parsed.roomId, parsed);
      }
    } catch (error: unknown) {
      console.error('[gateway] Event polling error', error);
      await sleep(1000);
    }
  }
};

const sendError = (socket: WebSocket, message: string, details: Record<string, unknown> = {}) => {
  sendEnvelope(socket, {
    topic: 'system',
    roomId: details['roomId']?.toString() ?? '',
    action: 'error',
    timestamp: nowIso(),
    payload: { message, ...details },
  });
};

const handleSystemMessage = (socket: WebSocket, envelope: MessageEnvelope<SystemPayload>) => {
  const action = envelope.action ?? 'ping';
  switch (action) {
    case 'join':
    case 'resume': {
      const { roomId, userId } = envelope.payload;
      if (!roomId) {
        sendError(socket, 'roomId is required to join');
        return;
      }
      joinRoom(socket, roomId, userId);
      sendEnvelope(socket, {
        topic: 'system',
        action: 'ack',
        roomId,
        timestamp: nowIso(),
        payload: { message: action, roomId, userId },
      });
      announcePresence(
        roomId,
        action === 'resume' ? 'presence.resume' : 'presence.join',
        { roomId, userId },
        socket,
      );
      break;
    }
    case 'leave': {
      leaveRoom(socket, 'leave');
      sendEnvelope(socket, {
        topic: 'system',
        action: 'ack',
        roomId: envelope.roomId,
        timestamp: nowIso(),
        payload: { message: 'left' },
      });
      break;
    }
    case 'ping': {
      const meta = context.get(socket);
      sendEnvelope(socket, {
        topic: 'system',
        action: 'pong',
        roomId: meta?.roomId ?? envelope.roomId,
        timestamp: nowIso(),
        payload: { message: 'pong' },
      });
      break;
    }
    default: {
      sendError(socket, 'Unsupported system action', { action });
    }
  }
};

const normaliseEnvelope = (incoming: Record<string, unknown>, socket: WebSocket): MessageEnvelope => {
  const topic = incoming['topic'];
  if (topic !== 'stroke' && topic !== 'object' && topic !== 'turn' && topic !== 'system') {
    throw new Error('Unknown topic');
  }
  const payload = incoming['payload'];
  if (typeof payload !== 'object' || payload === null) {
    throw new Error('payload must be an object');
  }
  const meta = context.get(socket);
  const roomIdValue = (incoming['roomId'] ?? (payload as Record<string, unknown>)['roomId']) as string | undefined;
  const roomId = roomIdValue ?? meta?.roomId;
  if (!roomId) {
    throw new Error('roomId missing from message');
  }
  const timestamp = typeof incoming['timestamp'] === 'string' ? (incoming['timestamp'] as string) : nowIso();
  return {
    topic,
    action: typeof incoming['action'] === 'string' ? (incoming['action'] as string) : undefined,
    roomId,
    timestamp,
    payload: payload as Record<string, unknown>,
  };
};

server.on('connection', (socket) => {
  socket.on('pong', () => {
    const meta = context.get(socket);
    if (meta) {
      meta.isAlive = true;
      meta.lastSeen = Date.now();
    }
  });

  socket.on('message', (data) => {
    try {
      if (payloadSize(data) > config.maxPayloadBytes) {
        sendError(socket, 'Payload too large');
        return;
      }
      const parsed = JSON.parse(bufferFromRawData(data).toString()) as Record<string, unknown>;
      const envelope = normaliseEnvelope(parsed, socket);
      if (envelope.topic === 'system') {
        handleSystemMessage(socket, envelope as MessageEnvelope<SystemPayload>);
        return;
      }
      const meta = context.get(socket);
      if (!meta || meta.roomId !== envelope.roomId) {
        sendError(socket, 'Join the room before sending events', { roomId: envelope.roomId });
        return;
      }
      meta.lastSeen = Date.now();
      meta.isAlive = true;
      if (!consumeRateLimit(meta.rateLimiter)) {
        sendError(socket, 'Rate limit exceeded', {
          roomId: envelope.roomId,
          retryInMs: meta.rateLimiter.refillIntervalMs,
        });
        return;
      }
      const message = {
        ...envelope,
        timestamp: nowIso(),
      };
      broadcast(envelope.roomId, message, socket);
    } catch (error) {
      console.error('Invalid message received', error);
      sendError(socket, 'Invalid message format');
    }
  });

  socket.on('close', () => {
    leaveRoom(socket, 'disconnect');
  });
});

server.on('listening', () => {
  console.log(`Realtime Gateway listening on ws://${config.host}:${config.port}`);
  void pollBackendEvents();
});

const heartbeat = () => {
  for (const sockets of rooms.values()) {
    for (const socket of sockets) {
      const meta = context.get(socket);
      if (!meta) {
        continue;
      }
      if (!meta.isAlive && Date.now() - meta.lastSeen > config.heartbeatToleranceMs) {
        console.warn('Terminating stale connection', meta.roomId, meta.userId);
        socket.terminate();
        leaveRoom(socket, 'disconnect');
        continue;
      }
      meta.isAlive = false;
      if (socket.readyState === WebSocket.OPEN) {
        socket.ping();
      }
    }
  }
};

setInterval(heartbeat, config.heartbeatIntervalMs);

const shutdown = async () => {
  console.log('[gateway] Shutting down');
  running = false;
  server.close();
};

process.on('SIGINT', () => {
  void shutdown().then(() => process.exit(0));
});

process.on('SIGTERM', () => {
  void shutdown().then(() => process.exit(0));
});
