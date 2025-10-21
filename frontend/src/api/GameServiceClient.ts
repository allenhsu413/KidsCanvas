import type { AnchorRing, RoomSnapshot, Stroke } from '../types';

type ObjectCommitResponse = {
  object: {
    id: string;
    room_id: string;
    owner_id: string;
    label?: string | null;
    status: string;
    bbox: AnchorRing['inner'];
    anchor_ring: AnchorRing;
    created_at: string;
  };
  turn: {
    id: string;
    room_id: string;
    sequence: number;
    status: string;
    current_actor: string;
    source_object_id: string;
    created_at: string;
  };
};

type StrokeApiPayload = {
  id: string;
  room_id: string;
  author_id: string;
  color: string;
  width: number;
  ts: string;
  path: Array<{ x: number; y: number }>;
  object_id: string | null;
};

export class GameServiceClient {
  constructor(private readonly baseUrl: string) {}

  async createRoom(name: string, hostId: string): Promise<RoomSnapshot> {
    return this.post<RoomSnapshot>('/rooms', { name, host_id: hostId });
  }

  async joinRoom(roomId: string, userId: string): Promise<RoomSnapshot> {
    return this.post<RoomSnapshot>(`/rooms/${roomId}/join`, {
      user_id: userId,
    });
  }

  async createStroke(
    roomId: string,
    stroke: Pick<Stroke, 'authorId' | 'color' | 'width' | 'path'>,
  ): Promise<Stroke> {
    const payload = {
      author_id: stroke.authorId,
      color: stroke.color,
      width: stroke.width,
      path: stroke.path,
    };
    const response = await this.post<{ stroke: StrokeApiPayload }>(
      `/rooms/${roomId}/strokes`,
      payload,
    );
    return this.transformStroke(response.stroke);
  }

  async listStrokes(roomId: string): Promise<Stroke[]> {
    const response = await this.get<{ strokes: StrokeApiPayload[] }>(
      `/rooms/${roomId}/strokes`,
    );
    return response.strokes.map((stroke) => this.transformStroke(stroke));
  }

  async commitObject(
    roomId: string,
    ownerId: string,
    strokeIds: string[],
    label?: string,
  ): Promise<ObjectCommitResponse> {
    return this.post<ObjectCommitResponse>(`/rooms/${roomId}/objects`, {
      owner_id: ownerId,
      stroke_ids: strokeIds,
      label,
    });
  }

  private transformStroke(stroke: StrokeApiPayload): Stroke {
    return {
      id: stroke.id,
      authorId: stroke.author_id,
      color: stroke.color,
      width: stroke.width,
      path: stroke.path,
      objectId: stroke.object_id,
      ts: stroke.ts,
    };
  }

  private async get<T>(path: string): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`GET ${path} failed: ${response.status}`);
    }
    return (await response.json()) as T;
  }

  private async post<T>(
    path: string,
    body: Record<string, unknown>,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`POST ${path} failed: ${response.status} ${detail}`);
    }
    return (await response.json()) as T;
  }
}
