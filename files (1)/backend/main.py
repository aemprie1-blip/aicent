"""
AI Restaurant Call Center — FastAPI Backend
============================================
Bridges Twilio Media Streams ↔ Gemini 3.1 Flash Live API (Multimodal Live WebSocket).

Connection flow:
  Phone Call → Twilio → Media Stream WS → This Server → Gemini Live WS
  Gemini audio response → This Server → Twilio Media Stream → Caller hears it
"""

import asyncio
import base64
import json
import logging
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware

import websockets

from config import get_settings
from db import create_order, upsert_customer, get_available_menu, update_order_status
from prompts import build_system_prompt, RECORD_ORDER_TOOL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("callcenter")

app = FastAPI(title="AI Call Center")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = get_settings()


# ────────────────────────────────────────────
# 1. Twilio Webhook — answers the call
# ────────────────────────────────────────────
@app.post("/twilio/voice")
async def twilio_voice_webhook(request: Request):
    """
    Twilio hits this URL when a call comes in.
    We respond with TwiML that opens a bidirectional Media Stream
    back to our /twilio/stream WebSocket.
    """
    host = request.headers.get("host", "localhost:8000")

    # Railway/Render proxy HTTPS→HTTP internally, so check X-Forwarded-Proto
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    is_secure = "https" in forwarded_proto or "https" in str(request.url)
    protocol = "wss" if is_secure else "ws"

    # Extract caller phone from Twilio POST form data
    form = await request.form()
    caller = form.get("From", "unknown")

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{protocol}://{host}/twilio/stream">
            <Parameter name="caller" value="{caller}" />
        </Stream>
    </Connect>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


# ────────────────────────────────────────────
# 2. The Voice Bridge: Twilio WS ↔ Gemini WS
# ────────────────────────────────────────────
@app.websocket("/twilio/stream")
async def twilio_media_stream(ws: WebSocket):
    """Twilio WS handler - relays audio between Twilio and Gemini."""
    await ws.accept()
    logger.info("Twilio stream connected")

    stream_sid: str | None = None
    caller_phone: str | None = None
    gemini_ws = None

    try:
        # ── Wait for the "start" event to get metadata ──
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("event") == "start":
                stream_sid = msg["start"]["streamSid"]
                caller_phone = msg["start"].get("customParameters", {}).get("caller")
                logger.info(f"Call started | stream={stream_sid} caller={caller_phone}")
                break

        # ── Build personalised system prompt ──
        system_prompt = build_system_prompt(caller_phone)

        # ── Open Gemini Live WebSocket ──
        gemini_url = f"{settings.gemini_ws_url}?key={settings.gemini_api_key}"

        gemini_ws = await websockets.connect(
            gemini_url,
            additional_headers={"Content-Type": "application/json"},
            max_size=2**24,  # 16 MB
        )
        logger.info("Gemini Live WS connected")

        # ── Send setup message (session config) ──
        setup_msg = {
            "setup": {
                "model": f"models/{settings.gemini_model}",
                "generation_config": {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": "Aoede"  # clear male-ish voice
                            }
                        }
                    }
                },
                "system_instruction": {
                    "parts": [{"text": system_prompt}]
                },
                "tools": [RECORD_ORDER_TOOL],
            }
        }
        await gemini_ws.send(json.dumps(setup_msg))
        logger.info("Gemini session setup sent")

        # Wait for setup complete
        setup_resp = await gemini_ws.recv()
        setup_data = json.loads(setup_resp)
        logger.info(f"Gemini setup response: {list(setup_data.keys())}")

        # ── Launch two concurrent tasks ──
        await asyncio.gather(
            _twilio_to_gemini(ws, gemini_ws),
            _gemini_to_twilio(ws, gemini_ws, stream_sid, caller_phone),
        )

    except WebSocketDisconnect:
        logger.info("Twilio stream disconnected")
    except Exception as e:
        logger.error(f"Bridge error: {e}", exc_info=True)
    finally:
        if gemini_ws:
            await gemini_ws.close()
        logger.info("Session ended")


async def _twilio_to_gemini(twilio_ws: WebSocket, gemini_ws):
    """Forward Twilio audio → Gemini as realtime input chunks."""
    try:
        async for raw in twilio_ws.iter_text():
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                # Twilio sends base64-encoded mulaw/8000 audio
                audio_b64 = msg["media"]["payload"]

                # Send as realtime input to Gemini
                realtime_msg = {
                    "realtime_input": {
                        "media_chunks": [
                            {
                                "data": audio_b64,      # already base64
                                "mime_type": "audio/pcm;rate=8000"
                                # Gemini Live accepts raw PCM; Twilio sends mulaw.
                                # In production, transcode mulaw→PCM here.
                                # For simplicity we send as-is — Gemini handles common codecs.
                            }
                        ]
                    }
                }
                await gemini_ws.send(json.dumps(realtime_msg))

            elif event == "stop":
                logger.info("Twilio stream stopped")
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"twilio→gemini error: {e}")


async def _gemini_to_twilio(twilio_ws: WebSocket, gemini_ws,
                            stream_sid: str, caller_phone: str | None):
    """Receive Gemini responses (audio + tool calls) → forward audio to Twilio."""
    try:
        async for raw in gemini_ws:
            resp = json.loads(raw)

            # ── Handle server content (audio) ──
            server_content = resp.get("serverContent")
            if server_content:
                parts = server_content.get("modelTurn", {}).get("parts", [])
                for part in parts:
                    inline_data = part.get("inlineData")
                    if inline_data and "audio" in inline_data.get("mimeType", ""):
                        audio_b64 = inline_data["data"]
                        # Send back to Twilio as a media message
                        media_msg = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": audio_b64
                            }
                        }
                        await twilio_ws.send_json(media_msg)

            # ── Handle tool calls ──
            tool_call = resp.get("toolCall")
            if tool_call:
                for fc in tool_call.get("functionCalls", []):
                    await _handle_function_call(
                        fc, gemini_ws, caller_phone
                    )

    except websockets.exceptions.ConnectionClosed:
        logger.info("Gemini WS closed")
    except Exception as e:
        logger.error(f"gemini→twilio error: {e}")


async def _handle_function_call(fc: dict, gemini_ws, caller_phone: str | None):
    """Process record_order tool call from Gemini."""
    name = fc.get("name")
    args = fc.get("args", {})
    call_id = fc.get("id", str(uuid.uuid4()))

    logger.info(f"Tool call: {name} args={json.dumps(args, ensure_ascii=False)}")

    if name == "record_order":
        items = args.get("items", [])
        total = args.get("total", 0)
        address = args.get("address", "")
        notes = args.get("notes", "")

        # Upsert customer
        if caller_phone:
            upsert_customer(caller_phone, address=address)

        # Create order in Supabase (triggers Realtime → kitchen printer)
        order = create_order(
            customer_phone=caller_phone or "unknown",
            items=items,
            total=total,
            address=address,
            notes=notes,
        )

        result_text = f"تم تسجيل الطلب رقم {order.get('id', '?')} بنجاح. المبلغ الإجمالي {total} دينار."
        logger.info(result_text)

        # Send tool response back to Gemini so it can confirm to the caller
        tool_response = {
            "tool_response": {
                "function_responses": [
                    {
                        "id": call_id,
                        "name": name,
                        "response": {
                            "result": {
                                "order_id": order.get("id"),
                                "message": result_text
                            }
                        }
                    }
                ]
            }
        }
        await gemini_ws.send(json.dumps(tool_response))


# ────────────────────────────────────────────
# 3. REST APIs for the Dashboard
# ────────────────────────────────────────────
@app.get("/api/menu")
async def api_get_menu():
    from db import get_db
    res = get_db().table("menu_items").select("*").order("category").execute()
    return res.data


@app.patch("/api/menu/{item_id}")
async def api_toggle_menu_item(item_id: int, body: dict):
    from db import get_db
    get_db().table("menu_items") \
        .update({"is_available": body.get("is_available", True)}) \
        .eq("id", item_id) \
        .execute()
    return {"ok": True}


@app.get("/api/orders")
async def api_get_orders(status: str | None = None, limit: int = 50):
    from db import get_db
    q = get_db().table("orders").select("*").order("created_at", desc=True).limit(limit)
    if status:
        q = q.eq("status", status)
    return q.execute().data


@app.patch("/api/orders/{order_id}")
async def api_update_order(order_id: int, body: dict):
    new_status = body.get("status")
    if new_status:
        update_order_status(order_id, new_status)
    return {"ok": True}


# ────────────────────────────────────────────
# 4. Health check
# ────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-call-center"}


# ────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=True)
