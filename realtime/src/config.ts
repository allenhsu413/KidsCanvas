export interface GatewayConfig {
  host: string;
  port: number;
  heartbeatIntervalMs: number;
}

export const loadConfig = (): GatewayConfig => ({
  host: process.env.GATEWAY_HOST ?? '0.0.0.0',
  port: Number(process.env.GATEWAY_PORT ?? 8080),
  heartbeatIntervalMs: Number(process.env.GATEWAY_HEARTBEAT_MS ?? 15000),
});
