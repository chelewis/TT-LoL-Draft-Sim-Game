"""How two champions interact in the simulation, for the Meta → Champion Pairs page: their same-team and
against-team win rates, and a few notes on what the engine does with the pair. Pure Python, no framework or
database imports.

Every number comes from the simulation's own formulas and the live config (like team_insights.py), so the notes
change when an admin changes the win rate tables or the simulation settings. Effects that are switched off in the
config give no note.

Where they meet decides which effects apply:
- Same lane (a shared usual role): the matchup wheel, the lane counter, range in lane and waveclear CS.
- Bot lane (one bot, one support): the lane counter and range in lane (each faces the enemy duo), not the wheel.
- No shared lane: they only meet in fights.
"""
from __future__ import annotations

from dataclasses import replace

from .matchup import apply_coach_draft, lane_matchup
from .models import Champion, MatchupTable
from .range_waveclear import NEUTRAL, avg_range, range_fight_multiplier, range_lane_multiplier, waveclear_lane_cs
from .scaling import scaling_multiplier
from .state import damage_balance_penalty, damage_profile
from .win_rates import ally_delta, counter_delta, multiplier

BOT_LANE = ("BOT", "SUPPORT")
CS_LANES = ("TOP", "MID", "BOT")          # lanes whose CS depends on waveclear against the lane opponent
LANE_LABEL = {"TOP": "Top", "JUNGLE": "Jungle", "MID": "Mid", "BOT": "Bot lane", "SUPPORT": "Support"}
NEUTRAL_DRAFT = 5                         # a coach Draft rating that leaves wheel multipliers unchanged
MAX_NOTES = 3
MIN_NOTES = 2
COUNTER_POINTS = 2.0                      # a win rate this far from 50 counts as a counter, not an even matchup
COMP_SHARE = 2 / 5                        # two champions are this much of a comp (weights the damage-mix note)


def _note(kind: str, title: str, detail: str, weight: float) -> dict:
    return {"kind": kind, "title": title, "detail": detail, "weight": round(abs(weight), 3)}


def _x(value: float) -> str:
    return f"x{value:.2f}"


def _roles(c: Champion) -> str:
    return " / ".join(LANE_LABEL[r] for r in c.roles) if c.roles else "any lane"


def _pick(notes: list[dict], fallbacks: list[dict]) -> list[dict]:
    """The biggest effects first, at most MAX_NOTES; topped up from `fallbacks` to MIN_NOTES."""
    out = sorted(notes, key=lambda n: -n["weight"])[:MAX_NOTES]
    for note in fallbacks:
        if len(out) >= MIN_NOTES:
            break
        if all(n["title"] != note["title"] for n in out):
            out.append(note)
    return out


def _late_minute(config: dict) -> int:
    return next((int(p["minutes"][0]) for p in config["phases"] if p["name"] == "late"), 25)


# ------------------------------------------------------------------ where they play
def meeting_lane(a: Champion, b: Champion) -> tuple[str | None, bool]:
    """(lane, direct): the lane where they would face each other, and whether head to head (same role) rather
    than across the bot lane (bot vs support). (None, False) when they never share a lane."""
    if a.roles and b.roles and a.roles[0] == b.roles[0]:
        return a.roles[0], True
    shared = [r for r in a.roles if r in b.roles]
    if shared:
        return shared[0], True
    if any(r in BOT_LANE for r in a.roles) and any(r in BOT_LANE for r in b.roles):
        return "BOT", False
    return None, False


def bot_duo(a: Champion, b: Champion) -> bool:
    """Whether they can share the bot lane on one team (one bot, the other support)."""
    return ("BOT" in a.roles and "SUPPORT" in b.roles) or ("SUPPORT" in a.roles and "BOT" in b.roles)


def lane_clash(a: Champion, b: Champion) -> str | None:
    """The one lane both only play, so on one team one of them has to go off-role; None when they fit."""
    if not a.roles or not b.roles:
        return None
    if any(la != lb for la in a.roles for lb in b.roles):
        return None
    return a.roles[0]


# ------------------------------------------------------------------ same team
def _synergy_note(a: Champion, b: Champion, table: MatchupTable, config: dict) -> dict | None:
    wr = config["win_rates"]
    rate = table.ally_rate(a.id, b.id)
    if not wr["enabled"] or rate is None:
        return None
    delta = ally_delta([a.id, b.id], table, config)
    fight = multiplier(delta, wr["fight_synergy_scale"], config)
    detail = f"{rate:.1f}% together: {_x(fight)} fight power when they fight side by side"
    weight = fight - 1
    if bot_duo(a, b):
        duo = multiplier(delta, wr["lane_duo_scale"], config)
        detail += f", and {_x(duo)} lane score as a bot / support duo"
        weight += duo - 1
    detail += " (in bigger fights it's averaged with every other pair)."
    if delta >= COUNTER_POINTS:
        return _note("strength", "Strong synergy", detail, weight)
    if delta <= -COUNTER_POINTS:
        return _note("weakness", "Poor synergy", detail, weight)
    return _note("neutral", "Neutral synergy", detail, weight)


def _clash_note(a: Champion, b: Champion, config: dict) -> dict | None:
    lane = lane_clash(a, b)
    cfg = config["off_role"]
    if lane is None or not cfg["enabled"]:
        return None
    return _note("weakness", f"Both want {LANE_LABEL[lane]}",
                 f"Neither usually plays another lane, so one of them goes off-role: {_x(1 - cfg['lane_penalty'])} "
                 f"lane score, unless it's in that player's top {cfg['pool_exempt']} pool picks.",
                 cfg["lane_penalty"])


def _damage_note(a: Champion, b: Champion, config: dict) -> dict | None:
    cfg = config["damage_balance"]
    profile = damage_profile([a, b])
    total = profile["physical"] + profile["magic"]
    if not cfg["enabled"] or total <= 0:
        return None
    physical = profile["physical"] / total
    penalty = damage_balance_penalty(profile, config)
    if penalty > 0:
        kind, other = ("physical", "magic") if physical > 0.5 else ("magic", "physical")
        return _note("weakness", f"Both {kind} damage",
                     f"{max(physical, 1 - physical):.0%} {kind} between them. A comp over {cfg['threshold']:.0%} one "
                     f"damage type loses up to {cfg['max_penalty']:.0%} of its fight damage once the enemy itemizes, "
                     f"so the other picks need {other} damage.", penalty * COMP_SHARE)
    return _note("strength", "Mixed damage",
                 f"{physical:.0%} physical / {1 - physical:.0%} magic: hard for the enemy to itemize against.", 0.02)


def _range_note(a: Champion, b: Champion, config: dict) -> dict | None:
    if not config["range"]["enabled"]:
        return None
    pair = [a, b]
    rng = avg_range(pair)
    if NEUTRAL - 0.5 < rng < NEUTRAL + 0.5:
        return None
    enemy = [replace(a, attack_range=NEUTRAL)] * 2       # an average-range enemy
    teamfight = range_fight_multiplier(pair, enemy, 5, config)
    skirmish = range_fight_multiplier(pair, enemy, 3, config)
    if rng > NEUTRAL:
        return _note("neutral", "Long-range pair",
                     f"Average range {rng:.1f}: {_x(teamfight)} in 4v4 and 5v5 fights (poke and kiting) but "
                     f"{_x(skirmish)} in small skirmishes against an average-range team.", teamfight - 1)
    return _note("neutral", "Melee dive pair",
                 f"Average range {rng:.1f}: {_x(skirmish)} in skirmishes of 3 or fewer (dive) but {_x(teamfight)} in "
                 "4v4 and 5v5 fights against an average-range team.", skirmish - 1)


def _scaling_note_together(a: Champion, b: Champion, config: dict) -> dict | None:
    if not config["champion_scaling"]["enabled"] or a.scaling == 2 and b.scaling == 2:
        return None
    late = _late_minute(config)
    if a.scaling == b.scaling:
        lane, end = scaling_multiplier(a, "lane", config), scaling_multiplier(a, "late", config)
        if a.scaling == 1:
            return _note("neutral", "Early-game pair",
                         f"Both peak early: {_x(lane)} in lane and early fights, {_x(end)} after {late} minutes. "
                         "Push the lead before they fall off.", (abs(lane - 1) + abs(end - 1)) / 2)
        return _note("neutral", "Late-game pair",
                     f"Both scale: {_x(lane)} in lane, {_x(end)} after {late} minutes. Survive the lane phase and "
                     "play for late fights.", (abs(lane - 1) + abs(end - 1)) / 2)
    if {a.scaling, b.scaling} == {1, 3}:
        early, scaler = (a, b) if a.scaling < b.scaling else (b, a)
        e_end, s_lane = scaling_multiplier(early, "late", config), scaling_multiplier(scaler, "lane", config)
        return _note("weakness", "Power spikes don't line up",
                     f"{early.name} peaks early and drops to {_x(e_end)} late; {scaler.name} is {_x(s_lane)} in lane "
                     "and only comes online late.", (abs(e_end - 1) + abs(s_lane - 1)) / 4)
    return None


def _control_note(a: Champion, b: Champion, config: dict) -> dict | None:
    f = config["fight"]
    avg = sum(c.cc + c.mobility + c.utility for c in (a, b)) / 2
    mod = max(1.0 + f["control_scale"] * (avg - f["control_average"]) / f["control_average"], 0.1)
    if abs(mod - 1) < 0.03:
        return None
    good = mod > 1
    return _note("strength" if good else "weakness", "Lots of control" if good else "Little control",
                 f"Crowd control + mobility + utility averages {avg:.1f} against a typical {f['control_average']:g}: "
                 f"{_x(mod)} fight power when they fight together.", mod - 1)


def same_team(a: Champion, b: Champion, table: MatchupTable, config: dict) -> list[dict]:
    notes = [n for n in (_synergy_note(a, b, table, config), _clash_note(a, b, config), _damage_note(a, b, config),
                         _range_note(a, b, config), _scaling_note_together(a, b, config), _control_note(a, b, config))
             if n is not None]
    fallbacks = []
    if config["win_rates"]["enabled"] and table.ally_rate(a.id, b.id) is None:
        fallbacks.append(_note("neutral", "No same-team win rate",
                               "Without data the pair gets no synergy bonus or penalty in fights.", 0.0))
    fallbacks.append(_note("neutral", "Nothing stands out",
                           "No big synergy or clash between them in the simulation's formulas.", 0.0))
    return _pick(notes, fallbacks)


# ------------------------------------------------------------------ against
def _side(value: float) -> str:
    return "a" if value > 0 else "b" if value < 0 else "even"


def _counter_note(a: Champion, b: Champion, lane: str | None, table: MatchupTable, config: dict) -> dict | None:
    wr = config["win_rates"]
    rate = table.enemy_rate(a.id, b.id)
    if not wr["enabled"] or rate is None:
        return None
    delta = counter_delta([a.id], [b.id], table, config)
    fight_a, fight_b = (multiplier(d, wr["fight_counter_scale"], config) for d in (delta, -delta))
    winner, loser = (a, b) if delta >= 0 else (b, a)
    win_rate = rate if delta >= 0 else 100 - rate
    if delta == 0:
        return _note("even", "Even matchup", f"{rate:.1f}%: no counter bonus either way.", 0.0)
    detail = f"{winner.name} wins {win_rate:.1f}%: {a.name} {_x(fight_a)}, {b.name} {_x(fight_b)} fight power " \
             "when they face each other"
    weight = fight_a - 1
    if lane is not None:
        lane_a, lane_b = (multiplier(d, wr["lane_counter_scale"], config) for d in (delta, -delta))
        detail += f"; {_x(lane_a)} / {_x(lane_b)} lane score in {LANE_LABEL[lane]}"
        if lane == "BOT":
            detail += " (averaged over both enemy bot laners)"
        weight += lane_a - 1
    if abs(delta) < COUNTER_POINTS:
        return _note("even", "Even matchup", detail + ".", weight)
    return _note(_side(delta), f"{winner.name} counters {loser.name}", detail + ".", weight)


def _wheel_note(a: Champion, b: Champion, lane: str, config: dict) -> dict:
    mult_a, mult_b, label = lane_matchup(a, b, config)
    if label is None:
        return _note("even", "Even on the matchup wheel",
                     f"{a.name}'s {a.strength} vs {b.name}'s {b.strength}: neither beats the other, so no wheel bonus "
                     f"in {LANE_LABEL[lane]}.", 0.01)
    winner, loser = (a, b) if label.startswith("A") else (b, a)
    mult = apply_coach_draft(max(mult_a, mult_b), NEUTRAL_DRAFT, config)
    strength = "strongly" if label.endswith("STRONG") else "slightly"
    return _note("a" if winner is a else "b", f"{winner.name} wins the matchup wheel",
                 f"{winner.name}'s {winner.strength} {strength} beats {loser.name}'s {loser.strength}: {_x(mult)} lane "
                 f"score in {LANE_LABEL[lane]}, more with a high-Draft coach.", mult - 1)


def _range_against_note(a: Champion, b: Champion, lane: str | None, config: dict) -> dict | None:
    if not config["range"]["enabled"] or a.attack_range == b.attack_range:
        return None
    longer, shorter = (a, b) if a.attack_range > b.attack_range else (b, a)
    fights = "Range wins teamfights and melee wins skirmishes, so it shifts which fights each team wants."
    if lane is None or lane == "JUNGLE":
        return _note("even", f"{longer.name} out-ranges {shorter.name}",
                     f"Range {longer.attack_range} vs {shorter.attack_range}. {fights}", 0.005)
    lane_mult = range_lane_multiplier([longer], [shorter], config)
    duo = " (bot lane compares duo averages)" if lane == "BOT" else ""
    return _note("a" if longer is a else "b", f"{longer.name} out-ranges {shorter.name}",
                 f"Range {longer.attack_range} vs {shorter.attack_range}: {_x(lane_mult)} lane score in "
                 f"{LANE_LABEL[lane]}{duo}. {fights}", lane_mult - 1)


def _waveclear_note(a: Champion, b: Champion, lane: str, config: dict) -> dict | None:
    if not config["waveclear"]["enabled"] or a.waveclear == b.waveclear or lane not in CS_LANES:
        return None
    cs_a, cs_b = waveclear_lane_cs(a, b, config), waveclear_lane_cs(b, a, config)
    faster = a if cs_a > cs_b else b
    return _note("a" if faster is a else "b", f"{faster.name} clears waves faster",
                 f"Waveclear {a.waveclear} vs {b.waveclear}: {a.name} {_x(cs_a)}, {b.name} {_x(cs_b)} lane-phase CS in "
                 f"{LANE_LABEL[lane]}.", abs(cs_a - 1))


def _scaling_against_note(a: Champion, b: Champion, config: dict) -> dict | None:
    if not config["champion_scaling"]["enabled"] or a.scaling == b.scaling:
        return None
    early, scaler = (a, b) if a.scaling < b.scaling else (b, a)
    e_lane, s_lane = scaling_multiplier(early, "lane", config), scaling_multiplier(scaler, "lane", config)
    e_late, s_late = scaling_multiplier(early, "late", config), scaling_multiplier(scaler, "late", config)
    late = _late_minute(config)
    if early.scaling == 2:
        title = f"{scaler.name} outscales {early.name}"
    elif scaler.scaling == 2:
        title = f"{early.name} has the early edge"
    else:
        title = f"{early.name} early, {scaler.name} late"
    return _note("even", title,
                 f"{_x(e_lane)} vs {_x(s_lane)} in lane, {_x(e_late)} vs {_x(s_late)} after {late} minutes: "
                 f"{early.name} wants a short game, {scaler.name} a long one.",
                 (abs(e_lane / s_lane - 1) + abs(s_late / e_late - 1)) / 4)


def against(a: Champion, b: Champion, table: MatchupTable, config: dict) -> tuple[list[dict], str | None, bool]:
    """(notes, lane they meet in, whether head to head)."""
    lane, direct = meeting_lane(a, b)
    notes = [_counter_note(a, b, lane, table, config), _range_against_note(a, b, lane, config),
             _scaling_against_note(a, b, config)]
    if direct:
        notes += [_wheel_note(a, b, lane, config), _waveclear_note(a, b, lane, config)]
    fallbacks = []
    if lane is None:
        fallbacks.append(_note("even", "They don't share a lane",
                               f"{a.name} plays {_roles(a)}, {b.name} plays {_roles(b)}: they only meet in fights, so "
                               "the matchup wheel and lane effects don't apply.", 0.0))
    if config["win_rates"]["enabled"] and table.enemy_rate(a.id, b.id) is None:
        fallbacks.append(_note("even", "No against-team win rate",
                               "Without data neither side gets a counter bonus.", 0.0))
    fallbacks.append(_note("even", "Nothing stands out", "No big edge either way in the simulation's formulas.", 0.0))
    return _pick([n for n in notes if n is not None], fallbacks), lane, direct


# ------------------------------------------------------------------ entry point
def summary(c: Champion) -> dict:
    return {"id": c.id, "name": c.name, "class": c.champ_class, "roles": list(c.roles), "damage_type": c.damage_type,
            "range": c.attack_range, "scaling": c.scaling, "waveclear": c.waveclear, "strength": c.strength,
            "weakness": c.weakness}


def analyse_pair(a: Champion, b: Champion, table: MatchupTable, config: dict) -> dict:
    """Both champions, their same-team and against-team win rates (against: a's rate against b) and notes.
    Against-team note kinds say who the effect favours: "a", "b" or "even"."""
    against_notes, lane, direct = against(a, b, table, config)
    return {
        "champions": [summary(a), summary(b)],
        "same_team": {"win_rate": table.ally_rate(a.id, b.id), "notes": same_team(a, b, table, config)},
        "against": {"win_rate": table.enemy_rate(a.id, b.id), "lane": lane, "head_to_head": direct,
                    "notes": against_notes},
    }
