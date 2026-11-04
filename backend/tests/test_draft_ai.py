"""The CPU drafter (game/draft_ai.py): legal choices that follow the simulation's rules."""
import dataclasses
import random

from app.data.loader import seed_team_setup
from app.game import draft_ai
from app.game.config import DRAFT_CONFIG, LANES, simulation_config
from app.game.draft_engine import new_draft
from app.game.models import MatchupTable
from app.game.simulation_engine import simulate_match

CFG = simulation_config()
TABLE = MatchupTable()


def teams(seed, blue_id=1, red_id=2):
    # the lineup is filled in after the draft; any placeholder works for the setup
    placeholder = dict(zip(LANES, range(1, 6)))
    return seed_team_setup(seed, blue_id, placeholder), seed_team_setup(seed, red_id, placeholder)


def cpu_draft(seed, champions, blue, red, rng, locked=(), actions=None, random_side=None):
    """Draft with the CPU on both sides (or a random drafter on `random_side`)."""
    draft = new_draft(actions or DRAFT_CONFIG["actions"], champions, locked)
    setups = {"BLUE": blue, "RED": red}
    while not draft.complete:
        side = draft.current.team
        if side == random_side:
            cid = rng.choice(draft.available())
        else:
            cid = draft_ai.choose(draft, setups[side], setups["RED" if side == "BLUE" else "BLUE"],
                                  champions, TABLE, CFG, rng)
        draft.apply(side, draft.current.action_type, cid)
    return draft


def test_every_choice_is_legal_including_fearless_locks(seed, champions):
    blue, red = teams(seed)
    locked = set(list(champions)[:30])
    draft = cpu_draft(seed, champions, blue, red, random.Random(1), locked=locked)
    used = [c for _, c in draft.bans] + draft.picks["BLUE"] + draft.picks["RED"]
    assert len(used) == len(set(used)) == 20
    assert not set(used) & locked


def test_first_ban_takes_away_an_enemy_pool_champion(seed, champions):
    blue, red = teams(seed)
    draft = new_draft(DRAFT_CONFIG["actions"], champions)
    banned = draft_ai.choose(draft, blue, red, champions, TABLE, CFG, random.Random(2))
    enemy_pools = {cid for p in red.roster.values() for cid in p.pool}
    assert banned in enemy_pools


def test_in_a_mirror_match_the_cpu_does_not_ban_its_own_players_favourites(seed, champions):
    """Same team on both sides: the enemy's best champions are the CPU's too, so banning them gains nothing."""
    team, _ = teams(seed)
    best = {p.pool[0] for p in team.roster.values()}
    draft = new_draft(DRAFT_CONFIG["actions"], champions)
    first_bans = {draft_ai.choose(draft, team, team, champions, TABLE, CFG, random.Random(s)) for s in range(5)}
    assert not first_bans & best
    assert len(first_bans) > 1                       # not always the first champion in the list


def test_first_pick_suits_one_of_its_own_players(seed, champions):
    blue, red = teams(seed)
    draft = new_draft([a for a in DRAFT_CONFIG["actions"] if a.endswith("PICK")], champions)
    pick = draft_ai.choose(draft, blue, red, champions, TABLE, CFG, random.Random(3))
    best_for_lane = {}
    for lane, player in blue.roster.items():
        ranked = sorted(champions.values(), key=lambda c: -draft_ai.lane_fit(player, c, CFG))
        best_for_lane[lane] = {c.id for c in ranked[:5]}
    assert any(pick in ids for ids in best_for_lane.values())


def test_assign_lanes_puts_each_player_on_their_best_champion(seed, champions):
    blue, _ = teams(seed)
    picks = [blue.roster[lane].pool[0] for lane in reversed(LANES)]     # pick order says nothing about lanes
    if len(set(picks)) < 5:
        return
    lanes = draft_ai.assign_lanes(picks, blue.roster, champions, CFG)
    assert set(lanes) == set(LANES)
    assert all(lanes[lane] == blue.roster[lane].pool[0] for lane in LANES)


def test_partial_picks_leave_lanes_open(seed, champions):
    blue, _ = teams(seed)
    lanes = draft_ai.assign_lanes([blue.roster["MID"].pool[0]], blue.roster, champions, CFG)
    assert list(lanes) == ["MID"]


def test_damage_balance_favours_the_missing_damage_type(seed, champions):
    blue, red = teams(seed)
    physical = [c.id for c in champions.values() if c.damage_type == "P"]
    magic = next(c for c in champions.values() if c.damage_type == "M")
    twin = dataclasses.replace(magic, id=-1, damage_type="P")      # same champion, physical damage
    pool = {**champions, -1: twin}
    me = draft_ai._View(blue, physical[:3], pool, CFG, draft_ai._Fits(CFG))
    them = draft_ai._View(red, [], pool, CFG, draft_ai._Fits(CFG))
    assert draft_ai._team_bonus(magic, me, them, pool, TABLE, CFG) > draft_ai._team_bonus(twin, me, them, pool, TABLE, CFG)


def test_late_game_champions_are_valued_over_the_whole_game_not_just_the_lane(champions):
    late = next(c for c in champions.values() if c.scaling == 3)
    early = dataclasses.replace(late, scaling=1)
    # the lane alone favours the early twin; over the whole game the gap is smaller
    lane_gap = draft_ai.scaling_multiplier(early, "lane", CFG) / draft_ai.scaling_multiplier(late, "lane", CFG)
    assert draft_ai.game_scaling(early, CFG) / draft_ai.game_scaling(late, CFG) < lane_gap


def test_range_counts_before_the_lane_opponent_is_known(seed, champions):
    blue, red = teams(seed)
    ranged = next(c for c in champions.values() if c.attack_range == 3)
    melee = dataclasses.replace(ranged, id=-1, attack_range=1)     # same champion, melee
    pool = {**champions, -1: melee}
    me = draft_ai._View(blue, [], pool, CFG, draft_ai._Fits(CFG))
    them = draft_ai._View(red, [], pool, CFG, draft_ai._Fits(CFG))
    value = lambda c: draft_ai._lane_value(c, "BOT", me, them, pool, TABLE, CFG, draft_ai._Fits(CFG))
    assert value(ranged) > value(melee)
    off = simulation_config({"range": {"enabled": False}})
    assert draft_ai._lane_value(ranged, "BOT", me, them, pool, TABLE, off, draft_ai._Fits(off)) == \
        draft_ai._lane_value(melee, "BOT", me, them, pool, TABLE, off, draft_ai._Fits(off))


def test_the_cpu_prefers_a_champion_in_its_usual_role(seed, champions):
    """Two identical champions, one usual in the open lane and one not: the CPU takes the on-role one."""
    blue, red = teams(seed)
    pools = {cid for p in blue.roster.values() for cid in p.pool}
    base = next(c for c in champions.values() if c.id not in pools)
    on = dataclasses.replace(base, id=-1, roles=("BOT", "SUPPORT"))
    off = dataclasses.replace(base, id=-2, roles=("JUNGLE", "TOP"))
    pool = {**champions, -1: on, -2: off}
    fits = draft_ai._Fits(CFG)
    me = draft_ai._View(blue, [], pool, CFG, fits)
    them = draft_ai._View(red, [], pool, CFG, fits)
    value = lambda c: draft_ai._lane_value(c, "BOT", me, them, pool, TABLE, CFG, fits)
    assert value(on) > value(off)
    assert abs(value(off) / value(on) - (1 - CFG["off_role"]["lane_penalty"])) < 1e-9
    # and the final lineup puts each in its usual lane when the fits are otherwise equal
    jungle = dataclasses.replace(base, id=-3, roles=("JUNGLE",))
    lanes = draft_ai.assign_lanes([-3, -1], blue.roster, {**pool, -3: jungle}, CFG)
    assert lanes.get("BOT", lanes.get("SUPPORT")) == -1 and lanes.get("JUNGLE", lanes.get("TOP")) == -3


def test_the_damage_term_is_off_when_the_setting_is(seed, champions):
    cfg = simulation_config({"damage_balance": {"enabled": False}})
    blue, red = teams(seed)
    physical = [c.id for c in champions.values() if c.damage_type == "P"]
    magic = next(c for c in champions.values() if c.damage_type == "M")
    twin = dataclasses.replace(magic, id=-1, damage_type="P")
    pool = {**champions, -1: twin}
    me = draft_ai._View(blue, physical[:3], pool, cfg, draft_ai._Fits(cfg))
    them = draft_ai._View(red, [], pool, cfg, draft_ai._Fits(cfg))
    assert draft_ai._team_bonus(magic, me, them, pool, TABLE, cfg) == draft_ai._team_bonus(twin, me, them, pool, TABLE, cfg)


def test_cpu_drafts_beat_random_drafts(seed, champions):
    """Same teams, same lane assignment logic: only the draft differs, so the CPU should win most games."""
    rng = random.Random(7)
    wins = games = 0
    for trial in range(24):        # ~89% over 100 games when measured; 24 keeps the suite quick
        # the two seed teams with rosters; each plays each side, as CPU and as the random drafter
        blue, red = teams(seed, 1, 2) if trial % 4 < 2 else teams(seed, 2, 1)
        cpu = "BLUE" if trial % 2 == 0 else "RED"
        rand = "RED" if cpu == "BLUE" else "BLUE"
        draft = cpu_draft(seed, champions, blue, red, rng, random_side=rand)
        setups = {}
        for side, setup in (("BLUE", blue), ("RED", red)):
            lineup = draft_ai.assign_lanes(draft.picks[side], setup.roster, champions, CFG)
            setups[side] = dataclasses.replace(setup, lineup=lineup)
        result = simulate_match(setups["BLUE"], setups["RED"], champions, trial, CFG, TABLE)
        wins += result.winner == cpu
        games += 1
    assert wins / games > 0.6, f"CPU won {wins}/{games}"
