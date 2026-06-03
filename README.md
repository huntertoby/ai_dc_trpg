# ⚔️ AI DC TRPG: 異世界冒險者系統 (AI-Powered Discord TRPG)

![Version](https://img.shields.io/badge/version-v0.2-blue.svg)
![Python](https://img.shields.io/badge/Python-3.8+-green.svg)
![Discord.py](https://img.shields.io/badge/Discord.py-2.0+-7289DA.svg)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063.svg)

一個結合了 **大型語言模型 (LLM)** 與 **Discord 互動介面** 的全自動化 TRPG (桌上角色扮演遊戲) 系統。玩家只需透過自然語言描述，AI 就能為其量身打造獨一無二的角色、技能與史詩裝備。

---

## 🌟 核心特色

- **🎭 AI 角色塑造**：透過自然語言輸入，AI 會自動推導角色的職業、種族、背景故事與性格特質，並生成對應的初始數值。
- **⚔️ 智能裝備與技能生成**：
    - **平衡器系統 (Balancer)**：內建雙軌制預算平衡演算法，確保 AI 生成的裝備在擁有酷炫描述的同時，數值依然合理。
    - **動態機制解析**：AI 能直接生成具備傷害公式、冷卻時間與特殊特效的技能。
- **📱 互動式角色面板**：採用全按鈕式 (Button-based) 介面，讓玩家能直觀地管理背包、更換裝備、分配屬性點。
- **💾 穩定持久化儲存**：基於 Pydantic 的嚴謹資料模型，並使用 JSON 平面化資料庫，確保角色資料的安全性與可擴展性。
- **🌐 模組化架構**：清晰的分層設計（Logic, UI, Core, DB, Services），便於開發者快速擴充新功能。

---

## 🎮 遊玩方法

### 1. 踏出第一步：創建角色
使用 `/生成角色` 指令，並在 `description` 中輸入你想扮演的角色特質。
- **範例**：`/生成角色 description:一個操縱星辰之力的精靈占星術師`
- AI 會根據你的描述生成：**背景故事、性格缺陷、初始技能與全套基礎裝備**。

### 2. 核心操作中心：角色面板
使用 `/角色面板` 是你冒險中最常用的指令。這是一個整合式的互動介面，包含：
- ⚜️ **屬性分配**：新角色擁有 5 點初始點數，可自由分配至力量、敏捷等六大屬性。
- 🎒 **背包管理**：直接點擊背包按鈕，可以查看、穿戴、更換或丟棄你的戰利品。
- 📜 **技能清單**：查看 AI 為你量身打造的技能機制、傷害公式與特效。
- 🎭 **多重角色管理**：支援同時擁有多個角色，隨時透過面板或 `/切換角色` 來改變身分

---

## 🛠️ 技術架構

### 系統分層
- **`main.py`**: Discord 機器人進入點，處理指令分發與事件監聽。
- **`core/`**: 核心業務邏輯。
    - `models.py`: 使用 Pydantic 定義所有資料模型（角色、裝備、技能、地圖等）。
    - `character.py`: 處理屬性計算、裝備邏輯與狀態更新。
    - `generator/`: AI 生成核心，包含裝備與技能的平衡邏輯。
- **`services/`**: 外部服務串接。
    - `llm_service.py`: 異步串接本地 LLM (如 LM Studio) 或 OpenAI API。
- **`ui/`**: 豐富的 Discord UI。
    - `views.py`: 複雜的按鈕式交互與選單邏輯。
    - `embeds.py`: ANSI 格式化的角色卡與資訊面板渲染。
- **`db/`**: 儲存層。
    - `storage.py`: Repository 模式，負責角色 JSON 檔案的 CRUD 操作。

---

## 🚀 快速開始

### 1. 環境準備
- **Python 3.8+**
- **LM Studio** (或其他支援 OpenAI API 格式的後端)：
    - 運行本地伺服器於 `http://localhost:1234`
    - 載入合適的 LLM 模型 (推薦 Qwen2 或 Llama3 系列)

### 2. 安裝依賴
```bash
pip install discord.py openai pydantic python-dotenv
```

### 3. 配置環境變數
建立 `.env` 檔案並填入：
```env
DISCORD_TOKEN=你的機器人Token
```

### 4. 啟動冒險
```bash
python main.py
```

---

## 📜 未來展望 (Roadmap)

### 第一階段：世界觀與探索 (World & Exploration)
- [ ] **動態地圖系統**：啟動 `AreaSchema` 邏輯，玩家可在區域間移動並觸發隨機事件。
- [ ] **AI 敘事 DM**：整合 LLM 進行場景描述與 NPC 對話，實現真正的「無人守備」TRPG。

### 第二階段：深度戰鬥 (Advanced Combat)
- [ ] **全按鈕式戰鬥流程**：從指令化轉向視覺化，支援行動順序 (Initiative)、目標選擇與戰鬥特效展示。
- [ ] **組隊系統**：支援玩家組隊共同挑戰地下城。

### 第三階段：經濟與成長 (Economy & Growth)
- [ ] **公會與任務系統**：啟動 `QuestSchema` 邏輯，AI 會根據玩家等級動態生成公會委託。
- [ ] **拍賣場/商店**：實現玩家間的資源交易與 AI 商人的動態物價。

---

## 🤝 貢獻指南

歡迎任何形式的貢獻！無論是回報 Bug、提出新功能建議，或是直接提交 PR，我們都非常歡迎。

- **開發原則**：保持 UI 與邏輯的分離，所有新資料結構必須經過 `models.py` 的驗證。

---

## ⚖️ 授權協議

本專案採用 [MIT License](LICENSE) 授權。
