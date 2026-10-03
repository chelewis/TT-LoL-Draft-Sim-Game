import random

import pytest

from app.game.config import DRAFT_CONFIG
from app.game.draft_engine import DraftError, new_draft, rebuild_draft

IDS = range(1, 41)


def draft():
    return new_draft(DRAFT_CONFIG["actions"], IDS)


def test_sequence_has_ten_bans_and_ten_picks():
    d = draft()
    kinds = [a.action_type for a in d.sequence]
    assert kinds.count("BAN") == 10 and kinds.count("PICK") == 10
    assert [a.team for a in d.sequence if a.action_type == "PICK"].count("BLUE") == 5


def test_only_active_team_can_act():
    with pytest.raises(DraftError, match="not your turn"):
        draft().apply("RED", "BAN", 1)


def test_wrong_action_type_rejected():
    with pytest.raises(DraftError, match="ban"):
        draft().apply("BLUE", "PICK", 1)


def test_duplicate_and_banned_champions_rejected():
    d = draft()
    d.apply("BLUE", "BAN", 1)
    with pytest.raises(DraftError, match="already"):
        d.apply("RED", "BAN", 1)


def test_unknown_champion_rejected():
    with pytest.raises(DraftError, match="Unknown"):
        draft().apply("BLUE", "BAN", 9999)


def test_full_draft_completes_with_five_each():
    d = draft()
    ids = iter(IDS)
    while not d.complete:
        a = d.current
        d.apply(a.team, a.action_type, next(ids))
    assert len(d.picks["BLUE"]) == 5 and len(d.picks["RED"]) == 5 and len(d.bans) == 10
    with pytest.raises(DraftError, match="complete"):
        d.apply("BLUE", "BAN", 40)


def test_banned_champion_cannot_be_picked():
    d = draft()
    ids = iter(IDS)
    for _ in range(6):   # the six opening bans
        a = d.current
        d.apply(a.team, a.action_type, next(ids))
    with pytest.raises(DraftError, match="already"):
        d.apply("BLUE", "PICK", 1)


def test_auto_action_is_legal_and_deterministic():
    d1, d2 = draft(), draft()
    for d in (d1, d2):
        rng = random.Random(7)
        while not d.complete:
            d.auto_action(rng)
    assert d1.history == d2.history
    assert len(d1.used) == 20 and all(h[4] for h in d1.history)


def test_rebuild_from_history():
    d = draft()
    rng = random.Random(3)
    for _ in range(6):
        d.auto_action(rng)
    rebuilt = rebuild_draft(DRAFT_CONFIG["actions"], IDS, [(t, k, c, a) for _, t, k, c, a in d.history])
    assert rebuilt.bans == d.bans and rebuilt.cursor == d.cursor
