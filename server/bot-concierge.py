#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""悅來餐廳語音訂位客服 - Pipecat Voice Agent

以 Google Gemini Live + function calling 打造的餐廳訂位語音客服:
- 透過 WebRTC 與瀏覽器即時語音對話,體驗如同打電話到餐廳
- 角色為訂位專員「小悅」,可查空位、訂位、查詢、改期、取消
- 所有訂位異動透過工具呼叫寫入 SQLite(server/data/bookings.db),
  可於管理後台 http://localhost:7861/admin 即時檢視

Required AI services:
- Gemini Live (LLM)

Run the bot using::

    uv run bot-concierge.py
"""

import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from PIL import Image
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    LLMRunFrame,
    OutputImageRawFrame,
    SpriteFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

import booking_db

load_dotenv(override=True)

DB_PATH = booking_db.DEFAULT_DB_PATH

# We use lambdas to defer transport parameter creation until the transport
# type is selected at runtime.
transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_out_enabled=True,
        video_out_width=1024,
        video_out_height=576,
    ),
}

sprites = []
script_dir = os.path.dirname(__file__)

# Load sequential animation frames
for i in range(1, 26):
    # Build the full path to the image file
    full_path = os.path.join(script_dir, f"assets/agent0{i}.png")
    # Get the filename without the extension to use as the dictionary key
    # Open the image and convert it to bytes
    with Image.open(full_path) as img:
        sprites.append(OutputImageRawFrame(image=img.tobytes(), size=img.size, format=img.format))

# Create a smooth animation by adding reversed frames
flipped = sprites[::-1]
sprites.extend(flipped)

# Define static and animated states
quiet_frame = sprites[0]  # Static frame for when bot is listening
talking_frame = SpriteFrame(images=sprites)  # Animation sequence for when bot is talking

PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.md"


def build_system_instruction() -> str:
    """讀取 prompts/system_prompt.md,注入今天日期讓「明天」「下週五」能正確換算。"""
    today = date.today()
    weekday = "一二三四五六日"[today.weekday()]
    text = PROMPT_PATH.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->\s*", "", text, flags=re.S)  # 去掉檔頭說明註解
    return text.replace("{{TODAY}}", today.isoformat()).replace("{{WEEKDAY}}", weekday)


# ---------------------------------------------------------------------------
# 工具(direct functions):Pipecat 會自動從函式簽名與 docstring 產生 schema,
# 並在 Gemini Live 發出 function call 時執行,結果經 result_callback 回給模型。
# ---------------------------------------------------------------------------


async def check_availability(params: FunctionCallParams, date: str, time: str, party_size: int):
    """查詢某個日期與時段是否還有位子;客滿時會回傳同一天可以改訂的替代時段。

    Args:
        date: 日期,格式 YYYY-MM-DD。
        time: 時段,格式 HH:MM,必須是三十分鐘整的營業時段。
        party_size: 用餐人數。
    """
    result = booking_db.check_availability(DB_PATH, date, time, party_size)
    logger.info(f"tool check_availability({date}, {time}, {party_size}) -> {result}")
    await params.result_callback(result)


async def create_booking(
    params: FunctionCallParams, name: str, phone: str, date: str, time: str, party_size: int
):
    """建立訂位。務必先向客人覆誦確認所有資訊後才呼叫。成功會回傳訂位編號。

    Args:
        name: 訂位人姓名。
        phone: 訂位人電話號碼。
        date: 日期,格式 YYYY-MM-DD。
        time: 時段,格式 HH:MM。
        party_size: 用餐人數。
    """
    result = booking_db.create_booking(DB_PATH, name, phone, date, time, party_size)
    logger.info(f"tool create_booking({name}, {phone}, {date}, {time}, {party_size}) -> {result}")
    await params.result_callback(result)


async def find_bookings(params: FunctionCallParams, phone: str):
    """用電話號碼查詢客人所有有效的訂位。

    Args:
        phone: 訂位時留的電話號碼。
    """
    result = booking_db.find_bookings(DB_PATH, phone)
    logger.info(f"tool find_bookings({phone}) -> {result}")
    await params.result_callback(result)


async def update_booking(
    params: FunctionCallParams,
    booking_id: int,
    new_date: str | None = None,
    new_time: str | None = None,
    new_party_size: int | None = None,
):
    """修改既有訂位的日期、時段或人數,只需要傳想改的欄位。

    Args:
        booking_id: 訂位編號(先用 find_bookings 查出)。
        new_date: 新日期,格式 YYYY-MM-DD,不改就不要傳。
        new_time: 新時段,格式 HH:MM,不改就不要傳。
        new_party_size: 新人數,不改就不要傳。
    """
    result = booking_db.update_booking(
        DB_PATH, booking_id, new_date=new_date, new_time=new_time, new_party_size=new_party_size
    )
    logger.info(f"tool update_booking({booking_id}, {new_date}, {new_time}, {new_party_size}) -> {result}")
    await params.result_callback(result)


async def cancel_booking(params: FunctionCallParams, booking_id: int):
    """取消訂位。務必先向客人確認是哪一筆訂位後才呼叫。

    Args:
        booking_id: 訂位編號(先用 find_bookings 查出)。
    """
    result = booking_db.cancel_booking(DB_PATH, booking_id)
    logger.info(f"tool cancel_booking({booking_id}) -> {result}")
    await params.result_callback(result)


class TalkingAnimation(FrameProcessor):
    """Manages the bot's visual animation states.

    Switches between static (listening) and animated (talking) states based on
    the bot's current speaking status.
    """

    def __init__(self):
        super().__init__()
        self._is_talking = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process incoming frames and update animation state.

        Args:
            frame: The incoming frame to process
            direction: The direction of frame flow in the pipeline
        """
        await super().process_frame(frame, direction)

        # Switch to talking animation when bot starts speaking
        if isinstance(frame, BotStartedSpeakingFrame):
            if not self._is_talking:
                await self.push_frame(talking_frame)
                self._is_talking = True
        # Return to static frame when bot stops speaking
        elif isinstance(frame, BotStoppedSpeakingFrame):
            await self.push_frame(quiet_frame)
            self._is_talking = False

        await self.push_frame(frame, direction)


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    """Main bot execution function.

    Sets up and runs the bot pipeline including:
    - Gemini Live model integration
    - Voice activity detection
    - Animation processing
    - RTVI event handling
    """

    # Prepare the booking database (idempotent)
    booking_db.init_db(DB_PATH)
    booking_db.seed_db(DB_PATH)

    # Initialize the Gemini Live model
    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        settings=GeminiLiveLLMService.Settings(
            model=os.getenv("GEMINI_LIVE_MODEL", "models/gemini-3.1-flash-live-preview"),
            system_instruction=build_system_instruction(),
            voice=os.getenv("GEMINI_LIVE_VOICE", "Kore"),  # Aoede, Charon, Fenrir, Kore, Puck
        ),
    )

    # Direct functions: auto-registered as callable tools for the LLM
    context = LLMContext(
        tools=[
            check_availability,
            create_booking,
            find_bookings,
            update_booking,
            cancel_booking,
        ]
    )
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        realtime_service_mode=True,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    ta = TalkingAnimation()

    # Pipeline - assembled from reusable components
    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            ta,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    # Queue initial static frame so video starts immediately
    await worker.queue_frame(quiet_frame)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        # Kick off the conversation
        context.add_message(
            {"role": "developer", "content": "電話接通了,請接聽並開始服務。"},
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
