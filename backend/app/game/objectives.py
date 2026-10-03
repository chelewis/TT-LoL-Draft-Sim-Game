"""Dragons, barons, towers and sieges (spec 9.10, 9.11)."""
from __future__ import annotations

from .state import Match, TeamState
from .structures import STRUCTURE_LANES


def _bounty_if_behind(match: Match, team: TeamState, enemy: TeamState) -> None:
    """A team more than `bounty_gold_deficit` behind in gold gets a bounty per tower taken."""
    eco = match.config["economy"]
    if team.gold < enemy.gold - eco["bounty_gold_deficit"]:
        for p in team.players.values():
            p.gold += eco["bounty_gold"]
            p.lane_score += eco["bounty_lane_score"]
        match.emit("BOUNTY", team=team.side, gold_deficit=round(enemy.gold - team.gold))


# ---------------------------------------------------------------- dragons
def roll_dragon(match: Match) -> None:
    obj = match.config["objectives"]
    blue, red = match.sides
    any_soul = blue.soul or red.soul
    if not any_soul and match.elementals_taken >= obj["elemental_pool"]:
        return
    taker = blue if match.rng.random() < match.control_ratio(blue) else red
    enemy = match.other(taker)
    taker.dragons += 1

    if any_soul:
        taker.elder_fights = obj["elder_fights"]
        match.emit("ELDER_DRAGON", team=taker.side)
        return

    match.elementals_taken += 1
    match.emit("DRAGON", team=taker.side, dragons=taker.dragons)
    # each dragon buffs the team's lane scores
    for p in taker.players.values():
        p.lane_score += p.lane_score * obj["dragon_lane_buff"]
    if taker.dragons >= obj["dragon_soul_at"] and not enemy.soul:
        taker.soul = True
        for p in taker.players.values():
            p.lane_score *= obj["soul_lane_multiplier"]
            p.gold += match.config["economy"]["soul_bonus"]
        match.emit("DRAGON_SOUL", team=taker.side)


# ----------------------------------------------------------------- towers
def roll_tower(match: Match) -> None:
    """One tower trade from an objective roll: only lane towers, never inhibitors or the nexus."""
    blue, red = match.sides
    taker = blue if match.rng.random() < match.control_ratio(blue) else red
    enemy = match.other(taker)
    lanes = enemy.structures.lanes_with_tower()
    if not lanes:
        return
    lane = match.rng.choice(lanes)
    _destroy_lane_structure(match, taker, enemy, lane, source="objective")


def _destroy_lane_structure(match: Match, attacker: TeamState, defender: TeamState, lane: str, source: str) -> None:
    kind = defender.structures.destroy_lane_structure(lane)
    receiver = attacker.players[lane]
    receiver.gold += match.config["economy"]["tower"]
    match.emit(kind.upper(), team=attacker.side, lane=lane, source=source,
               towers_remaining=defender.structures.total_towers - defender.structures.total_towers_down)
    if kind == "tower":
        _bounty_if_behind(match, attacker, defender)


def roll_baron(match: Match) -> None:
    blue, red = match.sides
    taker = blue if match.rng.random() < match.control_ratio(blue) else red
    taker.barons += 1
    taker.power_play = True
    match.emit("BARON", team=taker.side, barons=taker.barons)
    siege(match, taker, kills=0, reason="baron")


# ------------------------------------------------------------------ siege
def siege(match: Match, attacker: TeamState, kills: int, reason: str) -> None:
    """Attempt to destroy enemy structures after a fight win or a baron (spec 9.11)."""
    cfg = match.config["structures"]
    defender = match.other(attacker)
    hits = 1 + (1 if kills >= 4 else 0)
    if attacker.power_play:
        hits += cfg["baron_extra_hits"]
        attacker.power_play = False
    ratio = match.control_ratio(attacker, roll=False)
    chance = cfg["siege_base_chance"] + cfg["siege_control_scale"] * (ratio - 0.5)
    chance = max(0.15, min(0.95, chance))

    landed = 0
    for _ in range(hits):
        if match.ended:
            break
        if match.rng.random() >= chance:
            continue
        if _siege_hit(match, attacker, defender):
            landed += 1
    match.emit("SIEGE", team=attacker.side, reason=reason, hits=hits, landed=landed)


def _siege_hit(match: Match, attacker: TeamState, defender: TeamState) -> bool:
    s = defender.structures
    # the nexus and nexus towers cannot fall before `nexus_min_minute`
    late_enough = match.minute >= match.config["structures"]["nexus_min_minute"]
    if late_enough and s.nexus_unlocked:
        s.destroy_nexus()
        match.emit("NEXUS", team=attacker.side)
        match.end(attacker.side, "NEXUS")
        return True
    if late_enough and s.nexus_towers_unlocked:
        s.destroy_nexus_tower()
        lane = match.rng.choice(STRUCTURE_LANES)
        attacker.players[lane].gold += match.config["economy"]["tower"]
        match.emit("NEXUS_TOWER", team=attacker.side, source="siege",
                   towers_remaining=s.total_towers - s.total_towers_down)
        _bounty_if_behind(match, attacker, defender)
        return True
    lanes = s.lanes_with_structure()
    if not lanes:
        return False
    # prefer lanes where the attacker leads in lane score, plus focus lane preference
    weights = []
    for lane in lanes:
        lead = attacker.players[lane].lane_score - defender.players[lane].lane_score
        weight = max(1.0, 1.0 + lead / 100.0)
        for index, focus in enumerate(attacker.setup.focus):
            if focus and _focus_lane(focus) == lane:
                weight *= 1.3 if index == 0 else 1.15
        weights.append(weight)
    lane = match.rng.choices(lanes, weights=weights, k=1)[0]
    _destroy_lane_structure(match, attacker, defender, lane, source="siege")
    return True


def _focus_lane(focus: str) -> str:
    from .config import FOCUS_TO_LANE
    return FOCUS_TO_LANE.get(focus, focus)
