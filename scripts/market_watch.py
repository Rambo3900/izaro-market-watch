#!/usr/bin/env python3
"""Hourly PoE 1 transfigured-gem market monitor. Stdlib only.

Prices from poe.ninja. Gem name + socket color from RePoE game data.
Only uncorrupted level-1 / 0-quality gems are compared.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NINJA = "https://poe.ninja/poe1/api"
REPOE = "https://repoe-fork.github.io/gems_minimal.json"
UA = "IzaroMarketWatch/1.0 (https://github.com/Rambo3900/izaro-market-watch)"
COLORS = {"r": "rot", "g": "gruen", "b": "blau"}
MIN_LISTINGS = 4
# Official 3.30 patch-note gem; RePoE may lag behind the league launch.
CONFIRMED_PATCH_GEMS = {"Fireball of Radiation": "blau"}
HISTORY_LIMIT = 14 * 24
WATCHLIST = (
    "Poisonous Concoction of Bouncing",
    "Kinetic Blast of Clustering",
    "Elemental Hit of the Spectrum",
    "Dominating Blow of Inspiring",
    "Cyclone of Tumult",
    "Bladefall of Impaling",
    "Animate Weapon of Ranged Arms",
    "Lightning Tendrils of Eccentricity",
    "Scorching Ray of Immolation",
    "Fireball of Radiation",
)


def iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds").replace("+00:00", "Z")


def date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(path)


def fetch(url: str) -> Any:
    request = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"}
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            if attempt == 1:
                raise RuntimeError(f"API nicht erreichbar ({url.split('?')[0]}): {exc}") from exc
            time.sleep(3)
    raise RuntimeError("Unreachable")


def build_catalog(raw: Any) -> dict[str, str]:
    """A transfigured gem differs from its base gem in the RePoE metadata."""
    if not isinstance(raw, (list, dict)):
        raise ValueError("Unerwartetes RePoE-Format")
    entries = raw.values() if isinstance(raw, dict) else raw
    result: dict[str, str] = {}
    for gem in entries:
        if not isinstance(gem, dict) or gem.get("is_support") is True:
            continue
        name = gem.get("display_name")
        base = gem.get("base_item")
        color = gem.get("color")
        if (isinstance(name, str) and " of " in name and not name.startswith("Vaal ")
                and isinstance(base, dict) and name != base.get("display_name")
                and base.get("release_state", "released") == "released"
                and color in COLORS):
            result[name] = COLORS[color]
    result.update(CONFIRMED_PATCH_GEMS)
    if len(result) < 100:
        raise ValueError(f"Nur {len(result)} Transfigured Gems in RePoE gefunden")
    return result


def get_catalog(now: datetime) -> dict[str, str]:
    cached = read(DATA / "catalog.json", {})
    if isinstance(cached, dict) and isinstance(cached.get("gems"), dict):
        try:
            if now - date(cached["updated_at"]) < timedelta(hours=24):
                catalog = {**cached["gems"], **CONFIRMED_PATCH_GEMS}
                if catalog != cached["gems"]:
                    write(DATA / "catalog.json", {**cached, "gems": catalog})
                return catalog
        except (KeyError, ValueError, TypeError):
            pass
    try:
        catalog = build_catalog(fetch(REPOE))
        write(DATA / "catalog.json", {
            "source": REPOE, "updated_at": iso(now), "gems": catalog
        })
        print(f"RePoE-Katalog: {len(catalog)} transfigured Gems")
        return catalog
    except Exception as exc:
        if isinstance(cached, dict) and len(cached.get("gems", {})) >= 100:
            print(f"WARNUNG: RePoE nicht erreichbar, verwende Cache: {exc}")
            return cached["gems"]
        raise RuntimeError(f"Kein gültiger RePoE-Katalog verfügbar: {exc}") from exc


def choose_league(leagues: Any) -> str | None:
    """poe.ninja: first league is current softcore challenge league."""
    if not isinstance(leagues, list) or not leagues or not isinstance(leagues[0], dict):
        return None
    name = leagues[0].get("id")
    return name if isinstance(name, str) and name not in ("Standard", "Hardcore") else None


def eligible(line: dict) -> bool:
    if line.get("corrupted") is True:
        return False
    if line.get("gemLevel") != 1 or line.get("gemQuality") not in (0, None):
        return False
    value = line.get("chaosValue")
    return (isinstance(value, (float, int)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 < value < 1_000_000)


def extract(lines: Any, catalog: dict[str, str]) -> dict[str, dict]:
    if not isinstance(lines, list):
        raise ValueError("poe.ninja hat keine lines[] geliefert")
    gems: dict[str, dict] = {}
    for line in lines:
        if not isinstance(line, dict):
            continue
        name = line.get("name")
        if not isinstance(name, str) or name not in catalog or not eligible(line):
            continue
        listings = line.get("listingCount")
        count = line.get("count")
        listings = listings if type(listings) is int and listings >= 0 else None
        count = count if type(count) is int and count >= 0 else None
        entry = {"price_chaos": round(float(line["chaosValue"]), 2),
                 "color": catalog[name], "level": 1, "quality": 0,
                 "listings": listings, "observations": count}
        old = gems.get(name)
        score = (listings if listings is not None else -1, count or 0)
        prior = ((old["listings"] if old["listings"] is not None else -1),
                 old["observations"] or 0) if old else (-1, -1)
        if score > prior:
            gems[name] = entry
    return gems


def reliable(gem: dict) -> bool:
    return type(gem.get("listings")) is int and gem["listings"] >= MIN_LISTINGS


def color_rankings(gems: dict[str, dict]) -> dict[str, dict]:
    result = {}
    for color in COLORS.values():
        ranked = sorted(((n, g) for n, g in gems.items()
                         if g["color"] == color and reliable(g)),
                        key=lambda pair: pair[1]["price_chaos"], reverse=True)
        top = ranked[:10]
        result[color] = {
            "listed_gems": len(ranked),
            "top10_mean_chaos": (round(statistics.mean(g["price_chaos"] for n, g in top), 2)
                                 if len(top) == 10 else None),
            "top10": [{"name": n, "price_chaos": g["price_chaos"], "listings": g["listings"]}
                      for n, g in top]
        }
    return result


def detect(current: dict, previous: dict, cooldown: dict, now: datetime) -> tuple[list, dict]:
    if not previous:
        return [], cooldown  # First observation is only a baseline.
    events = []
    updated = dict(cooldown)
    for name, gem in current.items():
        if not reliable(gem):
            continue
        price = gem["price_chaos"]
        old = previous.get(name)
        if not old:
            if price >= 80 and gem["listings"] >= 5:
                events.append({"type": "new_hot_gem", "gem": name, "color": gem["color"],
                               "price_chaos": price, "listings": gem["listings"],
                               "watchlist": name in WATCHLIST})
            continue
        if not reliable(old):
            continue
        previous_price = old["price_chaos"]
        if previous_price < 1:
            continue
        change = (price / previous_price - 1) * 100
        difference = abs(price - previous_price)
        if name in WATCHLIST:
            meaningful = difference >= 10 and abs(change) >= 25 and max(price, previous_price) >= 20
        else:
            meaningful = difference >= 15 and abs(change) >= 30 and max(price, previous_price) >= 35
        if not meaningful:
            continue
        last = updated.get(name)
        if isinstance(last, dict):
            try:
                if (now - date(last["when"]) < timedelta(hours=4)
                        and abs(price / last["price"] - 1) < 0.50):
                    continue
            except (ValueError, KeyError, TypeError, ZeroDivisionError):
                pass
        events.append({"type": "price_up" if change > 0 else "price_down",
                       "gem": name, "color": gem["color"],
                       "from_chaos": previous_price, "price_chaos": price,
                       "change_percent": round(change, 1), "listings": gem["listings"],
                       "watchlist": name in WATCHLIST})
        updated[name] = {"when": iso(now), "price": price}

    before = color_rankings(previous)
    after = color_rankings(current)
    before_names = {row["name"] for part in before.values() for row in part["top10"]}
    for part in after.values():
        for row in part["top10"]:
            name = row["name"]
            if (name not in before_names and row["price_chaos"] >= 60
                    and row["listings"] >= 5
                    and not any(e.get("gem") == name for e in events)):
                events.append({"type": "top10_newcomer", "gem": name,
                               "color": current[name]["color"],
                               "price_chaos": row["price_chaos"],
                               "listings": row["listings"], "watchlist": name in WATCHLIST})

    def leader(rankings: dict) -> tuple[str, float] | None:
        eligible_colors = [(name, part["top10_mean_chaos"])
                           for name, part in rankings.items()
                           if part["top10_mean_chaos"] is not None]
        return max(eligible_colors, key=lambda pair: pair[1]) if len(eligible_colors) == 3 else None

    prev_leader = leader(before)
    next_leader = leader(after)
    if prev_leader and next_leader and prev_leader[0] != next_leader[0]:
        qualified = sorted((v["top10_mean_chaos"] for v in after.values()
                            if v["top10_mean_chaos"] is not None), reverse=True)
        # A tiny crossing between colors is not an actionable market change.
        if len(qualified) == 3 and qualified[0] >= qualified[1] * 1.10 and qualified[0] - qualified[1] >= 10:
            events.append({"type": "color_leader_change", "color": next_leader[0],
                           "previous_color": prev_leader[0],
                           "top10_mean_chaos": next_leader[1]})

    priority = {"price_up": 0, "price_down": 1, "new_hot_gem": 2,
                "top10_newcomer": 3, "color_leader_change": 4}
    events.sort(key=lambda e: (priority.get(e["type"], 9),
                               -abs(e.get("change_percent", 0)),
                               -e.get("price_chaos", 0)))
    return events[:8], updated


def main() -> int:
    now = datetime.now(timezone.utc)
    try:
        leagues = fetch(NINJA + "/economy/leagues")
        league = choose_league(leagues)
        print("Ligen:", ", ".join(str(x.get("id")) for x in leagues if isinstance(x, dict)))
        if not league:
            print("Noch keine Challenge-Liga. Kein Standard-Fallback. OK.")
            return 0
        print("Challenge-Liga:", league)
        url = NINJA + "/economy/stash/current/item/overview?" + urllib.parse.urlencode(
            {"league": league, "type": "SkillGem"})
        payload = fetch(url)
        catalog = get_catalog(now)
        market = extract(payload.get("lines"), catalog)
        print("Vergleichbare unkorrumpierte Level-1/0-Gems:", len(market))
        if not market:
            print("Noch keine passenden Preise. OK.")
            return 0

        old = read(DATA / "latest.json", {})
        previous = old.get("gems", {}) if old.get("league") == league else {}
        hist = read(DATA / "history.json", {})
        samples = hist.get("samples", []) if hist.get("league") == league else []
        state = read(DATA / "cooldowns.json", {})
        cooldown = state.get("gems", {}) if state.get("league") == league else {}
        if not isinstance(previous, dict): previous = {}
        if not isinstance(samples, list): samples = []
        if not isinstance(cooldown, dict): cooldown = {}
        events, cooldown = detect(market, previous, cooldown, now)
        stamp = iso(now)
        samples.append({"checked_at": stamp,
                        "prices": {name: g["price_chaos"] for name, g in market.items()}})
        write(DATA / "latest.json", {
            "schema_version": 1, "league": league, "checked_at": stamp,
            "source": "poe.ninja", "price_basis": "level 1 / quality 0 / uncorrupted",
            "minimum_listings_for_alerts": MIN_LISTINGS, "watchlist": list(WATCHLIST),
            "colors": color_rankings(market), "gems": market
        })
        write(DATA / "history.json", {"league": league, "samples": samples[-HISTORY_LIMIT:]})
        write(DATA / "cooldowns.json", {"league": league, "gems": cooldown})
        write(DATA / "latest_alert.json", {
            "schema_version": 1, "league": league, "checked_at": stamp,
            "event_id": stamp, "events": events
        })
        print(f"Samples: {min(len(samples), HISTORY_LIMIT)}; Alarme: {len(events)}")
        for event in events:
            print("ALERT", json.dumps(event, ensure_ascii=False))
        print("Market data successfully saved")
        return 0
    except Exception as exc:
        print(f"FEHLER: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
