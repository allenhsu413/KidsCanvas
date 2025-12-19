# Prototype 里程碑盤點與待辦清單

本文檢視目前 InfiniteKidsCanvas 專案的開發進度，並規劃達成「可試玩 Prototype」所需的下一步工作。

## 目前進度概況

### Backend（Game Service）
- FastAPI lifespan 已掛載健康檢查、房間、筆劃路由，並在啟動時載入 TurnProcessor 以串接 AI 服務。【F:backend/app/main.py†L1-L46】【F:backend/app/api/routes/rooms.py†L1-L75】【F:backend/app/api/routes/strokes.py†L1-L41】
- 房間／筆劃／物件服務串連記憶體資料庫與 Redis 事件佇列，建立 Turn 後會推送 `ws:events` 讓後續即時廣播使用；對應流程已有 pytest 驗證。【F:backend/app/services/objects.py†L1-L122】【F:backend/app/services/strokes.py†L12-L104】【F:backend/app/services/turn_processor.py†L1-L214】【F:backend/app/tests/test_strokes.py†L12-L56】【F:backend/app/tests/test_turn_processor.py†L14-L73】
- 資料層仍採 in-memory Database 與 Redis wrapper，方便替換為真正的 PostgreSQL／Redis，但目前缺乏持久化能力。【F:backend/app/core/database.py†L1-L200】【F:backend/app/core/redis.py†L1-L87】

### Realtime Gateway
- `ws` 伺服器具備房間管理、presence 廣播、速率限制與心跳維護，可轉發客戶端送出的 stroke/object/turn 訊息。【F:realtime/src/index.ts†L1-L353】【F:realtime/src/config.ts†L1-L28】
- 目前尚未訂閱後端的 Redis 事件佇列，AI/Backend 產生的 `ws:events` 尚無法自動推送到連線用戶端。【F:backend/app/services/strokes.py†L12-L104】【F:backend/app/services/turn_processor.py†L151-L210】【F:realtime/src/index.ts†L177-L317】

### AI Agent
- FastAPI `/generate` 端點呼叫 `PatchGenerationPipeline` 回傳固定的童話風格 patch payload，作為 TurnProcessor 測試用的佔位回覆。【F:ai_agent/app/main.py†L1-L16】【F:ai_agent/app/pipelines/patch_generation.py†L1-L18】

### Frontend
- Vite + TypeScript 介面已組合工具列、物件面板與畫布容器，啟動時會建立房間、載入快照並連接 Realtime Gateway 與後端 API。【F:frontend/src/main.ts†L1-L169】
- `InfiniteCanvas` 提供無限畫布、筆刷設定、平移縮放與 AI Patch 覆疊渲染；UI 元件支援筆刷調整、物件勾選與提交流程。【F:frontend/src/canvas/InfiniteCanvas.ts†L1-L200】【F:frontend/src/ui/Toolbar.ts†L1-L59】【F:frontend/src/ui/ObjectPanel.ts†L1-L105】

## Prototype 缺口摘要
- Backend 會把 stroke/object/turn 事件推入 Redis，但 Realtime Gateway 尚未消費 `ws:events`／`ws:object-events`，導致 AI patch 與物件狀態無法廣播給其他玩家。【F:backend/app/services/strokes.py†L12-L104】【F:backend/app/services/turn_processor.py†L151-L210】【F:realtime/src/index.ts†L177-L317】
- TurnProcessor 目前僅回寫 `safety_status='passed'`，未串接 `content_safety` 檢核流程與封鎖邏輯，仍需補齊真正的兒童安全控管。【F:backend/app/services/turn_processor.py†L137-L210】
- 資料層仍為記憶體／本機 Redis wrapper，Prototype 若要支援多人長時間遊戲仍需導入可持久化的 PostgreSQL／Redis 或備援機制。【F:backend/app/core/database.py†L1-L200】【F:backend/app/core/redis.py†L1-L87】
- 目前測試聚焦在房間、筆劃、物件與 TurnProcessor 單元，尚缺 Realtime 橋接與端對端流程的整合測試。【F:backend/app/tests/test_rooms.py†L1-L87】【F:backend/app/tests/test_strokes.py†L12-L56】【F:backend/app/tests/test_turn_processor.py†L14-L73】

## 建議待辦與優先順序

### Phase 1：最小可用迴路（Backend / Realtime） — ⏳ 部分完成
- [x] **房間與使用者流程**：完成房間建立/加入 API，回傳當前 strokes/objects/turns 快照供前端初始化。【F:backend/app/api/routes/rooms.py†L1-L75】【F:backend/app/services/rooms.py†L1-L83】
- [x] **Stroke API 與佇列**：建立 `/api/rooms/{roomId}/strokes` POST/GET，並將事件推入 `ws:events` 供即時同步。【F:backend/app/api/routes/strokes.py†L1-L41】【F:backend/app/services/strokes.py†L12-L104】
- [x] **WS Protocol 套件化**：Realtime Gateway 具備統一 envelope、presence 與心跳控管，可轉發玩家送出的筆劃與系統訊息。【F:realtime/src/index.ts†L1-L353】
- [x] **AI Turn webhook**：TurnProcessor 會消費 `turn:events`、呼叫 AI Agent 並將結果寫回審計／Redis 佇列。【F:backend/app/services/turn_processor.py†L1-L214】
- [x] **Backend ↔ Realtime 橋接**：Realtime Gateway 輪詢 `/api/internal/events/next` 並將 `ws:events`／`ws:object-events` 事件廣播至房間連線，後端同步維護事件 timeline cursor。【F:backend/app/api/routes/events.py†L1-L78】【F:realtime/src/index.ts†L177-L317】

### Phase 2：前端 Canvas Prototype — ✅ 已完成
- [x] **Canvas 繪圖工具列**：`InfiniteCanvas` 支援平移、縮放、筆刷設定與繪圖事件；Toolbar 控制筆刷與視角重設。【F:frontend/src/canvas/InfiniteCanvas.ts†L12-L200】【F:frontend/src/ui/Toolbar.ts†L1-L59】
- [x] **WebSocket 同步**：前端建立 RealtimeClient，連線後同步遠端筆劃並處理心跳／重連。【F:frontend/src/main.ts†L42-L138】【F:frontend/src/ws/RealtimeClient.ts†L1-L123】
- [x] **物件提交 UI**：ObjectPanel 提供勾選筆劃與提交流程，呼叫後端物件 API。【F:frontend/src/ui/ObjectPanel.ts†L1-L105】【F:frontend/src/api/GameServiceClient.ts†L1-L91】
- [x] **AI Patch 顯示**：收到 turn 事件後於畫布 Anchor Ring 呈現 AI patch 覆層與狀態提示。【F:frontend/src/main.ts†L57-L87】【F:frontend/src/canvas/InfiniteCanvas.ts†L77-L108】

### Phase 3：安全與審核基礎
- [x] **文本過濾**：在 backend 對物件標籤/提示進行黑名單檢查，失敗時阻擋並透過 WS 回傳安全訊息。【F:backend/app/services/objects.py†L75-L190】
- [x] **影像佔位安全檢測**：AI patch 產生固定 `safetyScore` 並由 TurnProcessor 評估安全摘要，預留接入模型的接口。【F:ai_agent/app/pipelines/patch_generation.py†L1-L27】【F:backend/app/services/turn_processor.py†L36-L214】
- [x] **審計查詢 API**：新增 `/api/rooms/{roomId}/audit` 供事件追蹤查詢。【F:backend/app/api/routes/audit.py†L1-L36】
- [x] **回放（基礎版）**：Timeline 事件可透過 `/api/rooms/{roomId}/replay` 以 timestamp 篩選回放。【F:backend/app/api/routes/replay.py†L1-L51】【F:backend/app/core/redis.py†L1-L176】

### Phase 4：穩定性與部署準備
- [x] **持久化策略**：內建 JSON state file 作為 Prototype dump/restore 機制，並可切換至 PostgreSQL/Redis。【F:backend/app/core/database.py†L260-L420】【F:backend/app/core/config.py†L27-L49】
- [x] **測試覆蓋**：補上 WS replay/事件串流與 AI pipeline 測試，維持核心流程可回歸驗證。【F:backend/app/tests/test_audit_replay.py†L1-L72】【F:ai_agent/app/tests/test_patch_generation.py†L1-L9】
- [x] **開發腳本**：新增 `make dev` 與 `scripts/dev.sh`，一鍵啟動 backend、realtime、ai_agent、frontend。【F:Makefile†L1-L12】【F:scripts/dev.sh†L1-L33】
- [x] **基本監控**：提供 `/api/metrics` 作為最小監測指標輸出。【F:backend/app/api/routes/metrics.py†L1-L26】

---
## 從安裝到執行

以下步驟適用於本機開發環境（Python 3.11 + Node.js 18+）。

### 1) 安裝依賴
```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

# AI Agent
cd ../ai_agent
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

# Realtime Gateway
cd ../realtime
npm install

# Frontend
cd ../frontend
npm install
```

### 2) 設定必要環境變數（可選）
```bash
export GATEWAY_EVENT_SERVICE_KEY=dev-gateway-key
export GAME_SERVICE_URL=http://localhost:8000
```

### 3) 啟動服務
```bash
# 一鍵啟動（需要事先安裝依賴）
make dev
```

或單獨啟動：
```bash
cd backend && python -m uvicorn app.main:app --reload --port 8000
cd ai_agent && python -m uvicorn app.main:app --reload --port 8100
cd realtime && npm run dev
cd frontend && npm run dev -- --host
```
