import { WebSocketServer, WebSocket } from 'ws';
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

type ConnectionContext = {
  roomId: string;
  userId?: string;
  joinedAt: number;
};

const config = loadConfig();

const server = new WebSocketServer({ host: config.host, port: config.port });

const rooms = new Map<string, Set<WebSocket>>();
const context = new WeakMap<WebSocket, ConnectionContext>();

const nowIso = () => new Date().toISOString();

const sendEnvelope = <T>(socket: WebSocket, envelope: MessageEnvelope<T>) => {
  if (socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(envelope));
  }
};

const joinRoom = (socket: WebSocket, roomId: string, userId?: string) => {
  if (!rooms.has(roomId)) {
    rooms.set(roomId, new Set());
  }
  rooms.get(roomId)?.add(socket);
  context.set(socket, { roomId, userId, joinedAt: Date.now() });
};

const leaveRoom = (socket: WebSocket) => {
  const meta = context.get(socket);
  if (!meta) return;
  const roomSockets = rooms.get(meta.roomId);
  roomSockets?.delete(socket);
  if (roomSockets && roomSockets.size === 0) {
    rooms.delete(meta.roomId);
  }
  context.delete(socket);
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
        payload: { message: 'joined', roomId, userId },
      });
      break;
    }
    case 'leave': {
      leaveRoom(socket);
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
  socket.on('message', (data) => {
    try {
      const parsed = JSON.parse(data.toString()) as Record<string, unknown>;
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
    leaveRoom(socket);
  });
});

server.on('listening', () => {
  console.log(`Realtime Gateway listening on ws://${config.host}:${config.port}`);
});

const heartbeat = () => {
  for (const sockets of rooms.values()) {
    for (const socket of sockets) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.ping();
      }
    }
  }
};

setInterval(heartbeat, config.heartbeatIntervalMs);
