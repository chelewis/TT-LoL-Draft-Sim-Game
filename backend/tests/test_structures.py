import pytest

from app.game.structures import STRUCTURE_LANES, TeamStructures


def test_eleven_towers():
    assert TeamStructures().total_towers == 11


def test_lane_chain_order():
    s = TeamStructures()
    kinds = [s.destroy_lane_structure("TOP") for _ in range(4)]
    assert kinds == ["tower", "tower", "tower", "inhibitor"]
    assert s.next_lane_structure("TOP") is None
    with pytest.raises(ValueError):
        s.destroy_lane_structure("TOP")


def test_nexus_locked_until_inhibitor_and_nexus_towers():
    s = TeamStructures()
    assert not s.nexus_towers_unlocked and not s.nexus_unlocked
    with pytest.raises(ValueError):
        s.destroy_nexus_tower()
    for _ in range(4):
        s.destroy_lane_structure("MID")
    assert s.nexus_towers_unlocked and not s.nexus_unlocked
    s.destroy_nexus_tower()
    assert not s.nexus_unlocked
    s.destroy_nexus_tower()
    assert s.nexus_unlocked and not s.nexus_towers_unlocked
    s.destroy_nexus()
    assert s.nexus_destroyed


def test_score_weights():
    s = TeamStructures()
    for _ in range(4):
        s.destroy_lane_structure("BOT")
    s.destroy_nexus_tower()
    assert s.score({"tower": 1, "inhibitor": 2, "nexus_tower": 2}) == 3 + 2 + 2
    assert set(STRUCTURE_LANES) == {"TOP", "MID", "BOT"}
