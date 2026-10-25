import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request, Response, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from passlib.context import CryptContext
from motor.motor_asyncio import AsyncIOMotorClient

APP_NAME = "Explore World"
MONGO_URL = os.getenv("MONGO_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
JWT_ALGORITHM = "HS256"
TOKEN_HOURS = 168
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title=APP_NAME)
app.mount("/static", StaticFiles(directory="static"), name="static")
mongo_client = AsyncIOMotorClient(MONGO_URL) if MONGO_URL else None
db = mongo_client["explore_world"] if mongo_client else None


class Credentials(BaseModel):
    nickname: str = Field(min_length=3, max_length=24, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)


class WeatherRequest(BaseModel):
    lat: float
    lon: float


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


def require_db():
    if db is None:
        raise HTTPException(503, "MongoDB не настроена: добавьте MONGO_URL в Render Environment.")


def token_for(nickname: str):
    return jwt.encode(
        {"sub": nickname, "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


async def current_user(request: Request):
    token = request.cookies.get("ew_session")
    if not token:
        raise HTTPException(401, "Войдите в аккаунт.")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Сессия истекла. Войдите снова.")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "service": APP_NAME, "mongodb_configured": db is not None}


@app.get("/api/config")
async def public_config():
    # Public browser token must be a restricted Cesium ion token; never expose database/API secrets here.
    return {"cesium_ion_token": os.getenv("CESIUM_ION_TOKEN", "")}


@app.post("/api/auth/register")
async def register(data: Credentials, response: Response):
    require_db()
    nickname = data.nickname.strip()
    if await db.users.find_one({"nickname_lower": nickname.lower()}):
        raise HTTPException(409, "Этот никнейм уже занят.")
    user = {
        "nickname": nickname,
        "nickname_lower": nickname.lower(),
        "password_hash": pwd_context.hash(data.password),
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(user)
    response.set_cookie(
        "ew_session", token_for(nickname), httponly=True, secure=True,
        samesite="lax", max_age=TOKEN_HOURS * 3600,
    )
    return {"nickname": nickname}


@app.post("/api/auth/login")
async def login(data: Credentials, response: Response):
    require_db()
    user = await db.users.find_one({"nickname_lower": data.nickname.strip().lower()})
    if not user or not pwd_context.verify(data.password, user["password_hash"]):
        raise HTTPException(401, "Неверный никнейм или пароль.")
    response.set_cookie(
        "ew_session", token_for(user["nickname"]), httponly=True, secure=True,
        samesite="lax", max_age=TOKEN_HOURS * 3600,
    )
    return {"nickname": user["nickname"]}


@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("ew_session", httponly=True, secure=True, samesite="lax")
    return {"ok": True}


@app.get("/api/auth/me")
async def me(user=Depends(current_user)):
    return {"nickname": user}


@app.post("/api/ai/chat")
async def ai_chat(data: ChatRequest, user=Depends(current_user)):
    key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    if not key:
        raise HTTPException(503, "Добавьте GROQ_API_KEY в Render Environment.")
    system = (
        "Ты Explore World — дружелюбный ИИ-помощник. Отвечай на языке пользователя. "
        "Не утверждай, что выполнил действия с GitHub, установил плагины или изменил файлы, если это не подтверждено. "
        "Перед изменениями репозитория подготовь план и запроси отдельное подтверждение пользователя."
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": data.message},
                ], "temperature": 0.7},
            )
        if res.status_code >= 400:
            raise HTTPException(502, f"Groq API ({res.status_code}): {res.text[:600]}")
        return {"reply": res.json()["choices"][0]["message"]["content"], "model": model}
    except httpx.TimeoutException:
        raise HTTPException(504, "ИИ не ответил вовремя. Попробуйте ещё раз.")


@app.post("/api/weather")
async def weather(data: WeatherRequest, user=Depends(current_user)):
    key = os.getenv("OPENWEATHER_API_KEY")
    if not key:
        raise HTTPException(503, "Добавьте OPENWEATHER_API_KEY в Render Environment.")
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": data.lat, "lon": data.lon, "appid": key, "units": "metric"},
        )
    if res.status_code >= 400:
        raise HTTPException(502, f"OpenWeather API ({res.status_code}): {res.text[:300]}")
    j = res.json()
    return {
        "city": j.get("name") or "Текущая точка",
        "temp": round(j["main"]["temp"]),
        "feels_like": round(j["main"]["feels_like"]),
        "description": j["weather"][0]["description"],
        "icon": j["weather"][0]["icon"],
        "humidity": j["main"]["humidity"],
        "wind": j["wind"]["speed"],
    }


@app.post("/api/ai/image")
async def image_generation(data: ImageRequest, user=Depends(current_user)):
    raise HTTPException(
        501,
        "Провайдер генерации изображений пока не подключён. Добавьте отдельный image-generation API и ключ в Render.",
    )


voice_rooms = {}


@app.websocket("/ws/voice/{room}")
async def voice_signaling(websocket: WebSocket, room: str):
    # Signaling relay only; audio transport requires a WebRTC client implementation.
    await websocket.accept()
    voice_rooms.setdefault(room, set()).add(websocket)
    try:
        while True:
            message = await websocket.receive_text()
            for peer in list(voice_rooms.get(room, set())):
                if peer is not websocket:
                    try:
                        await peer.send_text(message)
                    except Exception:
                        voice_rooms[room].discard(peer)
    except WebSocketDisconnect:
        voice_rooms.get(room, set()).discard(websocket)


@app.on_event("shutdown")
async def shutdown():
    if mongo_client:
        mongo_client.close()
