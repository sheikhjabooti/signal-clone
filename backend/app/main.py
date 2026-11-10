import asyncio
from contextlib import asynccontextmanager, suppress
import io
import json
import logging
import re
import secrets
from pathlib import Path
from fastapi import FastAPI, File, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.exc import OperationalError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from .config import Settings
from .database import Database
from .migrate import migrate
from .realtime import Hub
from .schemas import (AuthInput, ContactInput, DirectInput, GroupInput, GroupNameInput,
                      MemberInput, MessageInput, ProfileInput, ReactionInput, ReceiptInput, RoleInput)
from .security import AppError, Identity, RateLimiter
from .seed import seed_demo
from .services import Services

logger = logging.getLogger("signal")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    hub, limiter = Hub(), RateLimiter()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        await run_in_threadpool(migrate, settings.database_url)
        db = Database(settings)
        application.state.db = db
        application.state.services = Services(db, settings)
        application.state.hub = hub
        if settings.seed_demo:
            await run_in_threadpool(seed_demo, db)
        yield
        await hub.close_all()
        await run_in_threadpool(db.close)

    application = FastAPI(title="Signal-style messaging API", version="1.0.0", lifespan=lifespan)
    application.add_middleware(CORSMiddleware, allow_origins=list(settings.origins), allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "X-CSRF-Token"])

    def svc() -> Services:
        return application.state.services

    async def identity(request: Request, write: bool = False) -> Identity:
        who = await run_in_threadpool(svc().identity, request.cookies.get(settings.cookie_name))
        if write and not secrets.compare_digest(request.headers.get("x-csrf-token", ""), who.csrf_token):
            raise AppError(403, "csrf_failed", "Your session needs a refresh. Reload and try again.")
        return who

    def decorate(conversation):
        for member in conversation["members"]:
            member["online"] = hub.online(member["id"])
        if conversation["peer"]:
            conversation["peer"]["online"] = hub.online(conversation["peer"]["id"])
        return conversation

    async def changed(cid: int, audience: list[int], kind: str = "conversation.changed", **extra):
        await hub.publish(audience, {"type": kind, "conversation_id": cid, **extra})

    @application.middleware("http")
    async def guards(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in {"POST", "PATCH", "DELETE", "PUT"}:
            origin = request.headers.get("origin", "").rstrip("/")
            if origin not in settings.origins:
                return JSONResponse({"error": {"code": "origin_rejected", "message": "This request came from an untrusted origin."}}, status_code=403)
            maximum = settings.max_avatar_bytes + 65536 if request.url.path == "/api/me/avatar" else 65536
            try:
                too_large = int(request.headers.get("content-length", "0")) > maximum
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse({"error": {"code": "request_too_large", "message": "That upload is too large."}}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif not request.url.path.startswith("/_next/"):
            response.headers["Cache-Control"] = "no-cache"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; connect-src 'self' ws: wss:; font-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @application.exception_handler(AppError)
    async def application_error(_request, error: AppError):
        return JSONResponse({"error": {"code": error.code, "message": error.message}}, status_code=error.status)

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request, error):
        details = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in error.errors()]
        return JSONResponse({"error": {"code": "validation_failed", "message": details[0]["message"], "details": details}}, status_code=422)

    @application.exception_handler(OperationalError)
    async def database_busy(_request, _error):
        logger.warning("Database operation could not complete")
        return JSONResponse({"error": {"code": "database_unavailable", "message": "The database is busy. Please try again."}}, status_code=503)

    @application.exception_handler(HTTPException)
    async def http_error(_request, error):
        return JSONResponse({"error": {"code": "http_error", "message": str(error.detail)}}, status_code=error.status_code)

    @application.get("/api/health")
    async def health():
        def check():
            with application.state.db.engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
        await run_in_threadpool(check)
        return {"status": "ok", "encryption": "mock", "authentication": "demo_otp"}

    @application.get("/api/config")
    async def demo_config():
        return {"demo_otp": settings.demo_otp, "demo_accounts": ["alex", "maya", "sam"] if settings.seed_demo else [],
                "max_group_size": settings.max_group_size}

    async def authenticate(data: AuthInput, request: Request, register: bool):
        limiter.check(f"auth:{request.client.host if request.client else 'local'}", 30)
        # Rotate an existing browser session rather than leaving an old socket signed in.
        previous = request.cookies.get(settings.cookie_name)
        payload, token = await run_in_threadpool(svc().authenticate, data, register)
        if previous:
            with suppress(AppError):
                old = await run_in_threadpool(svc().identity, previous)
                await run_in_threadpool(svc().logout, old)
                await hub.revoke(old.token_hash)
        response = JSONResponse(payload, status_code=201 if register else 200)
        response.set_cookie(settings.cookie_name, token, max_age=settings.session_days * 86400,
            secure=settings.cookie_secure, httponly=True, samesite="lax", path="/")
        return response

    @application.post("/api/auth/register", status_code=201)
    async def register(data: AuthInput, request: Request):
        return await authenticate(data, request, True)

    @application.post("/api/auth/login")
    async def login(data: AuthInput, request: Request):
        return await authenticate(data, request, False)

    @application.post("/api/auth/logout")
    async def logout(request: Request):
        who = await identity(request, True)
        await run_in_threadpool(svc().logout, who)
        await hub.revoke(who.token_hash)
        response = JSONResponse({"ok": True})
        response.delete_cookie(settings.cookie_name, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")
        return response

    @application.get("/api/me")
    async def me(request: Request):
        return await run_in_threadpool(svc().me, await identity(request))

    @application.patch("/api/me")
    async def profile(data: ProfileInput, request: Request):
        who = await identity(request, True)
        return await run_in_threadpool(svc().profile, who.user_id, data.display_name)

    @application.post("/api/me/avatar")
    async def avatar(request: Request, file: UploadFile = File(...)):
        who = await identity(request, True)
        limiter.check(f"avatar:{who.user_id}", 12, 3600)
        raw = await file.read(settings.max_avatar_bytes + 1)
        await file.close()
        if len(raw) > settings.max_avatar_bytes:
            raise AppError(413, "avatar_too_large", "Choose an image smaller than 2 MB.")
        def save():
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format not in {"JPEG", "PNG", "WEBP"} or image.width * image.height > 16_000_000:
                        raise AppError(400, "invalid_image", "Use a JPEG, PNG, or WebP image up to 16 megapixels.")
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image = ImageOps.fit(image, (256, 256))
                    filename = secrets.token_hex(16) + ".jpg"
                    image.save(settings.avatars_dir / filename, "JPEG", quality=88)
                    return filename
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                raise AppError(400, "invalid_image", "That file does not look like a valid image.")
        filename = await run_in_threadpool(save)
        return await run_in_threadpool(svc().profile, who.user_id, None, filename)

    @application.get("/api/avatars/{filename}")
    async def avatar_file(filename: str, request: Request):
        await identity(request)
        if not re.fullmatch(r"[a-f0-9]{32}\.jpg", filename):
            raise AppError(404, "not_found", "Image not found.")
        path = settings.avatars_dir / filename
        if not path.is_file():
            raise AppError(404, "not_found", "Image not found.")
        return FileResponse(path, media_type="image/jpeg")

    @application.get("/api/users")
    async def users(request: Request, q: str = Query(default="", max_length=80)):
        who = await identity(request)
        limiter.check(f"search:{who.user_id}", 120)
        return await run_in_threadpool(svc().search_users, who.user_id, q)

    @application.get("/api/contacts")
    async def contacts(request: Request):
        return await run_in_threadpool(svc().list_contacts, (await identity(request)).user_id)

    @application.post("/api/contacts", status_code=201)
    async def add_contact(data: ContactInput, request: Request):
        who = await identity(request, True)
        return await run_in_threadpool(svc().add_contact, who.user_id, data.username)

    @application.get("/api/conversations")
    async def conversations(request: Request, q: str = Query(default="", max_length=80)):
        rows = await run_in_threadpool(svc().conversations, (await identity(request)).user_id, q)
        return [decorate(c) for c in rows]

    @application.post("/api/conversations/direct", status_code=201)
    async def direct(data: DirectInput, request: Request):
        who = await identity(request, True)
        limiter.check(f"create:{who.user_id}", 30)
        payload, audience = await run_in_threadpool(svc().direct, who.user_id, data.user_id)
        await changed(payload["id"], audience)
        return decorate(payload)

    @application.post("/api/groups", status_code=201)
    async def create_group(data: GroupInput, request: Request):
        who = await identity(request, True)
        limiter.check(f"create:{who.user_id}", 30)
        payload, audience = await run_in_threadpool(svc().group, who.user_id, data)
        await changed(payload["id"], audience)
        return decorate(payload)

    @application.get("/api/conversations/{cid}")
    async def conversation(cid: int, request: Request):
        return decorate(await run_in_threadpool(svc().conversation, (await identity(request)).user_id, cid))

    @application.patch("/api/groups/{cid}")
    async def rename(cid: int, data: GroupNameInput, request: Request):
        who = await identity(request, True)
        audience = await run_in_threadpool(svc().rename_group, who.user_id, cid, data.name)
        await changed(cid, audience)
        return {"ok": True}

    @application.post("/api/groups/{cid}/members")
    async def add_member(cid: int, data: MemberInput, request: Request):
        who = await identity(request, True)
        audience = await run_in_threadpool(svc().change_member, who.user_id, cid, data.user_id, "add")
        await changed(cid, audience, "membership.changed", user_id=data.user_id)
        return {"ok": True}

    @application.delete("/api/groups/{cid}/members/{target}")
    async def remove_member(cid: int, target: int, request: Request):
        who = await identity(request, True)
        audience = await run_in_threadpool(svc().change_member, who.user_id, cid, target, "remove")
        await changed(cid, audience, "membership.changed", user_id=target, removed=True)
        return {"ok": True}

    @application.patch("/api/groups/{cid}/members/{target}")
    async def set_role(cid: int, target: int, data: RoleInput, request: Request):
        who = await identity(request, True)
        audience = await run_in_threadpool(svc().change_member, who.user_id, cid, target, "role", data.role)
        await changed(cid, audience, "membership.changed", user_id=target)
        return {"ok": True}

    @application.get("/api/conversations/{cid}/messages")
    async def messages(cid: int, request: Request, limit: int = Query(50, ge=1, le=100),
                       before_id: int | None = Query(None, ge=1), after_id: int | None = Query(None, ge=0),
                       through_id: int | None = Query(None, ge=0)):
        who = await identity(request)
        return await run_in_threadpool(svc().history, who.user_id, cid, limit, before_id, after_id, through_id)

    @application.post("/api/conversations/{cid}/messages", status_code=201)
    async def send_message(cid: int, data: MessageInput, request: Request):
        who = await identity(request, True)
        limiter.check(f"send:{who.user_id}", 120)
        payload, audience, created = await run_in_threadpool(svc().send, who.user_id, cid, data)
        if created:
            await changed(cid, audience, "message.new", message_id=payload["id"], sender_id=who.user_id)
        return JSONResponse(payload, status_code=201 if created else 200)

    @application.get("/api/deliveries")
    async def deliveries(request: Request):
        return await run_in_threadpool(svc().pending, (await identity(request)).user_id)

    @application.post("/api/receipts")
    async def receipts(data: ReceiptInput, request: Request):
        who = await identity(request, True)
        events = await run_in_threadpool(svc().receipts, who.user_id, data.message_ids, data.state)
        for cid, audience in events.items():
            await changed(cid, audience, "receipt.changed")
        return {"ok": True}

    @application.post("/api/messages/{mid}/reactions")
    async def reaction(mid: int, data: ReactionInput, request: Request):
        who = await identity(request, True)
        limiter.check(f"reaction:{who.user_id}", 120)
        cid, audience = await run_in_threadpool(svc().react, who.user_id, mid, data.emoji)
        await changed(cid, audience, "reaction.changed")
        return {"ok": True}

    @application.websocket("/ws")
    async def socket(websocket: WebSocket):
        if websocket.headers.get("origin", "").rstrip("/") not in settings.origins:
            await websocket.close(code=4403)
            return
        try:
            who = await run_in_threadpool(svc().identity, websocket.cookies.get(settings.cookie_name))
        except AppError:
            await websocket.close(code=4401)
            return
        if sum(p.identity.user_id == who.user_id for p in hub.peers) >= 8:
            await websocket.close(code=4429)
            return
        await websocket.accept()
        peer = hub.add(websocket, who)
        writer = asyncio.create_task(hub.writer(peer))
        peer.queue.put_nowait({"type": "ready", "user_id": who.user_id})
        await hub.broadcast_presence(who.user_id)
        try:
            while True:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=45)
                if len(raw) > 2048:
                    await websocket.close(code=1009)
                    break
                try:
                    packet = json.loads(raw)
                    if not isinstance(packet, dict):
                        raise ValueError("not an object")
                except (json.JSONDecodeError, ValueError):
                    await websocket.close(code=1007)
                    break
                # Recheck the persisted session on every heartbeat or typing event.
                await run_in_threadpool(svc().identity_hash, who.token_hash)
                if packet.get("type") == "ping":
                    try:
                        limiter.check(f"ping:{who.token_hash}", 15, 10)
                    except AppError:
                        continue
                    peer.queue.put_nowait({"type": "pong"})
                elif packet.get("type") == "typing":
                    try:
                        limiter.check(f"typing:{who.user_id}", 10, 5)
                    except AppError:
                        # Typing is disposable. A burst must never revoke a login.
                        continue
                    cid = packet.get("conversation_id")
                    if type(cid) is not int or type(packet.get("active")) is not bool:
                        continue
                    try:
                        audience = await run_in_threadpool(svc().typing_audience, who.user_id, cid)
                    except AppError:
                        continue
                    await hub.publish([u for u in audience if u != who.user_id], {
                        "type": "typing", "conversation_id": cid, "user_id": who.user_id,
                        "active": packet["active"], "ttl_ms": 5000,
                    })
        except (WebSocketDisconnect, TimeoutError, RuntimeError):
            pass
        except AppError as error:
            with suppress(RuntimeError):
                await websocket.close(code=4401 if error.status == 401 else 1008)
        finally:
            hub.remove(peer)
            writer.cancel()
            with suppress(asyncio.CancelledError, RuntimeError, TimeoutError):
                await writer
            if not hub.online(who.user_id):
                await run_in_threadpool(svc().last_seen, who.user_id)
            await hub.broadcast_presence(who.user_id)

    # The API and socket routes must be registered before the static mount.
    if settings.frontend_dir.is_dir():
        application.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    else:
        @application.get("/")
        async def not_built():
            return {"message": "Backend is ready. Build frontend/ or run its development server.", "docs": "/docs"}
    return application


app = create_app()
