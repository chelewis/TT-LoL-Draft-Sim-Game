"""CPU drafting: picks, bans and lane assignments scored with the simulation's own rules. Pure Python, no
framework or database imports.

A pick is scored by how much lane score the CPU's player would get from it (the lane phase formula without the
dice: player stats x champion synergy, comfort, strength fit, the off-role penalty, the matchup wheel, counter
and duo win rates and lane range, with an unknown lane opponent counted as average), times the champion's
scaling over the whole game (lane and fight phases, so late-game champions aren't judged on their lane alone),
compared with the best champion still available for that lane. It is then adjusted by team-level effects: same-team synergy, win rate
against the enemy picks, damage balance, range in teamfights vs skirmishes and the team's playstyle.

A ban goes on the champion whose loss hurts an enemy player most (the one that player gets the most from over
their next best option, in a lane the enemy still has to fill), less what the CPU's own players would lose.

Every term reads the live simulation config, so effects an admin has switched off are ignored here too.
"""
from __future__ import annotations

import random
from dataclasses import replace
from itertools import permutations
from typing import Mapping, Sequence

from .comfort import comfort_modifier, comfort_tier, off_role_multiplier
from .config import LANES
from .draft_engine import DraftState
from .lane_phase import champion_synergy, strength_fit
from .matchup import apply_coach_draft, lane_matchup
from .models import Champion, MatchupTable, PlayerSpec, TeamSetup
from .playstyle import adjust_comfort, effect_totals
from .range_waveclear import NEUTRAL, range_fight_multiplier, range_lane_multiplier
from .scaling import scaling_multiplier
from .state import damage_balance_penalty, damage_profile
from .win_rates import ally_delta, counter_delta, multiplier

BOT_LANE = ("BOT", "SUPPORT")
FIT_STATS = ("aggr", "aware", "pos", "dmg")

WEIGHTS = {
    "denial": 0.10,           # pick: bonus for taking a champion the enemy also wants (share of its value to them)
    "damage_balance": 0.6,    # pick: per unit of fight damage lost to a one-sided damage profile
    "style": 0.03,            # pick: per step of champion scaling towards the team's early / scaling style
    "jitter": 0.03,           # +/- random share of every score, so drafts vary
    "ban_drop": 2.0,          # ban: per unit of value the enemy player loses (vs their next best champion)
    "ban_counter": 1.0,       # ban: per unit of the champion's counter edge against the CPU's picks
    "ban_own_interest": 1.0,  # ban: share of the CPU's own loss taken off (a ban removes the champion for both teams)
}


# ------------------------------------------------------------------ the whole game
def _phase_weights(config: dict) -> dict[str, float]:
    """phase -> its share of the game: each fight phase by its expected number of fights, and the lane phase as
    much as an average fight phase (its lead carries into every fight)."""
    fights = {p["name"]: (sum(p["skirmishes"]) + sum(p["teamfights"])) / 2 for p in config["phases"]}
    weights = {"lane": sum(fights.values()) / len(fights) if fights else 1.0, **fights}
    total = sum(weights.values())
    return {phase: w / total for phase, w in weights.items()}


def game_scaling(champion: Champion, config: dict) -> float:
    """The champion's scaling multiplier over the whole game (the lane phase and every fight phase), not just
    the lane: a late-game champion gives up some lane score but is stronger in late fights."""
    return sum(w * scaling_multiplier(champion, phase, config) for phase, w in _phase_weights(config).items())


def _fight_sizes(config: dict) -> tuple[float, float]:
    """(4+, 3 or fewer): the expected share of fighting sides of each size, which decides whether range or
    melee has the edge (range wins teamfights, melee wins skirmishes)."""
    big = small = 0.0
    for p in config["phases"]:
        lo, hi = p["skirmish_size"]
        per_size = sum(p["skirmishes"]) / 2 / (hi - lo + 1)
        for n_att in range(lo, hi + 1):             # the defenders bring 1..n_att
            big += per_size * (n_att >= 4)
            small += per_size * (n_att < 4)
            big += per_size * sum(d >= 4 for d in range(1, n_att + 1)) / n_att
            small += per_size * sum(d < 4 for d in range(1, n_att + 1)) / n_att
        lo, hi = p["teamfight_size"]
        sides = sum(p["teamfights"])                  # two sides per fight, each lo..hi
        big += sides * sum(n >= 4 for n in range(lo, hi + 1)) / (hi - lo + 1)
        small += sides * sum(n < 4 for n in range(lo, hi + 1)) / (hi - lo + 1)
    total = big + small
    return (big / total, small / total) if total else (0.5, 0.5)


# ------------------------------------------------------------------ lane value
def lane_fit(player: PlayerSpec, champion: Champion, config: dict, lane: str | None = None) -> float:
    """The lane phase's base score for this player on this champion in `lane` (default: the player's role),
    without the rolls: stats x champion synergy, x (1 + comfort) including playstyle pool hooks, x the player's
    lane_score tag, x strength fit, x the off-role penalty."""
    weights = champion_synergy(champion, config)
    base = sum(getattr(player, stat) * weights[stat] for stat in FIT_STATS)
    tags = effect_totals(player)
    tier = comfort_tier(player, champion.id, config)
    comfort = adjust_comfort(comfort_modifier(tier, config), tier, tags)
    return (base * (1.0 + comfort) * (1.0 + tags.get("lane_score", 0.0)) * strength_fit(player, champion, config)
            * off_role_multiplier(champion, lane or player.role, player, config))


class _Fits:
    """Cached lane_fit values (a draft evaluates the same player/champion/lane many times)."""

    def __init__(self, config: dict):
        self.config = config
        self._cache: dict[tuple[int, int, str], float] = {}

    def __call__(self, player: PlayerSpec, champion: Champion, lane: str) -> float:
        key = (player.id, champion.id, lane)
        if key not in self._cache:
            self._cache[key] = lane_fit(player, champion, self.config, lane)
        return self._cache[key]


def assign_lanes(picks: Sequence[int], roster: Mapping[str, PlayerSpec], champions: Mapping[int, Champion],
                 config: dict, fits: _Fits | None = None) -> dict[str, int]:
    """lane -> champion id: the lanes that give these picks the highest total lane value with this roster.
    With fewer picks than lanes, only that many lanes are filled (the rest are still open), and each lane's value
    is taken as a share of its player's best possible champion, so a strong player's lane doesn't soak up every
    pick."""
    fits = fits or _Fits(config)
    picks = [cid for cid in picks if cid in champions][:len(LANES)]
    lanes = [lane for lane in LANES if lane in roster]

    def value(lane: str, cid: int) -> float:
        return fits(roster[lane], champions[cid], lane) * game_scaling(champions[cid], config)

    scale = {lane: 1.0 for lane in lanes}
    if len(picks) < len(lanes):
        for lane in lanes:
            top = max(value(lane, cid) for cid in champions)
            scale[lane] = 1.0 / top if top > 0 else 1.0
    best, best_total = {}, float("-inf")
    for chosen in permutations(lanes, len(picks)):
        total = sum(value(lane, cid) * scale[lane] for lane, cid in zip(chosen, picks))
        if total > best_total:
            best, best_total = dict(zip(chosen, picks)), total
    return best


# ------------------------------------------------------------------ the draft
class _View:
    """One team's side of the draft: its setup, its picks and the lanes they fill."""

    def __init__(self, setup: TeamSetup, picks: list[int], champions: Mapping[int, Champion], config: dict,
                 fits: _Fits):
        self.setup = setup
        self.picks = [cid for cid in picks if cid in champions]
        self.lanes = assign_lanes(self.picks, setup.roster, champions, config, fits)
        self.open = [lane for lane in LANES if lane not in self.lanes and lane in setup.roster] or list(LANES)


def _lane_value(champion: Champion, lane: str, me: _View, them: _View, champions: Mapping[int, Champion],
                table: MatchupTable, config: dict, fits: _Fits) -> float:
    """The lane score `me`'s player in `lane` would get from `champion` against `them`'s known picks."""
    value = fits(me.setup.roster[lane], champion, lane) * game_scaling(champion, config)
    opponent = them.lanes.get(lane)
    if opponent is not None:     # the matchup wheel: the lane winner's multiplier, scaled by its coach's Draft
        mult, enemy_mult, _ = lane_matchup(champion, champions[opponent], config)
        value *= apply_coach_draft(mult, me.setup.coach.draft, config)
        value /= apply_coach_draft(enemy_mult, them.setup.coach.draft, config)
    lanes = BOT_LANE if lane in BOT_LANE else (lane,)
    opponents = [them.lanes[l] for l in lanes if l in them.lanes]
    if opponents:
        value *= multiplier(counter_delta([champion.id], opponents, table, config),
                            config["win_rates"]["lane_counter_scale"], config)
    partner = me.lanes.get("SUPPORT" if lane == "BOT" else "BOT") if lane in BOT_LANE else None
    if lane != "JUNGLE":         # range: the duo's average in the bot lane; an unknown opponent counts as average
        mine = [champion] + ([champions[partner]] if partner is not None else [])
        value *= range_lane_multiplier(mine, [champions[c] for c in opponents], config)
    if partner is not None:
        value *= multiplier(ally_delta([champion.id, partner], table, config),
                            config["win_rates"]["lane_duo_scale"], config)
    return value


def _lane_values(candidates: list[Champion], me: _View, them: _View, champions, table, config, fits
                 ) -> dict[str, dict[int, float]]:
    """open lane -> champion id -> lane value, for every candidate in every lane `me` still has to fill."""
    return {lane: {c.id: _lane_value(c, lane, me, them, champions, table, config, fits) for c in candidates}
            for lane in me.open}


def _relative(values: dict[str, dict[int, float]]) -> dict[int, float]:
    """champion id -> best share of the top value in any open lane (1.0 = the best option for some lane)."""
    out: dict[int, float] = {}
    for by_champ in values.values():
        top = max(by_champ.values(), default=0.0)
        if top <= 0:
            continue
        for cid, v in by_champ.items():
            out[cid] = max(out.get(cid, 0.0), v / top)
    return out


def _team_bonus(champion: Champion, me: _View, them: _View, champions, table, config) -> float:
    """Fractional bonus (or penalty) from team-level effects of adding `champion` to `me`."""
    wr = config["win_rates"]
    bonus = 0.0
    if me.picks:
        bonus += multiplier(ally_delta(me.picks + [champion.id], table, config), wr["fight_synergy_scale"], config) - 1
    if them.picks:
        bonus += multiplier(counter_delta([champion.id], them.picks, table, config), wr["fight_counter_scale"], config) - 1
    comp = [champions[c] for c in me.picks] + [champion]
    if len(me.picks) >= 2:       # the damage mix only means something once a few champions are in
        bonus -= WEIGHTS["damage_balance"] * damage_balance_penalty(damage_profile(comp), config)
    # range in fights: teamfights favour range, skirmishes melee. Comps not picked yet are filled with
    # average-range champions, so each champion moves the team's average by its fifth.
    average = replace(champion, attack_range=NEUTRAL)
    full = comp + [average] * (len(LANES) - len(comp))
    enemy = [champions[c] for c in them.picks]
    enemy += [average] * (len(LANES) - len(enemy))
    big, small = _fight_sizes(config)
    bonus += big * (range_fight_multiplier(full, enemy, 5, config) - 1)
    bonus += small * (range_fight_multiplier(full, enemy, 3, config) - 1)
    styles = me.setup.styles
    if config["team_style"]["enabled"]:
        if "early" in styles:
            bonus += WEIGHTS["style"] * (2 - champion.scaling)
        if "scaling" in styles:
            bonus += WEIGHTS["style"] * (champion.scaling - 2)
    return bonus


def _jitter(rng: random.Random) -> float:
    return 1.0 + rng.uniform(-WEIGHTS["jitter"], WEIGHTS["jitter"])


def _choose_pick(candidates, me, them, champions, table, config, fits, rng) -> int:
    mine = _relative(_lane_values(candidates, me, them, champions, table, config, fits))
    theirs = _relative(_lane_values(candidates, them, me, champions, table, config, fits))

    def score(c: Champion) -> float:
        value = mine.get(c.id, 0.0) * (1.0 + _team_bonus(c, me, them, champions, table, config))
        value += WEIGHTS["denial"] * theirs.get(c.id, 0.0)
        return value * _jitter(rng)

    return max(candidates, key=score).id


def _ban_loss(values: dict[str, dict[int, float]]) -> dict[int, float]:
    """champion id -> how much a team loses if it is banned: its best share of the top value in any open lane,
    plus the gap to the next best option when it is that lane's top champion."""
    loss: dict[int, float] = {}
    for by_champ in values.values():
        ranked = sorted(by_champ.items(), key=lambda kv: -kv[1])
        top = ranked[0][1] if ranked else 0.0
        if top <= 0:
            continue
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        for i, (cid, v) in enumerate(ranked):
            drop = (v - second) / top if i == 0 else 0.0     # only the lane's top champion leaves a gap when banned
            loss[cid] = max(loss.get(cid, 0.0), v / top + WEIGHTS["ban_drop"] * drop)
    return loss


def _choose_ban(candidates, me, them, champions, table, config, fits, rng) -> int:
    # A ban takes the champion from both teams, so it is worth what the enemy loses minus what the CPU loses.
    # (In a mirror match, the same team on both sides, banning a shared favourite gains nothing.)
    threat = _ban_loss(_lane_values(candidates, them, me, champions, table, config, fits))
    own = _ban_loss(_lane_values(candidates, me, them, champions, table, config, fits))
    wr = config["win_rates"]

    def score(c: Champion) -> float:
        value = threat.get(c.id, 0.0) - WEIGHTS["ban_own_interest"] * own.get(c.id, 0.0)
        if me.picks:
            value += WEIGHTS["ban_counter"] * (multiplier(counter_delta([c.id], me.picks, table, config),
                                                          wr["fight_counter_scale"], config) - 1)
        return value * _jitter(rng) + rng.uniform(0, 1e-6)     # ties (a mirror's first ban) go to a random one

    return max(candidates, key=score).id


def choose(draft: DraftState, own: TeamSetup, enemy: TeamSetup, champions: Mapping[int, Champion],
           table: MatchupTable, config: dict, rng: random.Random) -> int:
    """The champion the CPU picks or bans for the draft's current action (the CPU is the side whose turn it is).
    Always a legal choice: one of draft.available()."""
    action = draft.current
    if action is None:
        raise ValueError("The draft is already complete.")
    available = draft.available()
    candidates = [champions[cid] for cid in available if cid in champions]
    if not candidates:
        return rng.choice(available)
    enemy_side = "RED" if action.team == "BLUE" else "BLUE"
    fits = _Fits(config)
    me = _View(own, draft.picks[action.team], champions, config, fits)
    them = _View(enemy, draft.picks[enemy_side], champions, config, fits)
    if action.action_type == "PICK":
        return _choose_pick(candidates, me, them, champions, table, config, fits, rng)
    return _choose_ban(candidates, me, them, champions, table, config, fits, rng)
