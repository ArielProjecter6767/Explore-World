# Explore World

Responsive AI assistant + Cesium globe/flight prototype. FastAPI backend, MongoDB Atlas accounts, Groq chat, OpenWeather current conditions, Cesium globe and responsive flight controls.

## Deploy to Render
1. Upload all files from this project into the empty `ArielProjecter6767/Explore-World` GitHub repository.
2. In Render select **New + → Blueprint**, connect the repository and apply `render.yaml`. Alternatively create a Python web service with build command `pip install -r requirements.txt` and start command `uvicorn main:app --host 0.0.0.0 --port $PORT`.
3. Create a MongoDB Atlas database and add its connection string as `MONGO_URL`. URL-encode special characters in the database user's password. Configure Atlas Network Access to permit the Render service.
4. Add `GROQ_API_KEY`, `OPENWEATHER_API_KEY`, and `CESIUM_ION_TOKEN` in Render Environment. Never commit secrets into GitHub. Use a restricted Cesium browser token for the frontend.
5. Deploy and open `/api/health`. It should show `mongodb_configured: true`.

## Included
- Responsive UI for mobile and desktop
- MongoDB-backed nickname/password registration and login; bcrypt password hashes and HttpOnly signed session cookie
- Groq chat endpoint (default model `openai/gpt-oss-120b`)
- OpenWeather current weather endpoint
- Cesium globe and attempted terrain initialization
- Keyboard and touch controls for a prototype flight simulation
- Local-time offset control and a weather card UI

## Not complete yet
- Image generation provider is not connected.
- GitHub repository reading/writing and plugin installation require a dedicated OAuth/GitHub App integration, least-privilege permissions, and explicit per-change approval; they are not wired into this starter.
- The voice button currently checks microphone permission only. WebSocket signaling exists, but actual peer-to-peer WebRTC audio is not implemented.
- Flight movement is a basic prototype; external GLB model URLs are listed in the UI but models are not yet rendered as aircraft in the Cesium scene.
- Cesium terrain depends on a valid token and browser/provider availability.
