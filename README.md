# discord-ish

A Discord-inspired chat application built with Django + Channels.

Features:

- Custom user model (email required & unique, avatar, bio, online/offline presence)
- Three-tier role system (Administrator / Moderator / User), seeded automatically
- Public, private and voice channels with membership management
- 1-on-1 direct messages
- Real-time messaging via WebSockets (Django Channels, in-memory layer - no Redis)
- Voice channels (WebRTC mesh) with mute / connected list
- Image uploads and in-browser voice messages (recorded via MediaRecorder)
- Emoji reactions on channel messages
- Moderation: block / unblock users, soft-delete messages, optional reports queue
- User & channel search
- Discord-inspired Bootstrap 5 dark theme
- Custom 404 / 500 error pages

## Quick start

```bash
# 1. Create venv & install deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Copy environment file
cp .env.example .env
# (edit .env if you want; defaults are fine for local dev)

# 3. Migrate and seed demo data
python manage.py migrate
python manage.py seed_demo
# (Optional) create your own superuser too:
python manage.py createsuperuser

# 4. Run the ASGI server (Daphne) so WebSockets work
daphne -b 127.0.0.1 -p 8000 discord_django.asgi:application
# Or simply use:
python manage.py runserver
```

Then open <http://127.0.0.1:8000/>.

The seed command creates these accounts (password `demopass123` for all):

| Username   | Role          |
|------------|---------------|
| `admin`    | Administrator |
| `moderator`| Moderator     |
| `alice`    | User          |
| `bob`      | User          |
| `carol`    | User          |

## Project layout

```
discord_django/
├── discord_django/        # project settings, ASGI, routing, URL config
├── accounts/              # Custom user, auth views, presence consumer, role mixins
├── chat/                  # Channels, messages, reactions, ChannelChatConsumer
├── direct_messages/       # 1-on-1 conversations + DMConsumer
├── moderation/            # Blocking, soft-delete, reports + dashboard
├── core/                  # Home page, search, error handlers, sidebar context
├── templates/             # Bootstrap 5 templates (dark theme, Discord-like layout)
├── static/                # CSS + JS (chat.js for WS, presence.js, app.css)
└── media/                 # User uploads (avatars, images, audio)
```

## Roles & permissions

- A data migration (`accounts/migrations/0002_seed_role_groups.py`) creates the
  three groups on first migrate.
- A `post_save` signal (`accounts/signals.py`) puts every new registration into
  the `User` group, and superusers into `Administrator`.
- View access is enforced via `accounts.permissions.AdminRequiredMixin`,
  `ModeratorRequiredMixin`, `moderator_required`, and `admin_required`.
- Per-channel access is checked through `Channel.can_view()`,
  `Channel.can_post()`, `Channel.can_manage()`.

## Real-time architecture

- ASGI entry point: [`discord_django/asgi.py`](discord_django/asgi.py)
- WebSocket routes: [`discord_django/routing.py`](discord_django/routing.py)
  - `/ws/channel/<id>/` &rarr; `chat.consumers.ChannelChatConsumer`
  - `/ws/voice/<id>/` &rarr; `chat.voice_consumers.VoiceRoomConsumer`
  - `/ws/dm/<conversation_id>/` &rarr; `direct_messages.consumers.DMConsumer`
  - `/ws/presence/` &rarr; `accounts.consumers.PresenceConsumer`
- Channel layer: in-memory (`channels.layers.InMemoryChannelLayer`) - no Redis
  required, single-process only.

## Voice channels

Voice channels use **WebRTC mesh**: every participant opens an
`RTCPeerConnection` to every other participant. The Django consumer
([`chat/voice_consumers.py`](chat/voice_consumers.py)) is a pure
*signaling* relay - it forwards SDP offers/answers and ICE candidates
between peers but never touches the audio itself.

Client logic lives in [`static/js/voice.js`](static/js/voice.js):
`getUserMedia({audio: true})` -> open WS -> for every existing peer create
a peer connection and send an offer; for newcomers wait for an inbound
offer. Mute toggles the local audio track and broadcasts a `mute` event
so other clients can show the icon.

Limits / caveats:

- Mesh scales to roughly **4 participants per room**. Beyond that, audio
  uplinks become expensive; an SFU (LiveKit, mediasoup, Janus) is the
  next step.
- `getUserMedia` requires a **secure context** in the browser, so in
  production the site must be served over **HTTPS** (localhost is treated
  as secure for development).
- A public Google STUN server is used by default. For peers behind
  symmetric NATs, deploy a TURN server (e.g. coturn) and inject its URL
  into `window.VOICE_CONFIG.iceServers` (currently hardcoded in
  `templates/chat/channel_detail.html`; promote to env if needed).
- The peer registry is held in-process; running multiple Daphne workers
  requires switching `CHANNEL_LAYERS` to `channels_redis` and replacing
  the in-memory dict in `chat/voice_consumers.py` with a Redis-backed one.

## File uploads

Images and voice messages are uploaded over plain HTTP (multipart) to
`chat:upload_attachment` / `dm:upload_attachment`. After persisting the message
the view re-broadcasts a `message.new` event into the WebSocket group so all
connected clients see the new attachment instantly.

Limits (configurable via env):

- `MAX_UPLOAD_SIZE_BYTES` - default 10 MiB
- Allowed image extensions: `.png .jpg .jpeg .gif .webp`
- Allowed audio extensions: `.webm .ogg .mp3 .wav .m4a`

## Tests

```bash
python manage.py test
```

24 tests cover: registration / role assignment / email uniqueness,
public vs private channel access, join restrictions, message deletion
permissions (author, moderator, third party), block/unblock flow, voice
channel signaling (peer list, signal forwarding, mute, disconnect), and
the notifications consumer (channel fan-out, DM push, author self-skip,
non-member receives nothing).

## Deploy on Render

The repo is wired up for Render's free tier. Web Service runs Daphne (so
HTTP and WebSockets - chat, DMs, presence, voice signaling - share the same
process), static files are served by WhiteNoise, and a free Postgres instance
holds the data.

### One-shot via Blueprint (recommended)

1. Push the repo to GitHub.
2. In Render: **New + > Blueprint**, point at the repo.
3. Render reads [`render.yaml`](render.yaml) and provisions:
   - `discord-django` web service (free plan, Frankfurt)
   - `discord-django-db` Postgres (free plan, Frankfurt)
   - `DJANGO_SECRET_KEY` auto-generated
   - `DATABASE_URL` wired from the Postgres service
4. After the first deploy, open the service settings and set the two env
   vars that depend on the final hostname (Render printed it as
   `https://<service>.onrender.com`):
   - `DJANGO_ALLOWED_HOSTS=<service>.onrender.com`
   - `DJANGO_CSRF_TRUSTED_ORIGINS=https://<service>.onrender.com`
5. Trigger a redeploy ("Manual Deploy > Clear build cache & deploy").
6. Open the URL. Login as `admin` / `demopass123` (created by the
   `seed_demo` step in the build command).

### Manual setup (alternative)

If you prefer not to use the blueprint:

1. Create a **Postgres** instance (free tier).
2. Create a **Web Service** from the repo with:
   - **Build Command**:
     ```
     pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate --noinput && python manage.py seed_demo
     ```
   - **Start Command**:
     ```
     daphne -b 0.0.0.0 -p $PORT discord_django.asgi:application
     ```
3. Set environment variables: `DJANGO_SECRET_KEY` (random), `DJANGO_DEBUG=False`,
   `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
   `DATABASE_URL` (from the Postgres service "Internal Connection String"),
   `PYTHON_VERSION=3.12.6`.
4. Deploy.

### What works on the free tier

- HTTP + WebSockets share the Daphne process - chat, DMs, presence, and
  voice channel signaling all work.
- WebRTC voice (`getUserMedia`) needs HTTPS, which Render gives you for
  free on `*.onrender.com`. STUN traversal uses Google's public servers
  out of the box.
- Postgres free is enough for the demo (256 MB; resets every 30 days, so
  re-run `seed_demo` if you want fresh demo accounts).

### Caveats / known limitations

- **Media uploads (avatars, image messages, voice notes) are ephemeral**:
  Render's free Web Service doesn't include a persistent disk, so any
  files saved to `MEDIA_ROOT` disappear on redeploy. To keep them around,
  attach a Render Disk (paid) or move `MEDIA_ROOT` to S3/Cloudinary via
  `django-storages`.
- The free tier sleeps after ~15 min of inactivity; the first request
  after that takes ~30 s to wake up, and any open WebSocket is dropped
  during the sleep.
- Channels still uses the in-memory layer. That's fine here because
  `WEB_CONCURRENCY=1` (one Daphne worker), so all sockets share state.
  If you ever bump it up, switch to `channels_redis`.
- Voice channels rely on Google STUN. If a participant is behind a
  symmetric NAT, audio won't establish - deploy a TURN server (e.g.
  coturn or a managed Twilio TURN credential) and inject its URL into
  `window.VOICE_CONFIG.iceServers` in
  [templates/chat/channel_detail.html](templates/chat/channel_detail.html).

## Other production targets

The same setup runs on any host that supports long-running ASGI processes
(Fly.io, Railway, a VPS with `systemd`/Docker). The only host that *won't*
work as-is is anything WSGI-only (e.g. PythonAnywhere free tier) because
the WebSocket layer can't be served over WSGI.
