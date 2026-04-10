"""
AI Restaurant Call Center — OpenAI Realtime API Version
========================================================
Bridges Twilio Media Streams <-> OpenAI Realtime API (WebSocket).

Key advantage: OpenAI supports g711_ulaw natively — same format as Twilio.
No audio transcoding needed! Twilio audio goes straight to OpenAI and back.
"""

import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

import websockets

from config import get_settings
from db import create_order, upsert_customer, update_order_status
from prompts import build_system_prompt, RECORD_ORDER_TOOL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("callcenter")

app = FastAPI(title="AI Call Center — OpenAI Realtime")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = get_settings()


# ────────────────────────────────────────────
# 1. Twilio Webhook
# ────────────────────────────────────────────
@app.post("/twilio/voice")
async def twilio_voice_webhook(request: Request):
    host = request.headers.get("host", "localhost:8000")
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    is_secure = "https" in forwarded_proto or "https" in str(request.url)
    protocol = "wss" if is_secure else "ws"

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
# 2. Voice Bridge: Twilio WS <-> OpenAI Realtime WS
# ────────────────────────────────────────────
@app.websocket("/twilio/stream")
async def twilio_media_stream(ws: WebSocket):
    """Bridge Twilio Media Stream to OpenAI Realtime API."""
    await ws.accept()
    logger.info("Twilio stream connected")

    stream_sid: str | None = None
    caller_phone: str | None = None
    openai_ws = None

    try:
        # Wait for Twilio "start" event
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("event") == "start":
                stream_sid = msg["start"]["streamSid"]
                caller_phone = msg["start"].get("customParameters", {}).get("caller")
                logger.info(f"Call started | stream={stream_sid} caller={caller_phone}")
                break

        # Build personalized system prompt
        system_prompt = build_system_prompt(caller_phone)

        # Connect to OpenAI Realtime API
        openai_url = f"{settings.openai_ws_url}?model={settings.openai_model}"

        openai_ws = await websockets.connect(
            openai_url,
            additional_headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
            },
            max_size=2**24,
        )
        logger.info("OpenAI Realtime WS connected")

        # Wait for session.created
        created_raw = await openai_ws.recv()
        created = json.loads(created_raw)
        logger.info(f"OpenAI session created: {created.get('type')}")

        # Send session.update with config
        session_update = {
            "type": "session.update",
            "session": {
                "instructions": system_prompt,
                "voice": settings.openai_voice,
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "silence_duration_ms": 800,
                },
                "tools": [RECORD_ORDER_TOOL],
                "tool_choice": "auto",
            }
        }
        await openai_ws.send(json.dumps(session_update))
        logger.info("Session update sent (g711_ulaw, server_vad, tools)")

        # Wait for session.updated confirmation
        updated_raw = await openai_ws.recv()
        updated = json.loads(updated_raw)
        logger.info(f"Session updated: {updated.get('type')}")

        # Run two concurrent tasks
        await asyncio.gather(
            _twilio_to_openai(ws, openai_ws),
            _openai_to_twilio(ws, openai_ws, stream_sid, caller_phone),
        )

    except WebSocketDisconnect:
        logger.info("Twilio stream disconnected")
    except Exception as e:
        logger.error(f"Bridge error: {e}", exc_info=True)
    finally:
        if openai_ws:
            await openai_ws.close()
        logger.info("Session ended")


async def _twilio_to_openai(twilio_ws: WebSocket, openai_ws):
    """Forward Twilio mulaw audio -> OpenAI input_audio_buffer.append.
    
    No transcoding needed! Both use g711_ulaw.
    """
    try:
        async for raw in twilio_ws.iter_text():
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                # Twilio sends base64 mulaw — forward directly to OpenAI
                audio_b64 = msg["media"]["payload"]

                audio_append = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64,
                }
                await openai_ws.send(json.dumps(audio_append))

            elif event == "stop":
                logger.info("Twilio stream stopped")
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"twilio->openai error: {e}")


async def _openai_to_twilio(twilio_ws: WebSocket, openai_ws,
                            stream_sid: str, caller_phone: str | None):
    """Receive OpenAI responses -> forward audio to Twilio, handle tool calls."""

    # Buffer for accumulating function call arguments
    fn_call_args: dict[str, str] = {}  # call_id -> accumulated JSON string
    fn_call_names: dict[str, str] = {}  # call_id -> function name

    try:
        async for raw in openai_ws:
            resp = json.loads(raw)
            event_type = resp.get("type", "")

            # ── Audio delta — send to Twilio ──
            if event_type == "response.audio.delta":
                audio_b64 = resp.get("delta", "")
                if audio_b64:
                    media_msg = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {"payload": audio_b64},
                    }
                    await twilio_ws.send_json(media_msg)

            # ── Function call arguments streaming ──
            elif event_type == "response.function_call_arguments.delta":
                call_id = resp.get("call_id", "")
                delta = resp.get("delta", "")
                fn_call_args.setdefault(call_id, "")
                fn_call_args[call_id] += delta

            # ── Function call complete ──
            elif event_type == "response.function_call_arguments.done":
                call_id = resp.get("call_id", "")
                fn_name = resp.get("name", "")
                args_json = resp.get("arguments", fn_call_args.get(call_id, "{}"))

                logger.info(f"Function call: {fn_name} | args: {args_json}")

                if fn_name == "record_order":
                    result = await _handle_record_order(
                        args_json, caller_phone
                    )

                    # Send function output back to OpenAI
                    fn_output = {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(result, ensure_ascii=False),
                        }
                    }
                    await openai_ws.send(json.dumps(fn_output))

                    # Trigger OpenAI to generate a response based on function output
                    await openai_ws.send(json.dumps({"type": "response.create"}))

                # Cleanup
                fn_call_args.pop(call_id, None)

            # ── Error handling ──
            elif event_type == "error":
                logger.error(f"OpenAI error: {resp.get('error', {})}")

            # ── Session events (debug) ──
            elif event_type in ("session.created", "session.updated"):
                logger.info(f"OpenAI: {event_type}")

            elif event_type == "input_audio_buffer.speech_started":
                logger.debug("User started speaking")

            elif event_type == "input_audio_buffer.speech_stopped":
                logger.debug("User stopped speaking")

    except websockets.exceptions.ConnectionClosed:
        logger.info("OpenAI WS closed")
    except Exception as e:
        logger.error(f"openai->twilio error: {e}")


async def _handle_record_order(args_json: str, caller_phone: str | None) -> dict:
    """Process the record_order function call."""
    try:
        args = json.loads(args_json)
        items = args.get("items", [])
        total = args.get("total", 0)
        address = args.get("address", "")
        notes = args.get("notes", "")

        # Upsert customer
        if caller_phone:
            upsert_customer(caller_phone, address=address)

        # Create order in Supabase (triggers Realtime -> dashboard + printer)
        order = create_order(
            customer_phone=caller_phone or "unknown",
            items=items,
            total=total,
            address=address,
            notes=notes,
        )

        order_id = order.get("id", "?")
        logger.info(f"Order #{order_id} created | total={total} JOD")

        return {
            "order_id": order_id,
            "message": f"\u062a\u0645 \u062a\u0633\u062c\u064a\u0644 \u0627\u0644\u0637\u0644\u0628 \u0631\u0642\u0645 {order_id} \u0628\u0646\u062c\u0627\u062d. \u0627\u0644\u0645\u0628\u0644\u063a {total} \u062f\u064a\u0646\u0627\u0631."
        }

    except Exception as e:
        logger.error(f"record_order error: {e}")
        return {"error": str(e)}


# ────────────────────────────────────────────
# 3. REST APIs for Dashboard
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-call-center-openai"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=True)
