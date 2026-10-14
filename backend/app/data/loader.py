"""Load the seed CSVs into plain dicts / engine dataclasses and validate them (spec section 4)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from app.game.config import FOCUS_TO_LANE, ROLE_TO_LANE
from app.game.models import Champion

SEED_DIR = Path(__file__).parent / "seed"
DEFAULT_WIN_RATE = 50.0
CLASS_FIXES = {"Assasin": "Assassin"}


class SeedDataError(ValueError):
    pass


def _rows(name: str, seed_dir: Path) -> list[dict[str, str]]:
    """CSV rows as stripped strings. Blank or whitespace-only lines (a common leftover when editing by hand)
    are skipped. Each row also carries its file line number under `_line` for error messages."""
    rows = []
    with open(seed_dir / name, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            clean = {k.strip(): (v or "").strip() for k, v in row.items() if k is not None}
            if not any(clean.values()):
                continue
            clean["_line"] = reader.line_num
            rows.append(clean)
    return rows


MISSING_ATTRIBUTE_DEFAULT = 1


def _attr(row: dict[str, str], column: str, warnings: list[str]) -> int:
    """Read a champion attribute; a blank cell falls back to a default and is reported."""
    if row[column] == "":
        warnings.append(f"Champion {row['Name']!r} has no {column}; using {MISSING_ATTRIBUTE_DEFAULT}")
        return MISSING_ATTRIBUTE_DEFAULT
    return int(row[column])


def _norm(name: str) -> str:
    """Normalise a champion name for joining (case and punctuation insensitive)."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _fix_class(value: str) -> str:
    for wrong, right in CLASS_FIXES.items():
        value = value.replace(wrong, right)
    return value


@dataclass
class SeedData:
    champions: list[Champion]
    players: list[dict]
    pools: dict[int, list[int]]
    coaches: list[dict]
    teams: list[dict]
    rosters: dict[int, dict[str, int]]   # team id -> lane -> player id (only complete or partial rows)
    warnings: list[str]


def load_seed_data(seed_dir: Path = SEED_DIR) -> SeedData:
    warnings: list[str] = []

    stats: dict[str, dict[str, str]] = {}
    for r in _rows("ChampionStatistics.csv", seed_dir):
        try:
            float(r["WinRate"]), float(r["PickRate"])
        except (KeyError, ValueError) as exc:
            raise SeedDataError(f"ChampionStatistics.csv line {r['_line']} ({r.get('Champion', '?')!r}): "
                                f"WinRate and PickRate must be numbers") from exc
        key = _norm(r["Champion"])
        if key in stats:
            warnings.append(f"ChampionStatistics.csv has two rows for {r['Champion']!r} (line {r['_line']} wins); delete the stale one")
        stats[key] = r
    champions: list[Champion] = []
    placeholder_ids: dict[int, str] = {}
    for r in _rows("Champions.csv", seed_dir):
        label = f"Champions.csv line {r['_line']} ({r.get('Name') or 'no name'!r})"
        if r.get("Name") and all(not v for k, v in r.items() if k not in ("Id", "Name", "_line")):
            # a placeholder row (only Id and Name filled in): reserve the champion, add it to the game once completed
            warnings.append(f"{label}: only Id and Name are filled in, so it is not in the game yet")
            if not r.get("Id", "").isdigit():
                raise SeedDataError(f"{label}: placeholder rows still need a numeric Id")
            if int(r["Id"]) in placeholder_ids:
                raise SeedDataError(f"{label}: id {r['Id']} is already used by the placeholder {placeholder_ids[int(r['Id'])]!r}")
            placeholder_ids[int(r["Id"])] = r["Name"]
            continue
        stat = stats.get(_norm(r.get("Name", "")))
        if stat is None:
            warnings.append(f"No statistics row for champion {r.get('Name')!r}; using win rate {DEFAULT_WIN_RATE}")
        try:
            if not r.get("Name"):
                raise ValueError("Name is empty")
            if r.get("DamageType") not in ("P", "M", "PM"):
                raise ValueError(f"DamageType must be P, M or PM, not {r.get('DamageType')!r}")
            champions.append(Champion(
                id=int(r["Id"]), name=r["Name"], champ_class=_fix_class(r["Class"]), style=int(r["Style"]),
                difficulty=int(r["Difficulty"]), damage_type=r["DamageType"], damage=_attr(r, "Damage", warnings),
                sturdiness=_attr(r, "Sturdiness", warnings), cc=_attr(r, "Crowd-Control", warnings),
                mobility=_attr(r, "Mobility", warnings), utility=_attr(r, "Utility", warnings),
                win_rate=float(stat["WinRate"]) if stat else DEFAULT_WIN_RATE,
                pick_rate=float(stat["PickRate"]) if stat else 0.0,
            ))
        except KeyError as exc:
            raise SeedDataError(f"{label}: missing column {exc}") from exc
        except ValueError as exc:
            detail = str(exc)
            if detail.startswith("invalid literal"):
                detail = "a number column (Id, Style, Difficulty or an attribute) is blank or not a number"
            raise SeedDataError(f"{label}: {detail}") from exc
    seen: dict[int, str] = {}
    for pid, pname in placeholder_ids.items():
        if pid in {c.id for c in champions}:
            raise SeedDataError(f"Champions.csv: id {pid} is used by both {next(c.name for c in champions if c.id == pid)!r} and the placeholder {pname!r}")
    for c in champions:
        if c.id in seen:
            raise SeedDataError(f"Champions.csv: id {c.id} is used by both {seen[c.id]!r} and {c.name!r}")
        seen[c.id] = c.name
    champion_ids = set(seen)

    players = []
    for r in _rows("Players.csv", seed_dir):
        if r["Role"] not in ROLE_TO_LANE:
            raise SeedDataError(f"Player {r['Name']!r} has unknown role {r['Role']!r}")
        secondary = (r.get("SecondaryRole") or "").strip() or None   # optional column
        if secondary is not None and (secondary not in ROLE_TO_LANE or secondary == r["Role"]):
            raise SeedDataError(f"Player {r['Name']!r} has invalid secondary role {secondary!r}")
        players.append({
            "id": int(r["ID"]), "name": r["Name"], "role": ROLE_TO_LANE[r["Role"]],
            "secondary_role": ROLE_TO_LANE[secondary] if secondary else None, "age": int(r["Age"]),
            "aggr": int(r["aggr"]), "aware": int(r["aware"]), "pos": int(r["pos"]),
            "dmg": int(r["dmg"]), "cs": int(r["cs"]), "region": r["Region"],
        })
    player_ids = {p["id"] for p in players}

    pools: dict[int, list[int]] = {}
    for r in _rows("PlayerChampionPools.csv", seed_dir):
        pid = int(r["PlayerId"])
        pool = [int(r[f"ChampionId{i}"]) for i in range(1, 6)]
        if pid not in player_ids:
            raise SeedDataError(f"Champion pool for unknown player {pid}")
        if len(set(pool)) != len(pool):
            raise SeedDataError(f"Player {pid} has duplicate champions in their pool")
        for cid in pool:
            if cid not in champion_ids:
                raise SeedDataError(f"Player {pid} pool references unknown champion {cid}")
        pools[pid] = pool

    coaches = [{"id": int(r["ID"]), "name": r["Name"], "draft": int(r["Draft"]), "synergy": int(r["Synergy"])}
               for r in _rows("Coaches.csv", seed_dir)]

    teams = []
    for r in _rows("Teams.csv", seed_dir):
        teams.append({
            "id": int(r["ID"]), "name": r["Name"], "logo": r["Logo"], "style1": r["Style1"], "style2": r["Style2"],
            "focus1": FOCUS_TO_LANE.get(r["Focus1"]), "focus2": FOCUS_TO_LANE.get(r["Focus2"]),
            "fanbase": r["Fanbase"], "region": r["Region"],
        })
    team_ids = {t["id"] for t in teams}

    rosters: dict[int, dict[str, int]] = {}
    lane_columns = {"Top": "TOP", "Jungle": "JUNGLE", "Mid": "MID", "Bot": "BOT", "Supp": "SUPPORT"}
    coach_ids = {c["id"] for c in coaches}
    for r in _rows("TeamRosters.csv", seed_dir):
        tid = int(r["TeamID"])
        if tid not in team_ids:
            raise SeedDataError(f"Roster for unknown team {tid}")
        slots = {lane: int(r[col]) for col, lane in lane_columns.items()}
        for lane, pid in slots.items():
            if pid not in player_ids:
                raise SeedDataError(f"Team {tid} {lane} references unknown player {pid}")
        if int(r["Coach"]) not in coach_ids:
            raise SeedDataError(f"Team {tid} references unknown coach {r['Coach']}")
        rosters[tid] = slots
        for t in teams:
            if t["id"] == tid:
                t["coach_id"] = int(r["Coach"])

    for t in teams:
        if t["id"] not in rosters:
            warnings.append(f"Team {t['name']!r} has no roster; it will not be selectable")

    unused = set(stats) - {_norm(c.name) for c in champions}
    if unused:
        warnings.append(f"{len(unused)} statistics rows have no matching champion")

    return SeedData(champions, players, pools, coaches, teams, rosters, warnings)


def seed_team_setup(data: SeedData, team_id: int, lineup: dict[str, int]):
    """Build an engine TeamSetup from seed data (used by tests, scripts and the balance suite)."""
    from app.game.config import FOCUS_TO_LANE as _F  # noqa: F401
    from app.game.models import CoachSpec, PlayerSpec, TeamSetup

    team = next(t for t in data.teams if t["id"] == team_id)
    players = {p["id"]: p for p in data.players}
    coach = next(c for c in data.coaches if c["id"] == team["coach_id"])
    roster = {}
    for lane, pid in data.rosters[team_id].items():
        p = players[pid]
        roster[lane] = PlayerSpec(p["id"], p["name"], p["role"], p["age"], p["aggr"], p["aware"], p["pos"],
                                  p["dmg"], p["cs"], tuple(data.pools[pid]))
    styles = tuple(s for s in (team["style1"], team["style2"]) if s)
    focus = tuple(f for f in (team["focus1"], team["focus2"]) if f)
    return TeamSetup(team["id"], team["name"], styles, focus,
                     CoachSpec(coach["id"], coach["name"], coach["draft"], coach["synergy"]), roster, dict(lineup))
