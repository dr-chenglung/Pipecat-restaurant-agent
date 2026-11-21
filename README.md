**English** | [繁體中文](README.zh-TW.md)

# Yuelai Restaurant Voice Booking Agent (Pipecat + Gemini Live + Function Calling)

This is a **voice assistant that does real work**, built with [Pipecat](https://github.com/pipecat-ai/pipecat).
You open a web page, use your microphone to "call" Yuelai Restaurant (悅來餐廳), and talk with
Xiao Yue (小悅), the booking assistant. By voice, you can **check free tables, book a table,
look up a booking, change a booking, and cancel a booking**. Every change is written into a real
SQLite database through Gemini Live **function calling**, and you can see it at once in the staff dashboard.

The assistant speaks Taiwanese Mandarin. This project is based on the sibling project
[`Pipecat-interview-coach`](../Pipecat-interview-coach) (a voice mock interviewer).
That project shows how to give the bot a role; this project shows how the bot can **call tools to get work done**.

## Demo video

[docs/demo/restaurant-agent-demo.mp4](docs/demo/restaurant-agent-demo.mp4) (about 3 minutes):
a full booking call (about 1 minute), followed by an English explanation of the architecture and the tools.
In the video, the customer's voice is synthesized speech (edge-tts).

## How does it "do work"?

```
You say: "I want a table for four, tomorrow at 7 pm."
  → Gemini Live decides it must check, and calls the tool check_availability("2026-07-20", "19:00", 4)
  → Python really queries SQLite → the result goes back to the model
  → Xiao Yue: "We have a table tomorrow at 7 pm. May I have your name and phone number?"
  → After the customer confirms, it calls create_booking(...) → a new booking is saved
  → The staff dashboard (http://localhost:7861/admin) shows it within two seconds
```

There are five tools. They are direct functions in `server/bot-concierge.py`, and the real logic is in `server/booking_db.py`:

| Tool | What it does |
|---|---|
| `check_availability` | Checks if a time slot on a date has free seats; if it is full, it returns other free time slots |
| `create_booking` | Creates a booking (called only after the assistant repeats the details and the customer confirms) |
| `find_bookings` | Finds active bookings by phone number |
| `update_booking` | Changes the date, time, or party size (checks the new slot's capacity first) |
| `cancel_booking` | Cancels a booking and frees the seats |

Opening rules: lunch 11:00–13:30 and dinner 17:00–20:30 (last booking times, in 30-minute slots).
Each time slot holds at most 20 guests.

## Architecture

```
Browser client (5173)  ←WebRTC→  bot server (7860, Pipecat + Gemini Live)
                                     │ function calling
                                     ▼
                              booking_db.py ←→ server/data/bookings.db (SQLite)
                                     ▲
Staff browser  ←HTTP→  admin server (7861, FastAPI /admin + /api/bookings)
```

- **Browser client**: a Vite web page with the Pipecat JS client. It sends your voice and plays the bot's voice and video.
- **Bot server**: Python + Pipecat. It passes the audio to Gemini Live and runs the tools.
- **Gemini Live**: Google's speech-to-speech model. It listens, decides when to call a tool, and speaks the reply.
- **Admin server**: a FastAPI page that shows all bookings.

## Requirements

- **Windows** (the batch files are written for Windows)
- **Python 3.11+** and [**uv**](https://docs.astral.sh/uv/)
- **Node.js 18+**
- **Google Gemini API key**: <https://aistudio.google.com/apikey>

You need **only one key**: `GOOGLE_API_KEY`. No other service (Daily, ElevenLabs, Deepgram, OpenAI)
is used, because the browser connects to the server directly with SmallWebRTC.

## Setup

1. Copy `server/env.example` to `server/.env`, then set `GOOGLE_API_KEY=your-key`.
   (**Never commit `.env` to git.**)
2. Install the dependencies:

   ```powershell
   cd server
   uv sync
   cd ..\client
   npm install
   ```

## Run

```powershell
.\start.bat
```

This opens three windows:

- **Booking web page** → <http://localhost:5173> (click 「撥打訂位專線」 to start the call)
- **Staff dashboard** → <http://localhost:7861/admin> (watch bookings appear in the database)
- Bot server API → <http://localhost:7860>

Put the booking page and the staff dashboard side by side. Then you can see each booking appear
right after you make it by voice. To stop everything: `.\stop.bat`.

On the first start, the server creates `server/data/bookings.db` and adds a few sample bookings.
To reset the data, stop the services and delete that file.

## Tests

The booking data layer has unit tests (capacity, full slots, changes, cancellations that free seats, and more):

```powershell
cd server
uv run pytest
```

## Things to try

1. "我想訂明天晚上七點，四個人" (a table for four, tomorrow at 7 pm) → finish the booking and listen to Xiao Yue repeat the details.
2. Open the staff dashboard and see the new booking.
3. "我想查一下我的訂位" (I want to check my booking) → give your phone number.
4. "幫我改到八點" (change it to 8 pm) → the dashboard updates.
5. "取消好了" (please cancel it) → the dashboard shows it as cancelled.
6. Try a full slot: fill one time slot, then book again. Xiao Yue will suggest other times.

## How to customize

- **Role, call flow, and rules**: edit `server/prompts/system_prompt.md`.
  The server reads this file at the start of each call, and fills in today's date for `{{TODAY}}` and `{{WEEKDAY}}`.
- **Opening hours and capacity**: the constants at the top of `server/booking_db.py`.
- **Model and voice**: set them in `server/.env`:

  ```
  GEMINI_LIVE_MODEL=models/gemini-3.8-live
  GEMINI_LIVE_VOICE=Kore
  ```

  `server/env.example` uses `gemini-3.8-live`. If `GEMINI_LIVE_MODEL` is not set, the code uses
  `models/gemini-3.1-flash-live-preview` (the model used in the demo video). Other voices: Aoede, Charon, Fenrir, Puck.

## Further reading

A full tutorial (in Chinese) covers phone booking, the system architecture, and a walkthrough of this
project's code: [docs/tutorial/語音客服系統教學.md](docs/tutorial/語音客服系統教學.md)

## ⚠️ Security notes

`server/.env` holds a real API key, so `.gitignore` must exclude `.env`.
The staff dashboard has no login. Use it only as a local demo.
