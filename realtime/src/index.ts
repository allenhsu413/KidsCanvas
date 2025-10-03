import { WebSocketServer, WebSocket } from 'ws';
import { loadConfig } from './config.js';

interface StrokeMessage {
  type: 'stroke';
  payload: Record<string, unknown>;
}

interface ObjectMessage {
  type: 'object';
  payload: Record<string, unknown>;
}

interface TurnMessage {
  type: 'turn';
  payload: Record<string, unknown>;
}

type RoomMessage = StrokeMessage | ObjectMessage | TurnMessage;

type ConnectionContext = {
  roomId: string;
};

const config = loadConfig();

const server = new WebSocketServer({ host: config.host, port: config.port });

const rooms = new Map<string, Set<WebSocket>>();
const context = new WeakMap<WebSocket, ConnectionContext>();

const joinRoom = (socket: WebSocket, roomId: string) => {
  if (!rooms.has(roomId)) {
    rooms.set(roomId, new Set());
  }
  rooms.get(roomId)?.add(socket);
  context.set(socket, { roomId });
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

const broadcast = (roomId: string, message: RoomMessage, sender?: WebSocket) => {
  const roomSockets = rooms.get(roomId);
  if (!roomSockets) return;
  const raw = JSON.stringify(message);
  for (const socket of roomSockets) {
    if (socket !== sender && socket.readyState === WebSocket.OPEN) {
      socket.send(raw);
    }
  }
};

server.on('connection', (socket) => {
  socket.on('message', (data) => {
    try {
      const parsed = JSON.parse(data.toString()) as RoomMessage & {
        roomId?: string;
        topic?: string;
      };
      if (!parsed?.payload || typeof parsed.payload !== 'object') {
        return;
      }
      const roomId = parsed.payload['roomId'] ?? parsed['roomId'];
      if (typeof roomId !== 'string') {
        return;
      }
      if (!context.has(socket)) {
        joinRoom(socket, roomId);
      }
      broadcast(roomId, parsed, socket);
    } catch (error) {
      console.error('Invalid message received', error);
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
