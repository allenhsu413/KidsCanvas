# Prototype 里程碑盤點與待辦清單

本文檢視目前 InfiniteKidsCanvas 專案的開發進度，並規劃達成「可試玩 Prototype」所需的下一步工作。

## 目前進度概況

### Backend（Game Service）
- 已有 FastAPI 應用程式骨架與健康檢查路由，並透過設定模組集中管理環境參數。【F:backend/app/main.py†L5-L18】【F:backend/app/api/routes/health.py†L1-L12】【F:backend/app/core/config.py†L1-L31】
- 完成 `/api/rooms/{roomId}/objects` 物件提交端點，會計算 BBox 與 Anchor Ring、更新筆劃狀態、寫入審計紀錄並排入回合事件佇列。【F:backend/app/api/routes/rooms.py†L1-L33】【F:backend/app/services/objects.py†L1-L111】【F:backend/app/services/turns.py†L1-L52】
- 目前資料層採用記憶體資料庫與 Redis wrapper，方便之後替換為 PostgreSQL 與實體 Redis。【F:backend/app/core/database.py†L1-L138】【F:backend/app/core/redis.py†L1-L66】
- 具備物件提交流程的 pytest 覆蓋，驗證 turn queue 與審計紀錄是否寫入。【F:backend/app/tests/test_objects.py†L1-L77】

### Realtime Gateway
- 已有基於 `ws` 套件的 WebSocket 伺服器，能按房間維持連線、接收 stroke/object/turn 主題訊息並轉發給其他客戶端。【F:realtime/src/index.ts†L1-L83】
- Heartbeat/ping 機制與基本環境設定載入已就緒，但尚未串接後端或持久化訊息。【F:realtime/src/index.ts†L85-L98】【F:realtime/src/config.ts†L1-L10】

### AI Agent
- FastAPI 服務已建立 `/generate` 端點，並透過 `PatchGenerationPipeline` 回傳童話風格的佔位 patch payload，可作為整合時的假資料來源。【F:ai_agent/app/main.py†L1-L17】【F:ai_agent/app/pipelines/patch_generation.py†L1-L18】

### Frontend
- 目前僅有 placeholder README，尚未建立 canvas、WebSocket 或 API 互動的實作。【F:frontend/README.md†L1-L4】

## Prototype 缺口摘要
- 缺少房間建立/加入、筆劃同步與物件管理的 API／WS protocol 定義，前端無法實際連線。
- 尚未實作客戶端畫布（繪圖、平移縮放）、stroke 序列化/反序列化與撤銷/重做。
- AI patch 還未經過安全審核流程，也沒有 deliver 回 WebSocket 的回合事件。
- 資料持久層仍為 in-memory；需評估在 Prototype 階段是否導入最小可用的 PostgreSQL/Redis 或維持記憶體並加上重設工具。
- 自動化測試僅覆蓋物件提交流程，尚未覆蓋 WS、AI pipeline 或安全規則。

## 建議待辦與優先順序

### Phase 1：最小可用迴路（Backend / Realtime）
1. **房間與使用者流程**：新增房間建立/加入 API，定義使用者身份（host/participant）及回傳目前 strokes/objects snapshot。
2. **Stroke API 與佇列**：實作 `/api/rooms/{roomId}/strokes`（POST + 批次 GET）與對應的 WS broadcast 事件，確保畫布同步基礎可運作。
3. **WS Protocol 套件化**：定義統一訊息格式（含 `topic`, `payload`, `timestamp`），補上 reconnect/心跳回應處理與錯誤回傳。
4. **AI Turn webhook**：補上 turn queue 消費者（可先在 backend 內部使用 asyncio task），呼叫 AI Agent `/generate` 並寫入回合結果（含安全狀態 placeholder）。

### Phase 2：前端 Canvas Prototype
1. **Canvas 繪圖工具列**：使用原生 TS 建立無限畫布（平移、縮放、筆寬/顏色、觸控手勢）。
2. **WebSocket 同步**：串接 Realtime Gateway，實作 stroke buffering、節流與遠端筆劃渲染。
3. **物件提交 UI**：提供合併筆劃為物件的流程（框選 or 選擇列表），並呼叫 backend object API。
4. **AI Patch 顯示**：接收回合事件後在 anchor ring 內顯示 AI patch（先以假圖層 or 向量指令描繪），並顯示安全狀態。

### Phase 3：安全與審核基礎
1. **文本過濾**：在 backend 對物件標籤/提示進行黑名單檢查，失敗時阻擋並透過 WS 回傳安全訊息。
2. **影像佔位安全檢測**：為 AI patch 增加假實作的安全分數（可固定安全），為日後接入模型預留接口。
3. **審計查詢 API**：新增 `/api/rooms/{roomId}/audit` 用於追蹤事件。
4. **回放（基礎版）**：儲存 stroke/object/turn 事件順序，提供最簡回放 API（以 timestamp 過濾）。

### Phase 4：穩定性與部署準備
1. **持久化策略**：視 Prototype 需求決定是否接上本地 PostgreSQL/Redis，或至少提供 dump/restore 工具以避免伺服器重啟即遺失資料。
2. **測試覆蓋**：補上 WS integration 測試（pytest-asyncio）、AI pipeline 單元測試與前端單元測試（若建構工具允許）。
3. **開發腳本**：撰寫 `make dev`/`docker-compose` 方便一次啟動 backend、realtime、ai_agent。
4. **基本監控**：加入 Prometheus metrics 或最小 log 格式，以便 Prototype demo 時觀察系統狀態。

---
上述待辦可在 JIRA/Linear 等系統拆分為 Story/Task，優先完成 Phase 1 + Phase 2 即可達到「可試玩」原型目標，其餘 Phase 3-4 作為強化項目逐步補齊。
