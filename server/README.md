# Simple Chatbot Server（Gemini Live 版）

用 Pipecat 架的語音聊天機器人 server，透過瀏覽器用麥克風跟 Gemini Live API 即時語音對話。

這個資料夾是從官方 [pipecat-examples/simple-chatbot](https://github.com/pipecat-ai/pipecat-examples/tree/main/simple-chatbot) 精簡而來：只保留 `bot-gemini.py`，並且拿掉了 Daily transport（因為 `daily-python` 沒有 Windows wheel，裝不了），只用 **webrtc transport**，所以完全不需要 Daily 帳號、`DAILY_API_KEY`。

## Setup

1. 設定環境變數：`.env` 只需要填一個

   ```ini
   GOOGLE_API_KEY=          # 去 https://aistudio.google.com/apikey 申請
   ```

2. 安裝依賴：

   ```bash
   cd server
   uv sync
   ```

3. 啟動 server：

   ```powershell
   uv run bot-gemini.py
   ```

   預設監聽 `http://localhost:7860`，前端打 `/start` 建立 WebRTC session。

   如果你的 Windows 主控台編碼不是 UTF-8（例如把輸出重新導向到檔案、寫成排程工作等「非互動主控台」的情境），log 裡的 emoji 可能會噴 `UnicodeEncodeError: 'cp950' codec can't encode character...`。這時再加上 `PYTHONUTF8=1` 即可（PowerShell 用 `$env:PYTHONUTF8=1`，cmd.exe 用 `set PYTHONUTF8=1`，Git Bash 用 `export PYTHONUTF8=1`）。一般直接在終端機視窗裡執行不需要這個設定。

## Troubleshooting

- **`UnicodeEncodeError: 'cp950' codec can't encode character '\U0001f680'`**：只會在輸出不是接到真正的主控台時發生（重新導向到檔案、排程工作等），啟動前加 `PYTHONUTF8=1`（見上）。一般直接在終端機視窗執行不會遇到。
- **`daily-python` 安裝失敗 / 找不到 wheel**：這個套件沒有 Windows 版本。本專案的 `pyproject.toml` 已經把 `daily` extra 拿掉，`bot-gemini.py` 也移除了 Daily transport 的程式碼，只用 webrtc，不會遇到這個問題——如果你是從官方原始版本改的，記得同步拿掉。

## Gemini Live API 模型選用

Gemini Live API（即時雙向語音對話）目前有 **3 個免費可用**的模型（免費層有速率限制，但不用付費；資訊來源：[Gemini API 官方定價頁](https://ai.google.dev/gemini-api/docs/pricing)，2026-07 查詢）：

| Model ID | 官方名稱 | 定位 |
|---|---|---|
| `models/gemini-2.5-flash-native-audio-preview-12-2025` | Gemini 2.5 Flash Live Preview | 通用型即時語音對話（pipecat 函式庫的內建預設值） |
| `models/gemini-3.1-flash-live-preview` | Gemini 3.1 Flash Live Preview | 新一代、低延遲，**本專案目前採用這個** |
| `models/gemini-3.5-live-translate-preview` | Gemini 3.5 Live Translate | 專門做即時語音口譯/翻譯，不是一般聊天用途 |

三個模型都是走同一套 Live API（WebSocket 雙向串流），SDK 呼叫方式完全一樣，差別只在 `model` 字串跟少數幾個設定欄位的名稱。以下逐一說明。

---

### 1. `gemini-2.5-flash-native-audio-preview-12-2025`（Gemini 2.5 Flash Live Preview）

**特性**
- Native audio 架構：語音是模型直接生成的，不是「語音辨識→文字 LLM→文字轉語音」拼接出來的，音色比較自然、有語氣起伏。
- 輸入：audio / video / text；輸出：audio + text。
- Context window：input 131,072 tokens、output 8,192 tokens。
- Knowledge cutoff：2025 年 1 月。
- 支援 function calling（同步）、search grounding、`thinkingBudget`（思考預算）、affective dialog（情緒感知）、proactivity（主動發話）。
- **不支援** caching、code execution、file search、structured outputs、圖片生成。

**實測速度**（我們在這台機器上直連 Google，繞過 pipeline 量測，3 次取樣，回覆內容是「用五個字打招呼」這種極短句子）：
- 第一個聲音片段：1.9 ~ 2.5 秒
- 整輪對話完成：4.9 ~ 5.4 秒

這個延遲很穩定（不是網路抖動），是 Preview 版 + native-audio 架構 + 免費層的固有速度，回覆越長，生成時間會等比例拉長（因為是邊生成邊串流語音，語音生成速度大約跟播放時長同步）。

**使用時機**：如果不特別在意延遲、想要功能最全（affective dialog、proactivity 這些目前只有這代支援）、或需要跟舊版設定相容，適合用這個。目前是 pipecat `GeminiLiveLLMService` 沒指定 model 時的內建預設值。

**呼叫方式 — 原生 `google-genai` SDK**

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=GOOGLE_API_KEY)

config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],  # 這代模型不支援純 TEXT 回覆
    output_audio_transcription={},   # 想同時拿到文字逐字稿就加這個
    system_instruction="You are a helpful assistant.",
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
        )
    ),
    thinking_config={"thinkingBudget": 0},  # 思考預算，這代用這個欄位名稱
)

async with client.aio.live.connect(
    model="models/gemini-2.5-flash-native-audio-preview-12-2025",
    config=config,
) as session:
    await session.send_client_content(
        turns=types.Content(role="user", parts=[types.Part(text="hi")]),
        turn_complete=True,
    )
    async for response in session.receive():
        ...  # 處理 response.data（音訊 bytes）或 response.server_content.output_transcription
```

**呼叫方式 — pipecat `GeminiLiveLLMService`**

```python
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService

llm = GeminiLiveLLMService(
    api_key=os.getenv("GOOGLE_API_KEY"),
    settings=GeminiLiveLLMService.Settings(
        model="models/gemini-2.5-flash-native-audio-preview-12-2025",
        system_instruction="You are Chatbot, a friendly, helpful robot...",
        voice="Charon",  # Aoede, Charon, Fenrir, Kore, Puck
        thinking={"thinkingBudget": 0},
    ),
)
```

---

### 2. `gemini-3.1-flash-live-preview`（Gemini 3.1 Flash Live Preview）—— 本專案目前採用

**特性**
- 一樣是 native audio 架構，語音串流、輸入輸出模態跟上一代相同。
- 新增/改用 `thinkingLevel`（取代舊版的 `thinkingBudget`）來控制思考量，並支援 thought summaries（思考過程摘要）。
- 支援**非同步** function calling（可以在等工具回傳結果的同時繼續對話，不用整個卡住）。
- 128k token context window。

**實測速度**（同條件、同一台機器直連測試）：
- 第一個聲音片段：0.36 秒
- 整輪對話完成：2.8 秒

跟 2.5 版比起來，第一個聲音片段快了約 **6 倍**，整輪完成快了約 **2 倍**。這是目前 3 個免費模型裡最快的通用對話模型。

**使用時機**：任何在意「使用者講完話後多久聽到回應」的即時語音應用（例如我們這個 live chatbot）都應該優先選這個。除非你需要 2.5 版才有的 affective dialog / proactivity 功能，否則沒理由不用這個。

**呼叫方式 — 原生 `google-genai` SDK**

```python
config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    output_audio_transcription={},
    system_instruction="You are a helpful assistant.",
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
        )
    ),
    thinking_config={"thinkingLevel": "LOW"},  # 注意：欄位名稱跟 2.5 版不同
)

async with client.aio.live.connect(
    model="models/gemini-3.1-flash-live-preview",
    config=config,
) as session:
    ...  # 其餘用法跟上面完全一樣
```

**呼叫方式 — pipecat `GeminiLiveLLMService`**（`server/bot-gemini.py` 目前的實際設定）

```python
llm = GeminiLiveLLMService(
    api_key=os.getenv("GOOGLE_API_KEY"),
    settings=GeminiLiveLLMService.Settings(
        model="models/gemini-3.1-flash-live-preview",
        system_instruction="You are Chatbot, a friendly, helpful robot...",
        voice="Charon",
    ),
)
```

---

### 3. `gemini-3.5-live-translate-preview`（Gemini 3.5 Live Translate）

**特性**
- 專門為「即時口譯」設計，不是通用聊天模型：輸入某語言的語音，即時輸出另一語言的語音翻譯，而不是「回答問題」。
- 定價是三者中最貴的（付費層 input $3.50/1M tokens 或 $0.0053/分鐘音訊，output $21.00/1M tokens 或 $0.0315/分鐘音訊），免費層一樣可用但有速率限制。
- 呼叫時通常需要額外指定來源/目標語言相關參數，設定方式跟一般對話模型（`system_instruction` 決定人設）不同調性，不建議直接拿來套用聊天機器人的既有 prompt 邏輯。

**使用時機**：做即時口譯/多語言字幕、跨語言語音客服這類「翻譯」而非「對話」的產品。**不適合**當一般聊天機器人的 LLM 後端——如果你把它接到現在這個 `bot-gemini.py` 架構裡，system_instruction 人設設定很可能不會被當作預期的方式處理，因為這模型的任務目標是翻譯，不是角色扮演對話。

**呼叫方式**：架構跟前兩者一樣是 `client.aio.live.connect(model=..., config=...)`，但 `config` 需要換成翻譯情境的參數（例如指定語言方向），細節請查官方文件，這裡不展開示範以免誤用。

---

### 快速比較表

| | 2.5 Flash Live | 3.1 Flash Live | 3.5 Live Translate |
|---|---|---|---|
| 首個聲音片段（實測） | ~2 秒 | **~0.36 秒** | 未測（非對話用途） |
| 整輪完成（實測） | ~5 秒 | **~2.8 秒** | 未測 |
| 思考控制欄位 | `thinkingBudget` | `thinkingLevel` | 不適用 |
| Affective dialog / proactivity | ✅ | ❌（本次查證未見） | 不適用 |
| 非同步 function calling | ❌ | ✅ | 不適用 |
| 適合場景 | 功能最全的通用對話 | **低延遲即時對話（本專案採用）** | 即時口譯/翻譯 |

> 速度數字是在台灣本地網路環境、單次極短回覆的量測結果，僅供相對比較；實際延遲會隨你機器所在地區、當下 Google 端負載、回覆內容長短而變動。免費層模型的速度、可用性也可能隨時間調整，正式上線前建議自行重新量測。

## 虛擬角色 / 對嘴動畫（Talking Avatar）

畫面上那個機器人動畫是怎麼做的、能不能換角色、要不要做成真的對嘴，記錄在這裡，之後要實作再回來挑一個等級。

### 目前的實作方式

`bot-gemini.py` 第 69-120 行：把 `server/assets/robot01.png` ~ `robot025.png`（**25 張**）依序讀成一組動畫序列，尾巴再接上反過來的序列，變成可以來回循環、不會跳格的動畫。

- 圖片規格：`1024 x 576`、PNG、RGB —— 跟 `TransportParams(video_out_width=1024, video_out_height=576)` 設定的畫布一致，換圖時新圖也要同尺寸。
- 播放邏輯（`TalkingAnimation` class）只有兩種狀態，**跟語音內容完全無關**：
  - 收到 `BotStoppedSpeakingFrame`（沒在講話）→ 顯示第 1 張（靜止姿勢）
  - 收到 `BotStartedSpeakingFrame`（開始講話）→ 切成整組動畫循環播放

**換角色**：只要換掉 `server/assets/` 裡的圖片（同尺寸、同命名規則 `robotXX.png`，或改程式碼裡的檔名/張數），跟語音邏輯無關，隨時可以換。

### 對嘴動畫的技術等級

想讓嘴型「跟著講話內容變化」，難度跟品質分四個等級：

**等級 1：二元開關（目前這個專案的做法）**
只判斷「有沒有在講話」，不管內容，固定播同一組張合循環。跟語音完全無關。

**等級 2：音量驅動（Amplitude-driven）**
即時分析輸出音訊每個片段的音量（RMS），音量大嘴巴張越開、音量小或靜音就閉嘴。準備 3~5 張不同張合程度的嘴型圖，依當下音量對應顯示哪一張。
- 優點：不需要額外服務，純數學運算，延遲極低。
- 缺點：只反映音量大小，不是真的嘴型（例如「嗚」跟「啊」嘴型差很多，音量分析分不出來）。VTuber 軟體（如 Live2D）常用這招做即時對嘴，效果尚可。
- 這是**最容易在現有架構上加的下一步**，不需要新的第三方依賴。

**等級 3：音素/口型位驅動（Viseme-based，較準確）**
把語音拆解成音素（phoneme），對應到有限幾種標準口型位（viseme，例如 Preston Blair 或 Oculus OVR LipSync 的 15 種分類），需要「哪個時間點講哪個音」的時間軸資訊——來源通常是 TTS 引擎直接吐出的 phoneme/viseme 時間戳（例如 Azure、AWS Polly 有提供 "speech marks"），或事後用強制對齊（forced alignment）工具分析音檔反推。

> ⚠️ **Gemini Live 的原生語音輸出不會附帶 phoneme/viseme 時間戳**，要做這個等級得自己另外跑語音分析，實作成本較高。

**等級 4：神經網路即時生成（真正的「AI 換臉對嘴」）**
不是切換預畫好的嘴型圖，而是用深度學習模型即時把音訊直接轉換成連續、自然的臉部/嘴唇畫面（研究上如 Wav2Lip、SadTalker；商用如 D-ID、HeyGen、Simli、Tavus）。流程大致是：
1. 先提供一張人臉照片或錄一段影片建立「臉部模型」
2. 即時把音訊串流傳給雲端 API
3. 對方模型即時算出對應嘴型/表情，串流合成好的影片畫面回來

**pipecat 本身就有現成整合**，函式庫裡有 `pipecat/services/simli`、`pipecat/services/tavus`、`pipecat/services/heygen` 三個服務模組，都是「音訊進、對嘴影片出」的雲端服務。以 `SimliVideoService` 為例，架構上是把現在的 `TalkingAnimation` 這個 `FrameProcessor` 整個換成它，把 Gemini 生成的語音餵給 Simli，它會回傳對嘴的臉部影片畫面取代 sprite 動畫。這類服務要另外申請帳號、有自己的計費，跟 Gemini API 是分開的第三方服務。

### 比較表

| 等級 | 做法 | 跟語音內容的關聯度 | 額外依賴/成本 | 實作難度 |
|---|---|---|---|---|
| 1（目前） | 二元開關循環動畫 | 無（只看講話/靜止） | 無 | 已完成 |
| 2 | 音量驅動嘴型 | 音量大小 | 無 | 低，可直接加在現有 pipeline |
| 3 | Viseme 對嘴 | 音素等級 | 需要 phoneme 時間軸來源（Gemini 沒有，得自己算） | 中高 |
| 4 | 神經網路生成臉部影片 | 完全對應內容與情緒 | 需要 Simli/Tavus/HeyGen 等第三方帳號與計費 | 低（用 pipecat 現成整合）但要另外付費 |

### 建議

- 想要「比現在更有反應」又不想接外部服務 → 做**等級 2**（音量驅動），投報率最高。
- 想要真正的數位人等級效果、不介意額外服務與費用 → 直接接 **Simli/Tavus/HeyGen**（等級 4），pipecat 已經幫你把整合寫好了，換掉 `TalkingAnimation` 那段即可。
- 等級 3 因為 Gemini Live 沒有現成的 viseme 時間戳，投入報酬比較不划算，除非之後刻意換一個會吐 viseme 時間戳的 TTS 服務。
