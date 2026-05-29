#!/usr/bin/env python3
"""
Sleeper startup dynasty draft data export.
Fetches all API data, saves raw JSON files, and produces draft_summary.md.
"""

import json
import time
import urllib.request
from pathlib import Path

LEAGUE_ID = "1338318874067615744"
OUT_DIR = Path(__file__).parent


def fetch(url: str, label: str) -> dict | list:
    print(f"  Fetching {label} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.88"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data


def save(data, filename: str):
    path = OUT_DIR / filename
    path.write_text(json.dumps(data, indent=2))
    print(f"  Saved {filename} ({path.stat().st_size // 1024} KB)")
    return data


def main():
    print("\n=== Fetching Sleeper data ===\n")

    league = save(fetch(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}", "league"), "league.json")
    users  = save(fetch(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/users", "users"), "users.json")
    rosters = save(fetch(f"https://api.sleeper.app/v1/league/{LEAGUE_ID}/rosters", "rosters"), "rosters.json")

    draft_id = league["draft_id"]
    print(f"\n  draft_id = {draft_id}\n")

    draft  = save(fetch(f"https://api.sleeper.app/v1/draft/{draft_id}", "draft"), "draft.json")
    picks  = save(fetch(f"https://api.sleeper.app/v1/draft/{draft_id}/picks", "picks"), "picks.json")
    players = save(fetch("https://api.sleeper.app/v1/players/nfl", "players (NFL DB, large)"), "players.json")

    print("\n=== Building draft_summary.md ===\n")

    # --- lookup tables ---
    # user_id → {username, display_name}
    user_map = {u["user_id"]: u for u in users}

    # owner_id → roster (contains settings.waiver_position == draft_slot in some leagues;
    # draft slot is in draft.slot_to_roster_id which maps slot → roster_id)
    roster_map = {r["roster_id"]: r for r in rosters}

    # slot (int) → roster_id  (from draft metadata)
    slot_to_roster = {int(slot): rid for slot, rid in draft.get("slot_to_roster_id", {}).items()}

    # roster_id → owner_id
    roster_owner = {r["roster_id"]: r.get("owner_id") for r in rosters}

    # player_id → {full_name, position, team}
    def player_info(pid: str) -> tuple[str, str, str]:
        p = players.get(pid, {})
        name = p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip() or f"ID:{pid}"
        pos  = p.get("fantasy_positions", [None])[0] or p.get("position") or "?"
        team = p.get("team") or "FA"
        return name, pos, team

    # picks keyed by (round, pick_no) within the draft
    # picks list has: round, pick_no (pick within round), draft_slot, player_id, metadata
    # group by draft_slot
    picks_by_slot: dict[int, list] = {}
    for pk in picks:
        slot = pk.get("draft_slot")
        picks_by_slot.setdefault(slot, []).append(pk)

    # sort each team's picks by (round, pick_no)
    for slot in picks_by_slot:
        picks_by_slot[slot].sort(key=lambda p: (p["round"], p["pick_no"]))

    # --- build markdown ---
    lines = [
        f"# Startup Dynasty Draft Summary",
        f"",
        f"**League ID:** {LEAGUE_ID}  ",
        f"**Draft ID:** {draft_id}  ",
        f"**Draft Type:** {draft.get('type','?')} — {draft.get('status','?')}  ",
        f"**Rounds:** {draft.get('settings', {}).get('rounds', '?')}  ",
        f"",
    ]

    num_teams = draft.get("settings", {}).get("teams", 12)
    for slot in range(1, num_teams + 1):
        roster_id = slot_to_roster.get(slot)
        owner_id  = roster_owner.get(roster_id) if roster_id else None
        user      = user_map.get(owner_id, {}) if owner_id else {}

        username     = user.get("display_name") or user.get("username") or f"(unknown owner_id={owner_id})"
        team_name    = user.get("metadata", {}).get("team_name") or ""
        display_name = team_name if team_name else username

        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## Slot {slot:02d} — {display_name}")
        if team_name and team_name != username:
            lines.append(f"**Sleeper username:** {username}  ")
        lines.append(f"**Roster ID:** {roster_id}  ")
        lines.append(f"")

        team_picks = picks_by_slot.get(slot, [])
        if team_picks:
            lines.append(f"| Rd.Pick | Overall | Player | Pos | NFL Team |")
            lines.append(f"|---------|---------|--------|-----|----------|")
            for pk in team_picks:
                rd  = pk["round"]
                pno = pk["pick_no"]
                overall = pk.get("pick_no")  # within round
                overall_pick = (rd - 1) * num_teams + pno
                pid  = pk.get("player_id") or (pk.get("metadata") or {}).get("player_id") or ""
                if pid:
                    name, pos, team = player_info(pid)
                else:
                    meta = pk.get("metadata") or {}
                    name = meta.get("first_name","") + " " + meta.get("last_name","")
                    name = name.strip() or "—"
                    pos  = meta.get("position") or "?"
                    team = meta.get("team") or "FA"
                lines.append(f"| {rd}.{pno:02d} | {overall_pick:>3} | {name} | {pos} | {team} |")
        else:
            lines.append("_No picks recorded for this slot._")

        lines.append(f"")

    md = "\n".join(lines)

    out_path = OUT_DIR / "draft_summary.md"
    out_path.write_text(md)
    print(f"  Saved draft_summary.md ({out_path.stat().st_size // 1024} KB)")

    print("\n=== Done! ===\n")
    print(md)


if __name__ == "__main__":
    main()
