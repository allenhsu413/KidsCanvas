export type Point = {
  x: number;
  y: number;
};

export type BBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type AnchorRing = {
  inner: BBox;
  outer: BBox;
};

export type Stroke = {
  id: string;
  authorId: string;
  color: string;
  width: number;
  path: Point[];
  objectId?: string | null;
  ts?: string;
  pending?: boolean;
};

export type CanvasObject = {
  id: string;
  ownerId: string;
  label?: string | null;
  status: string;
  bbox: BBox;
  anchorRing: AnchorRing;
  createdAt?: string;
};

export type TurnEventPayload = {
  turnId: string;
  sequence: number;
  status: string;
  safetyStatus?: string;
  patch?: Record<string, unknown>;
  reason?: string;
};

export type MessageEnvelope<T = Record<string, unknown>> = {
  topic: 'stroke' | 'object' | 'turn' | 'system';
  roomId: string;
  timestamp: string;
  payload: T;
  action?: string;
};

export type RoomSnapshot = {
  room: {
    id: string;
    name: string;
    turn_seq: number;
    created_at: string;
  };
  member: {
    room_id: string;
    user_id: string;
    role: string;
    joined_at: string;
  };
  members: Array<{
    room_id: string;
    user_id: string;
    role: string;
    joined_at: string;
  }>;
  strokes: Array<{
    id: string;
    room_id: string;
    author_id: string;
    color: string;
    width: number;
    ts: string;
    path: Point[];
    object_id: string | null;
  }>;
  objects: Array<{
    id: string;
    owner_id: string;
    label?: string | null;
    status: string;
    bbox: BBox;
    anchor_ring: AnchorRing;
  }>;
  turns: Array<{
    id: string;
    sequence: number;
    status: string;
    current_actor: string;
    source_object_id: string;
  }>;
};
