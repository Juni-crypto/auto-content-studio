"""Studio settings: paths, the three frozen brands, cadence and posting slots.

Secrets never live here: /opt/studio/.env (Telegram) and /opt/studio/secrets/instagram.json (IG tokens), both chmod 600.
The frozen production format is in rules/PLAN.md ("Final production format") and rules/EDITING-RULES.md.
"""
import os, pathlib

ROOT = pathlib.Path(os.environ.get("STUDIO_ROOT", "/opt/studio"))
APP, TOOLS, KIN = ROOT / "app", ROOT / "tools", ROOT / "tools" / "kinetic"
DATA, MEDIA, WORK, LOGS = ROOT / "data", ROOT / "media", ROOT / "work", ROOT / "logs"
RULES, ASSETS, EXAMPLES, PROMPTS = ROOT / "rules", ROOT / "assets", ROOT / "examples", APP / "prompts"
LOGOS = ASSETS / "logos"                      # approved official logos: <slug>.png + <slug>.json (source, licence)
DB = DATA / "studio.db"
PY = ROOT / "venvs" / "qwen" / "bin" / "python"
SECRETS = ROOT / "secrets" / "instagram.json"
PUBLIC = os.environ.get("STUDIO_PUBLIC", "https://studio.example.com")   # Caddy serves MEDIA at PUBLIC/m/
TZ = "Asia/Kolkata"
HYPERFRAMES = "hyperframes@0.8.79"

# The frozen format (27 Sep 2026): creator-style Aiden voice, constant greeting, hook at frame 0, real 3D emojis,
# tap-to-Follow outro "Follow <brand> for more, and catch you later, <friend>!", no blank centre, English only.
BRANDS = {
    "sportsdesk": dict(
        name="SPORTS DESK", say="Sports Desk", handle="sportsdesk.example", beat="sports", theme="sportsdesk",
        friend="champ", greeting="Hey champ", greet_emoji="salute", kicker="First. Every time.",
        music=["sportsdesk-take1.wav", "sportsdesk-take2.wav"], board="brand/sportsdesk-board.png",
        voice="A hyped, sports-mad young creator talking to his mates on Instagram. Big energy on the good news, a disappointed "
              "little groan on 'hmmm, bit sad', disbelief on 'can you believe it', a smile on the sign-off. Natural rhythm and "
              "breaths. Never monotone, never a TV announcer.",
        focus="India-first sports news: cricket, football, hockey, kabaddi, badminton, athletics, chess, Olympic sports; results, "
              "big moments and the stories behind them. English only.",
        image_style='Brand "SPORTS DESK", an Indian-first sports news account. Visual world: a modern Indian single-screen cinema poster '
                    'and hand-painted street lettering: ink black #111111 background with halftone texture, hot magenta #E6007E, '
                    'marigold #FFB300, cream #FFF6E5, a touch of teal #00A6A6; heavy wide display type and heavy condensed numerals '
                    'for scores; halftone crowd silhouettes with raised arms, flags and stadium floodlights rising from the bottom edge. '
                    'Brand chrome: the SPORTS DESK badge (a black circle with a big cream italic "6" and two speed lines, on marigold) '
                    'with the wordmark "SPORTS DESK" small in the top-right corner.',
        no_faces=True),
    "techdesk": dict(
        name="TECHDESK", say="Techdesk", handle="techdesk.example", beat="tech", theme="techdesk",
        friend="buddy", greeting="Hey buddy", greet_emoji="wave", kicker="PATCH {mmdd}",
        music=["techdesk-take1.wav", "techdesk-take2.wav"], board="brand/concepts/techdesk-board.png",
        voice="A playful, cheeky young tech creator talking straight to camera on Instagram. Real reactions: he laughs out loud on "
              "'Haha!', teasing when a big company slips, a thoughtful 'hmmm', faster when excited, slower when making a point. "
              "Natural rhythm and breaths. Never monotone, never a news announcer.",
        focus="The day's biggest tech story explained fast: AI, phones, chips, apps, big tech, Indian tech and startups, "
              "launches, lawsuits, security. English only.",
        image_style='Brand "TECHDESK" (tech news, shipped fast). Visual system: near-black #121212 background with subtle print grain; '
                    'hazard-orange #FF5B1F tape strips with black text; ultra-heavy condensed ITALIC grotesk headlines in off-white '
                    '#F2EFE8, huge and tight; small mono labels; yellow #FFD23F used only for small arrows; urgent, fast, editorial. '
                    'Brand chrome: a hazard-orange tape strip across the top-left corner with the black text "PATCH {mmdd}".',
        no_faces=False),
    "bizdesk": dict(
        name="BIZDESK", say="Bizdesk", handle="bizdesk.example", beat="business", theme="bizdesk",
        friend="boss", greeting="Hey boss", greet_emoji="wave", kicker="BRAND KAHANI",
        music=["bizdesk-take1.wav", "bizdesk-take2.wav"], board="brand/bizdesk-board.png",
        voice="A warm, witty young storyteller telling a friend a brilliant business story on Instagram. Curious and amused, builds "
              "up to each twist, proud when he says 'our hero', laughs warmly on 'Haha', impressed on 'crazy, right' and 'it worked'. "
              "Natural rhythm and breaths. Never monotone, never an announcer.",
        focus="The stories behind India's brands (and global brands in India): how they started, the big bet, the twist, how "
              "they won or fell. Storytelling, not news. English with the odd Hindi word the whole country knows.",
        image_style='Brand "BIZDESK" (the stories behind India\'s brands). Visual world: Indian hand-painted shop signboards and truck '
                    'art made modern and premium: sunflower yellow #FFC400, parrot green #1FA34A, signal red #E0262B, royal blue '
                    '#1F4FB8, black #111111; bold hand-lettered display type with painted drop shadows, decorative painted borders, '
                    'small flower motifs, slight brush texture.',
        no_faces=True),
}

# Default cadence per brand per day, and IST posting slots (brands staggered so they never post in the same minute).
CADENCE = {"sportsdesk": {"reel": 1, "carousel": 1, "story": 2},
           "techdesk": {"reel": 1, "carousel": 1, "story": 2},
           "bizdesk": {"reel": 1, "carousel": 1, "story": 1}}
SLOTS = {"story": ["10:00", "21:30"], "carousel": ["13:00"], "reel": ["19:00"], "poster": ["16:00"]}
OFFSET_MIN = {"sportsdesk": 0, "techdesk": 20, "bizdesk": 40}
LEAD_HOURS = 14          # start making an item this many hours before its slot
VETO_MIN = 45            # previews reach Telegram at least this long before posting (approval mode "veto")
MAX_FIX_ROUNDS = 3       # committee "fix" verdicts -> rewrite and re-review at most this many times
WORKERS = 3              # items made side by side (voice and render still take turns on the CPU)
