"""Out-of-the-box blocking: a freshly initialised DB ships social + video
blocking enabled, so the built image blocks from first boot without any wizard
step. The DEFAULT set is the union of social_only.txt and the video section of
hard_mode.txt (news and gaming are deliberately dropped)."""
from pathlib import Path

from stillhem.blocklist import export_to_file, list_platforms
from stillhem.db import init_db

PRESET_DIR = Path(__file__).parent.parent / "blocklists"

# The domains the image is expected to block on first boot.
EXPECTED_SOCIAL = {
    "facebook.com", "instagram.com", "cdninstagram.com", "fbcdn.net", "threads.net",
    "twitter.com", "t.co", "twimg.com", "x.com",
    "tiktok.com", "tiktokcdn.com", "tiktokv.com",
    "reddit.com", "redd.it", "redditstatic.com", "redditmedia.com", "reddituploads.com",
    "snapchat.com", "sc-cdn.net",
    "pinterest.com", "pinimg.com",
    "linkedin.com", "licdn.com",
}
EXPECTED_VIDEO = {
    "youtube.com", "youtu.be", "googlevideo.com", "ytimg.com",
    "netflix.com", "nflxvideo.net",
    "twitch.tv", "twitchsvc.net",
}
EXPECTED_DEFAULT = EXPECTED_SOCIAL | EXPECTED_VIDEO
# News + gaming domains that must NOT ship blocked out of the box.
EXCLUDED = {
    "nytimes.com", "theguardian.com", "bbc.com", "bbc.co.uk", "cnn.com",
    "dn.se", "svt.se", "aftonbladet.se", "expressen.se",
    "discord.com", "discordapp.com", "discordapp.net",
}


def test_fresh_init_db_exports_default_blocklist(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    init_db(db)
    out = tmp_path / "active_blocklist.txt"
    export_to_file(db, out)
    exported = set(out.read_text().splitlines())
    missing = EXPECTED_DEFAULT - exported
    assert not missing, f"default blocking missing domains: {sorted(missing)}"


def test_fresh_init_db_does_not_block_news_or_gaming(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    init_db(db)
    out = tmp_path / "active_blocklist.txt"
    export_to_file(db, out)
    exported = set(out.read_text().splitlines())
    leaked = EXCLUDED & exported
    assert not leaked, f"news/gaming domains must not ship blocked: {sorted(leaked)}"


def test_fresh_init_db_seeds_pinterest_and_netflix(tmp_path: Path) -> None:
    # These two platforms were absent from the original seed; the default set adds them.
    db = tmp_path / "fresh.db"
    init_db(db)
    names = {p["name"] for p in list_platforms(db)}
    assert "pinterest" in names
    assert "netflix" in names


def test_default_platforms_enabled_out_of_the_box(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    init_db(db)
    plats = list_platforms(db)
    assert plats, "init_db must seed platforms"
    # Every seeded platform (all social/video) ships enabled so blocking is on.
    for p in plats:
        assert p["category"] in ("social", "video")
        assert p["enabled"] == 1, f"{p['name']} should be enabled by default"


def test_default_txt_matches_seeded_default(tmp_path: Path) -> None:
    """blocklists/default.txt documents the shipped set; it must match what a
    fresh init_db actually exports so the artifact never drifts from behaviour."""
    default_path = PRESET_DIR / "default.txt"
    lines = default_path.read_text().splitlines()
    documented = {l.strip() for l in lines if l.strip() and not l.startswith("#")}

    db = tmp_path / "fresh.db"
    init_db(db)
    out = tmp_path / "active_blocklist.txt"
    export_to_file(db, out)
    exported = set(out.read_text().splitlines())
    assert documented == exported
