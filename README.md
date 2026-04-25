# discord-ish

A Discord-inspired chat application built with Django + Channels.

Features:

- Custom user model (email required & unique, avatar, bio, online/offline presence)
- Three-tier role system (Administrator / Moderator / User), seeded automatically
- Public and private text channels with membership management
- 1-on-1 direct messages
- Real-time messaging via WebSockets (Django Channels, in-memory layer - no Redis)
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
  - `/ws/dm/<conversation_id>/` &rarr; `direct_messages.consumers.DMConsumer`
  - `/ws/presence/` &rarr; `accounts.consumers.PresenceConsumer`
- Channel layer: in-memory (`channels.layers.InMemoryChannelLayer`) - no Redis
  required, single-process only.

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

12 smoke tests cover: registration / role assignment / email uniqueness,
public vs private channel access, join restrictions, message deletion
permissions (author, moderator, third party), and block/unblock flow.

## Production notes

For production:

1. Set a real `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, populate `DJANGO_ALLOWED_HOSTS`.
2. Swap to PostgreSQL by adjusting `DATABASES` in `settings.py`.
3. Replace the in-memory channel layer with the Redis layer
   (`channels_redis`) so multiple worker processes can share state.
4. Serve static files via WhiteNoise, NGINX, or a CDN.
5. Run behind Daphne / Uvicorn with a process manager (systemd, supervisor).
