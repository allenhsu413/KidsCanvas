export interface RateLimitConfig {
  burst: number;
  refillIntervalMs: number;
}

export interface GatewayConfig {
  host: string;
  port: number;
  heartbeatIntervalMs: number;
  heartbeatToleranceMs: number;
  maxPayloadBytes: number;
  rateLimit: RateLimitConfig;
  gameServiceUrl: string;
  eventPollIntervalMs: number;
  eventServiceKey?: string;
}

const numberFromEnv = (key: string, fallback: number): number => {
  const value = process.env[key];
  if (value === undefined) {
    return fallback;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export const loadConfig = (): GatewayConfig => ({
  host: process.env.GATEWAY_HOST ?? '0.0.0.0',
  port: numberFromEnv('GATEWAY_PORT', 8080),
  heartbeatIntervalMs: numberFromEnv('GATEWAY_HEARTBEAT_MS', 15000),
  heartbeatToleranceMs: numberFromEnv('GATEWAY_HEARTBEAT_TOLERANCE_MS', 45000),
  maxPayloadBytes: numberFromEnv('GATEWAY_MAX_PAYLOAD_BYTES', 256 * 1024),
  rateLimit: {
    burst: numberFromEnv('GATEWAY_RATE_LIMIT_BURST', 40),
    refillIntervalMs: numberFromEnv('GATEWAY_RATE_LIMIT_REFILL_MS', 1000),
  },
  gameServiceUrl: process.env.GAME_SERVICE_URL ?? 'http://localhost:8000',
  eventPollIntervalMs: numberFromEnv('GATEWAY_EVENT_POLL_MS', 250),
  eventServiceKey: process.env.GATEWAY_EVENT_SERVICE_KEY,
});
