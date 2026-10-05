import os


class Config:
    API_ID = int(os.environ.get("API_ID", "0") or 0)
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    DATABASE_URI = os.environ.get("DATABASE_URI", "")
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "randomforwardbot")

    # Multiple owners allowed: OWNER_ID="123 456"
    OWNER_IDS = [
        int(x)
        for x in os.environ.get("OWNER_ID", "").replace(",", " ").split()
        if x.lstrip("-").isdigit()
    ]

    # Render sets PORT and RENDER_EXTERNAL_URL automatically for web services
    PORT = int(os.environ.get("PORT", "8080"))
    PING_URL = os.environ.get("PING_URL") or os.environ.get("RENDER_EXTERNAL_URL", "")

    @classmethod
    def check(cls):
        missing = [
            name
            for name, val in [
                ("API_ID", cls.API_ID),
                ("API_HASH", cls.API_HASH),
                ("BOT_TOKEN", cls.BOT_TOKEN),
                ("DATABASE_URI", cls.DATABASE_URI),
                ("OWNER_ID", cls.OWNER_IDS),
            ]
            if not val
        ]
        if missing:
            raise SystemExit("Missing environment variables: " + ", ".join(missing))
