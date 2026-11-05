"""Team notes for the team editor: strengths, weaknesses, suggested playstyles and focus lanes, and ideal comps
from the players' champion pools. Pure Python, no framework or database imports.

Everything is read from the simulation's own formulas with the dice left out (the same terms the CPU drafter
uses in draft_ai.py), so the notes change when an admin changes the simulation config:

- A player's lane value on a champion is draft_ai.lane_fit (stats x champion synergy, comfort, playstyle tags,
  strength fit, off-role penalty) x the champion's scaling over the whole game.
- Lane power compares that with a typical player (every stat at the custom-player budget / 5) on the same
  champion, so it shows what the player's stats and tags add.
- Focus lanes are scored with the lane phase's focus bonus and assist formula (lane_phase.py).
- Comps are searched over every combination of pool champions (one per lane, no repeats) and scored like a
  CPU pick: each player's share of their best lane value, plus same-team synergy, damage balance and range
  in fights, with an extra lean towards each playstyle's kind of comp.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import product
from types import SimpleNamespace
from typing import Mapping, Sequence

from .comfort import comfort_tier, off_role
from .config import FOCUS_TO_LANE, LANES
from .draft_ai import _fight_sizes, game_scaling, lane_fit
from .lane_phase import _assist_fraction, role_factors
from .models import Champion, CoachSpec, MatchupTable, PlayerSpec
from .playstyle import effect_totals
from .range_waveclear import NEUTRAL, avg_range, range_fight_multiplier
from .state import damage_balance_penalty, damage_profile
from .win_rates import ally_delta, multiplier

STYLES = ("early", "scaling", "teamfight", "skirmish")
STYLE_LABEL = {"early": "Early game", "scaling": "Scaling", "teamfight": "Teamfight", "skirmish": "Skirmish"}
LANE_LABEL = {"TOP": "Top", "JUNGLE": "Jungle", "MID": "Mid", "BOT": "Bot", "SUPPORT": "Support"}
# early and scaling pull the lane phase in opposite directions (scaling costs lane score), so they are not
# suggested together
CLASHES = {frozenset(("early", "scaling"))}
STAT_NAMES = {"aggr": "Aggression", "aware": "Awareness", "pos": "Positioning", "dmg": "Damage", "cs": "CS"}

WEIGHTS = {
    "damage_balance": 0.6,   # comp: per unit of fight damage lost to a one-sided damage profile (as draft_ai)
    "archetype": 0.12,       # comp: lean towards the archetype's feature, per unit of that feature
    "max_comps_scored": 20000,
}
MAX_NOTES = 6
MIN_DAMAGE_PENALTY = 0.01   # smaller damage-balance losses count as mixed damage


@dataclass
class _Lane:
    lane: str
    player: PlayerSpec
    values: dict[int, float]      # pool champion id -> lane value (lane fit x whole-game scaling)
    best: int                     # champion id with the highest value
    power: float                  # best value vs a typical player on the same champion


def _pct(x: float) -> str:
    return f"{x * 100:+.0f}%"


def _avg(values: Sequence[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _note(kind: str, title: str, detail: str, weight: float) -> dict:
    return {"kind": kind, "title": title, "detail": detail, "weight": round(abs(weight), 3)}


# ------------------------------------------------------------------ lanes
def _typical(player: PlayerSpec, stat: float) -> PlayerSpec:
    """The same player (pool, role) with every stat at `stat` and no tags."""
    s = round(stat)
    return PlayerSpec(player.id, player.name, player.role, player.age, s, s, s, s, s, player.pool)


def _lanes(roster: Mapping[str, PlayerSpec], champions: Mapping[int, Champion], config: dict,
           typical_stat: float) -> dict[str, _Lane]:
    out = {}
    for lane in LANES:
        p = roster.get(lane)
        if p is None:
            continue
        pool = [cid for cid in dict.fromkeys(p.pool) if cid in champions]
        if not pool:
            continue
        values = {cid: lane_fit(p, champions[cid], config, lane) * game_scaling(champions[cid], config) for cid in pool}
        best = max(values, key=values.get)
        ref = lane_fit(_typical(p, typical_stat), champions[best], config, lane) * game_scaling(champions[best], config)
        out[lane] = _Lane(lane, p, values, best, values[best] / ref if ref > 0 else 1.0)
    return out


# ------------------------------------------------------------------ comps
def _comp_features(comp: Sequence[Champion], averages: dict[str, float]) -> dict[str, float]:
    """Comp shape, each roughly -1..1 around an average comp."""
    control = _avg([c.cc + c.utility for c in comp])
    mobility = _avg([c.mobility for c in comp])
    return {
        "scaling": _avg([c.scaling for c in comp], 2.0) - 2.0,                 # + late game, - early game
        "range": avg_range(comp) - NEUTRAL,                                    # + ranged, - melee
        "control": _clamp((control - averages["control"]) / averages["control"]),
        "mobility": _clamp((mobility - averages["mobility"]) / averages["mobility"]),
    }


ARCHETYPES = {
    # style -> how a comp of that kind leans, from its features
    "early": lambda f: -f["scaling"] + 0.3 * f["mobility"],
    "scaling": lambda f: f["scaling"] + 0.3 * f["control"],
    "teamfight": lambda f: f["range"] + 0.5 * f["control"],
    "skirmish": lambda f: -f["range"] + 0.5 * f["mobility"],
}
ARCHETYPE_LABEL = {
    "early": "Early pressure", "scaling": "Late-game scaling", "teamfight": "Teamfight & poke", "skirmish": "Dive & skirmish",
}


def _comp_base(picks: dict[str, int], lanes: dict[str, _Lane], champions: Mapping[int, Champion],
               table: MatchupTable, config: dict, sizes: tuple[float, float]) -> float:
    """A comp's value without any style lean: each player's share of their best lane value, plus team effects."""
    lane_part = _avg([lanes[l].values[cid] / lanes[l].values[lanes[l].best] for l, cid in picks.items()])
    comp = [champions[cid] for cid in picks.values()]
    bonus = 0.0
    wr = config["win_rates"]
    if len(comp) >= 2:
        bonus += multiplier(ally_delta(list(picks.values()), table, config), wr["fight_synergy_scale"], config) - 1
        bonus -= WEIGHTS["damage_balance"] * damage_balance_penalty(damage_profile(comp), config)
    duo = [picks[l] for l in ("BOT", "SUPPORT") if l in picks]
    if len(duo) == 2:
        bonus += multiplier(ally_delta(duo, table, config), wr["lane_duo_scale"], config) - 1
    # range in fights against an average-range enemy: teamfights favour range, skirmishes melee
    enemy = [replace(comp[0], attack_range=NEUTRAL)] * len(LANES)
    big, small = sizes
    bonus += big * (range_fight_multiplier(comp, enemy, 5, config) - 1)
    bonus += small * (range_fight_multiplier(comp, enemy, 3, config) - 1)
    return lane_part * (1.0 + bonus)


def _search_comps(lanes: dict[str, _Lane], champions: Mapping[int, Champion], table: MatchupTable,
                  config: dict) -> list[tuple[dict[str, int], float, dict[str, float]]]:
    """Every legal comp from the pools (one champion per lane, no repeats): (picks, base value, features)."""
    order = [l for l in LANES if l in lanes]
    options = [sorted(lanes[l].values, key=lanes[l].values.get, reverse=True) for l in order]
    # keep the search small: cut each pool from the bottom until the combinations fit
    while _count(options) > WEIGHTS["max_comps_scored"] and max(len(o) for o in options) > 1:
        longest = max(range(len(options)), key=lambda i: len(options[i]))
        options[longest] = options[longest][:-1]
    sizes = _fight_sizes(config)
    averages = _champion_averages(champions)
    out = []
    for combo in product(*options):
        if len(set(combo)) < len(combo):
            continue
        picks = dict(zip(order, combo))
        comp = [champions[c] for c in combo]
        out.append((picks, _comp_base(picks, lanes, champions, table, config, sizes), _comp_features(comp, averages)))
    return out


def _count(options: list[list[int]]) -> int:
    n = 1
    for o in options:
        n *= max(len(o), 1)
    return n


def _champion_averages(champions: Mapping[int, Champion]) -> dict[str, float]:
    cs = list(champions.values())
    return {"control": _avg([c.cc + c.utility for c in cs], 10.0) or 10.0,
            "mobility": _avg([c.mobility for c in cs], 5.0) or 5.0}


def _describe_comp(picks: dict[str, int], lanes: dict[str, _Lane], champions: Mapping[int, Champion],
                   config: dict) -> dict:
    comp = [champions[cid] for cid in picks.values()]
    profile = damage_profile(comp)
    total = profile["physical"] + profile["magic"]
    physical = profile["physical"] / total if total else 0.5
    scaling = _avg([c.scaling for c in comp], 2.0)
    rng = avg_range(comp)
    notes = []
    penalty = damage_balance_penalty(profile, config)
    if penalty >= MIN_DAMAGE_PENALTY:
        notes.append(f"Leans {'physical' if physical > 0.5 else 'magic'} damage: up to {penalty:.0%} of fight damage "
                     "lost once the enemy itemizes against it")
    else:
        notes.append(f"Mixed damage ({physical:.0%} physical / {1 - physical:.0%} magic)")
    notes.append("Late-game power curve" if scaling >= 2.4 else "Early-game power curve" if scaling <= 1.6
                 else "Even power curve across the game")
    notes.append("Long range: wins teamfights" if rng >= 2.4 else "Melee-heavy: wins skirmishes" if rng <= 1.6
                 else "Balanced range")
    return {
        "picks": {lane: {"champion_id": cid, "name": champions[cid].name,
                         "comfort": comfort_tier(lanes[lane].player, cid, config),
                         "fit": round(lanes[lane].values[cid] / lanes[lane].values[lanes[lane].best], 2)}
                  for lane, cid in picks.items()},
        "damage": {"physical": round(physical, 2), "magic": round(1 - physical, 2)},
        "scaling": round(scaling, 2),
        "range": round(rng, 2),
        "notes": notes,
    }


def _ideal_comps(scored, lanes, champions, config, style_order: Sequence[str]) -> list[dict]:
    """The best comp for each playstyle (suggested styles first), without repeats."""
    if not scored:
        return []
    out, seen = [], set()
    for style in style_order:
        lean = ARCHETYPES[style]
        picks, _, _ = max(scored, key=lambda s: s[1] * (1.0 + WEIGHTS["archetype"] * lean(s[2])))
        key = tuple(sorted(picks.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append({"style": style, "label": ARCHETYPE_LABEL[style], **_describe_comp(picks, lanes, champions, config)})
    return out


# ------------------------------------------------------------------ playstyles
def _style_scores(stats: dict[str, float], typical: float, power: float, features: dict[str, float]) -> list[dict]:
    """Each playstyle's fit (0-100) for this roster and its best comp, with the reasons behind it."""
    def d(stat: str) -> float:          # a team stat average vs typical, -1..1
        return _clamp((stats[stat] - typical) / 3.0)

    lane = _clamp((power - 1.0) * 4)
    terms = {
        "early": [(0.4, -features["scaling"], "pools lean early-game", "pools lean late-game"),
                  (0.3, d("aggr"), "high aggression starts more fights", "low aggression starts fewer fights"),
                  (0.3, lane, "strong lanes", "weak lanes")],
        "scaling": [(0.4, features["scaling"], "pools lean late-game", "pools lean early-game"),
                    (0.3, _clamp((stats["aware"] + stats["pos"] - 2 * typical) / 6.0),
                     "awareness and positioning win objectives", "weak awareness and positioning for objectives"),
                    (0.3, d("cs"), "high CS feeds a long game", "low CS for a long game")],
        "teamfight": [(0.4, features["range"], "ranged champions win teamfights", "melee champions lose teamfights"),
                      (0.3, features["control"], "plenty of crowd control and utility", "little crowd control"),
                      (0.3, d("dmg"), "high damage stat", "low damage stat")],
        "skirmish": [(0.4, -features["range"], "melee champions win skirmishes", "ranged champions lose skirmishes"),
                     (0.3, features["mobility"], "mobile champions", "immobile champions"),
                     (0.3, d("aggr"), "high aggression", "low aggression")],
    }
    out = []
    for style, parts in terms.items():
        score = sum(w * v for w, v, _, _ in parts)
        reasons = [(w * v, good if v > 0 else bad) for w, v, good, bad in parts if abs(w * v) >= 0.03]
        reasons.sort(key=lambda r: -abs(r[0]))
        out.append({"style": style, "label": STYLE_LABEL[style], "score": round(50 + 50 * _clamp(score)),
                    "pros": [t for v, t in reasons if v > 0], "cons": [t for v, t in reasons if v < 0]})
    out.sort(key=lambda s: -s["score"])
    return out


def _pick_styles(scores: list[dict]) -> list[str]:
    first = scores[0]["style"]
    second = next(s["style"] for s in scores[1:] if frozenset((first, s["style"])) not in CLASHES)
    return [first, second]


# ------------------------------------------------------------------ focus lanes
def _lane_total(base: dict[str, float], focus: Sequence[str], synergy: float, fight: dict[str, float],
                config: dict) -> float:
    """The team's lane scores after the focus bonus and assists (lane_phase.run_lane_phase without rolls),
    each weighted by how much that player turns into fight power; plus the top/mid focus CS bonus as gold."""
    lane_cfg, cs_cfg = config["lane"], config["cs"]
    bonus = config["team_style"]["focus_lane_bonus"] if config["team_style"]["enabled"] else 0.0
    team = SimpleNamespace(setup=SimpleNamespace(focus=tuple(focus)))
    weight = {l: (1.0 if focus and focus[0] == l else 0.5 if l in focus[1:] else 0.0) for l in LANES}
    scored = {l: v * (1.0 + bonus * synergy * weight[l]) for l, v in base.items()}
    factors = role_factors(config)
    total = 0.0
    for lane, own in scored.items():
        value = own + sum(scored[o] * _assist_fraction(lane, o, lane_cfg, team) * synergy for o in scored if o != lane)
        value *= factors[lane]
        if lane in ("TOP", "MID"):       # gold is half of a fighter's base strength
            value += 0.5 * base[lane] * cs_cfg["focus_bonus"] * synergy * weight[lane]
        total += value * fight[lane]
    return total


def _focus(lanes: dict[str, _Lane], synergy: float, config: dict) -> tuple[list[dict], list[str]]:
    base = {l: x.values[x.best] for l, x in lanes.items()}
    if not base:
        return [], []
    scale = config["fight"]["dmg_stat_scale"]
    lo, hi = config["lane"]["strength_fit"]["stat_range"]
    mid, half = (lo + hi) / 2, (hi - lo) / 2
    fight = {l: max(1.0 + scale * (x.player.dmg - mid) / half, 0.1) for l, x in lanes.items()}
    none = _lane_total(base, (), synergy, fight, config) or 1.0
    gains = {l: _lane_total(base, (l,), synergy, fight, config) / none - 1 for l in base}
    best_pair = max(((a, b) for a in base for b in base if a != b),
                    key=lambda pair: _lane_total(base, pair, synergy, fight, config), default=None)
    suggested = list(best_pair) if best_pair else list(base)[:1]
    rows = []
    for lane in sorted(base, key=lambda l: -gains[l]):
        x = lanes[lane]
        if lane == "JUNGLE":
            why = f"{x.player.name} passes more of their lane score to all four lanes"
        elif lane == "SUPPORT":
            why = f"{x.player.name} passes more of their lane score to Bot"
        else:
            why = f"Bonus lane score{' and CS' if lane in ('TOP', 'MID') else ''} for {x.player.name}"
        rows.append({"lane": lane, "gain": round(gains[lane], 4), "reason": why, "power": round(x.power, 2)})
    return rows, suggested


# ------------------------------------------------------------------ notes
def _initiative(aggr_total: float, typical_total: float, config: dict) -> float:
    f = config["fight"]
    share = aggr_total / (aggr_total + typical_total) if aggr_total + typical_total > 0 else 0.5
    lo, hi = f["initiative_bounds"]
    return max(lo, min(hi, 0.5 + f["initiative_scale"] * (share - 0.5)))


def _stat_notes(lanes: dict[str, _Lane], stats: dict[str, float], typical: float, config: dict) -> list[dict]:
    notes = []
    players = [x.player for x in lanes.values()]
    n = len(players)
    if not n:
        return notes
    aggr = sum(p.aggr * (1.0 + effect_totals(p).get("initiative", 0.0)) for p in players)
    chance = _initiative(aggr, typical * n, config)
    if abs(chance - 0.5) >= 0.04:
        good = chance > 0.5
        notes.append(_note("strength" if good else "weakness",
                           "Fight initiative" if good else "Slow to start fights",
                           f"Average aggression {stats['aggr']:.1f}: you start about {chance:.0%} of fights against a "
                           "typical team.", (chance - 0.5) * 2))
    obj = sum((p.aware + p.pos) * (1.0 + effect_totals(p).get("objective", 0.0)) for p in players)
    ratio = obj / (2 * typical * n) - 1
    if abs(ratio) >= 0.08:
        good = ratio > 0
        notes.append(_note("strength" if good else "weakness",
                           "Objective control" if good else "Losing objectives",
                           f"Awareness + positioning is {_pct(ratio)} against a typical team when contesting dragons, "
                           "barons and towers.", ratio))
    scale = config["fight"]["dmg_stat_scale"]
    lo, hi = config["lane"]["strength_fit"]["stat_range"]
    mid, half = (lo + hi) / 2, (hi - lo) / 2
    fight = scale * (stats["dmg"] - mid) / half - scale * (typical - mid) / half
    if abs(fight) >= 0.02:
        good = fight > 0
        notes.append(_note("strength" if good else "weakness", "Fight damage" if good else "Low fight damage",
                           f"Average damage stat {stats['dmg']:.1f}: {_pct(fight)} fight performance against a typical "
                           "team.", fight * 4))
    cs = stats["cs"] - typical
    if abs(cs) >= 1.0:
        good = cs > 0
        notes.append(_note("strength" if good else "weakness", "Strong farming" if good else "Weak farming",
                           f"Average CS stat {stats['cs']:.1f} against a typical {typical:.1f}: gold is fight strength.",
                           cs / 4))
    return notes


def _lane_notes(lanes: dict[str, _Lane], champions: Mapping[int, Champion], config: dict) -> list[dict]:
    notes = []
    if lanes:
        best = max(lanes.values(), key=lambda x: x.power)
        worst = min(lanes.values(), key=lambda x: x.power)
        if best.power >= 1.05:
            notes.append(_note("strength", f"{LANE_LABEL[best.lane]} is your strongest lane",
                               f"{best.player.name} on {champions[best.best].name}: {_pct(best.power - 1)} lane score "
                               "against a typical player.", best.power - 1))
        if worst.power <= 0.95 and worst is not best:
            notes.append(_note("weakness", f"{LANE_LABEL[worst.lane]} is your weakest lane",
                               f"{worst.player.name}: {_pct(worst.power - 1)} lane score against a typical player, even on "
                               f"their best pick ({champions[worst.best].name}).", worst.power - 1))
    penalty = config["off_role"]["lane_penalty"]
    for x in lanes.values():
        off = [champions[c].name for c in x.values if off_role(champions[c], x.lane, x.player, config)]
        if off:
            notes.append(_note("weakness", f"Off-role picks in {x.player.name}'s pool",
                               f"{', '.join(off)} {'is' if len(off) == 1 else 'are'} not usually played in "
                               f"{LANE_LABEL[x.lane]}: {_pct(-penalty)} lane score.", 0.1 * len(off)))
        close = [c for c, v in x.values.items() if v >= 0.85 * x.values[x.best]]
        if len(close) == 1 and len(x.values) > 1:
            notes.append(_note("weakness", f"{x.player.name} relies on one champion",
                               f"Only {champions[x.best].name} is close to their best: a ban there hurts.", 0.15))
        risky = [champions[c].name for c in x.values
                 if champions[c].difficulty >= 3 and comfort_tier(x.player, c, config) in ("FAMILIAR", "VULNERABLE")]
        if risky:
            notes.append(_note("weakness", f"Risky hard champions for {x.player.name}",
                               f"{', '.join(risky)}: hard champions low in the pool swing fights both ways and fail "
                               "more often.", 0.08 * len(risky)))
    return notes


def _comp_notes(features: dict[str, float], comp: Sequence[Champion], config: dict) -> list[dict]:
    notes = []
    profile = damage_profile(comp)
    total = profile["physical"] + profile["magic"]
    penalty = damage_balance_penalty(profile, config)
    if penalty >= MIN_DAMAGE_PENALTY:
        kind = "physical" if profile["physical"] > profile["magic"] else "magic"
        notes.append(_note("weakness", f"One-sided damage ({kind})",
                           f"Even your best comp is {max(profile.values()) / total:.0%} {kind}: up to {penalty:.0%} "
                           "of fight damage lost once the enemy itemizes against it.", penalty * 3))
    elif total:
        notes.append(_note("strength", "Mixed damage",
                           "Your best comp mixes physical and magic damage, so it's hard to itemize against.", 0.1))
    if features["range"] >= 0.4:
        notes.append(_note("strength", "Long range", "Ranged comps win teamfights (poke and kiting).", features["range"] / 2))
        notes.append(_note("weakness", "Vulnerable to dives", "Ranged comps lose small skirmishes to melee dive.",
                           features["range"] / 3))
    elif features["range"] <= -0.4:
        notes.append(_note("strength", "Strong dive", "Melee comps win small skirmishes.", -features["range"] / 2))
        notes.append(_note("weakness", "Weak in teamfights", "Melee comps lose 4v4 and 5v5 fights to ranged poke.",
                           -features["range"] / 3))
    if features["scaling"] >= 0.5:
        notes.append(_note("strength", "Late-game power", "Your pools peak in the late game.", features["scaling"] / 2))
        notes.append(_note("weakness", "Weak early game", "Late-game champions give up lane score early on.",
                           features["scaling"] / 3))
    elif features["scaling"] <= -0.5:
        notes.append(_note("strength", "Early-game power", "Your pools hit hardest before the late game.",
                           -features["scaling"] / 2))
        notes.append(_note("weakness", "Falls off late", "Early-game champions lose power in long games.",
                           -features["scaling"] / 3))
    if features["control"] <= -0.25:
        notes.append(_note("weakness", "Little crowd control", "Few stuns and little utility for fights.",
                           -features["control"] / 2))
    elif features["control"] >= 0.25:
        notes.append(_note("strength", "Plenty of crowd control", "Lots of stuns and utility in fights.", features["control"] / 2))
    return notes


def _setup_notes(styles: Sequence[str], focus: Sequence[str], coach: CoachSpec | None, suggested_styles: list[str],
                 suggested_focus: list[str], missing: list[str], config: dict) -> list[dict]:
    notes = []
    if missing:
        notes.append(_note("weakness", "Empty roster slots", f"No player for: {', '.join(LANE_LABEL[l] for l in missing)}.", 1))
    if coach is None:
        notes.append(_note("weakness", "No coach", "Choose a coach: their Synergy scales every playstyle and focus bonus.", 0.5))
    else:
        factor = 1 + (coach.synergy - 5) * config["coach"]["synergy_scale"]
        if abs(factor - 1) >= 0.04:
            notes.append(_note("strength" if factor > 1 else "weakness", f"Coach Synergy {coach.synergy}",
                               f"{coach.name} makes playstyle and focus bonuses {_pct(factor - 1)}.", factor - 1))
    if styles and styles[0] not in suggested_styles:
        notes.append(_note("weakness", "Playstyle doesn't suit the roster",
                           f"Your primary playstyle is {STYLE_LABEL.get(styles[0], styles[0])}; the roster suits "
                           f"{STYLE_LABEL[suggested_styles[0]]} better.", 0.3))
    lanes = [FOCUS_TO_LANE.get(f, f) for f in focus]
    if suggested_focus and lanes and lanes[0] not in suggested_focus:
        notes.append(_note("weakness", "Focus lane could be stronger",
                           f"Focusing {LANE_LABEL.get(lanes[0], lanes[0])} gains less than "
                           f"{LANE_LABEL[suggested_focus[0]]}.", 0.2))
    return notes


# ------------------------------------------------------------------ entry point
def analyse(roster: Mapping[str, PlayerSpec], styles: Sequence[str], focus: Sequence[str], coach: CoachSpec | None,
            champions: Mapping[int, Champion], table: MatchupTable, config: dict, typical_total: float) -> dict:
    """Notes on a (possibly incomplete) roster. `typical_total` is a typical player's stat total (the custom
    player budget), which strengths and weaknesses are measured against."""
    typical = typical_total / 5.0
    lanes = _lanes(roster, champions, config, typical)
    players = [x.player for x in lanes.values()]
    stats = {s: _avg([getattr(p, s) for p in players], typical) for s in STAT_NAMES}
    synergy = 1 + ((coach.synergy if coach else 5) - 5) * config["coach"]["synergy_scale"]
    missing = [l for l in LANES if l not in roster]

    scored = _search_comps(lanes, champions, table, config) if lanes else []
    if scored:
        best_picks, _, features = max(scored, key=lambda s: s[1])
        best_comp = [champions[c] for c in best_picks.values()]
    else:
        features, best_comp = {"scaling": 0.0, "range": 0.0, "control": 0.0, "mobility": 0.0}, []
    power = _avg([x.power for x in lanes.values()], 1.0)

    style_scores = _style_scores(stats, typical, power, features)
    suggested_styles = _pick_styles(style_scores)
    focus_rows, suggested_focus = _focus(lanes, synergy, config)
    order = suggested_styles + [s["style"] for s in style_scores if s["style"] not in suggested_styles]
    comps = _ideal_comps(scored, lanes, champions, config, order)

    notes = (_stat_notes(lanes, stats, typical, config) + _lane_notes(lanes, champions, config)
             + (_comp_notes(features, best_comp, config) if best_comp else [])
             + _setup_notes(styles, focus, coach, suggested_styles, suggested_focus, missing, config))
    strengths = sorted((n for n in notes if n["kind"] == "strength"), key=lambda n: -n["weight"])[:MAX_NOTES]
    weaknesses = sorted((n for n in notes if n["kind"] == "weakness"), key=lambda n: -n["weight"])[:MAX_NOTES]
    return {
        "filled": len(lanes),
        "stats": {s: round(v, 1) for s, v in stats.items()},
        "typical_stat": round(typical, 1),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "styles": style_scores,
        "suggested_styles": suggested_styles,
        "focus": focus_rows,
        "suggested_focus": suggested_focus,
        "comps": comps,
        "lanes": {l: {"player": x.player.name, "power": round(x.power, 2), "best": champions[x.best].name}
                  for l, x in lanes.items()},
    }
