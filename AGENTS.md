# AGENTS.md

## 專案定位
**InfiniteKidsCanvas**：兒童向「AI 畫畫接龍」原型。  
核心體驗：使用者在無邊際畫布畫圖，AI 僅沿著使用者物件周邊接續創作，且內容需符合兒童安全。

## Prototype 必做範圍（MVP）
1. 單一房間、多使用者即時同步畫布（筆劃/物件/回合事件）。
2. 支援無邊際畫布的平移/縮放與基本繪圖。
3. 多筆劃可合併為 Object，伺服器計算並保存 `bbox`。
4. AI 接龍只可在 `Anchor Ring` 內生成 patch，並盡量保持同屏可見。
5. 建立回合事件流（User → AI → User），可追溯審計。
6. 內容安全採雙層檢查（文字規則 + 圖像安全模型）。

## 關鍵需求（精簡）
- **即時性**：筆劃同步端到端延遲目標 ≤ 300ms（行動網路環境）。
- **AI 回應時間**：patch 回傳目標 2–6 秒。
- **可追溯性**：所有 AI 輸出與安全判定需記錄 audit log。
- **可擴展性**：Game Service 可水平擴充；筆劃資料支援壓縮（delta + gzip）。

## 系統與技術基準
- Backend：Python 3.11 + FastAPI
- Realtime：WebSocket（`/ws/rooms/{roomId}`）
- DB：PostgreSQL + Redis
- Frontend：TypeScript + Canvas（行動瀏覽器優先）

## API / 通道契約（最小集合）
- `POST /api/rooms/{roomId}/objects`：建立物件（含 bbox）
- `WS /ws/rooms/{roomId}`：廣播 `stroke` / `object` / `turn`
- `POST /api/turns/{turnId}/retry`：僅 moderator/parent 可重試

## 核心資料模型（最小集合）
- `Stroke`：筆劃資料（path、color、width、author、objectId?）
- `Object`：使用者物件（bbox、owner、status）
- `Turn`：回合狀態（pending / ai_generating / delivered / blocked）
- `AgentPatch`：AI 輸出（payload、anchorRegion、style、safetyScore）
- `SafetyReview`：安全檢測結果（passed、labels、reason）
- `AuditLog`：事件稽核紀錄

## Anchor Ring 規則（硬性）
1. `padding = max(bbox.w, bbox.h) * 0.4` 形成外環。
2. AI patch 必須落在環帶內。
3. 與既有元素重疊 > 30% 時必須重採樣位置。
4. 需通過同屏可見檢查（與 viewport 交集 ≥ 70%），不符則內縮/平移策略優先。

## 兒童安全規範（硬性）
- 風格：童話、明亮、友善角色。
- 禁止：暴力、血腥、成人、仇恨、毒品/酒精/武器、危險行為、個資內容。
- 流程：
  1) 文本提示過濾 → 2) 圖像安全偵測（NSFW/暴力）→ 3) 不通過則遮罩並提供安全替代。

## 開發規範
- Python：PEP8 + `black` + `ruff`
- 前端：`eslint` + `prettier`
- 測試：`pytest -q`（含 `pytest-asyncio` 測 WS），覆蓋率目標 ≥ 80%
- Commit 格式：`[module] action: summary`
- PR 必附：測試結果、風險說明（效能/安全/相依）

## 建議目錄
```text
/backend/app/{api,ws,core,models,services,tests}
/frontend/src/{canvas,ws,ui}
/docs
```
