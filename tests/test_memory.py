"""Smoke tests for the durable memory store — the second place a silent failure is
most expensive. Verifies: a written fact survives a 'restart' (a fresh store reading
the same file); an edit sticks; a hand-edit to the file is respected; remove works;
a backup is left; and the agent injects facts as background knowledge."""
import json

import pytest

from memory import MemoryStore


def _store(tmp_path):
    return MemoryStore(path=tmp_path / "store.json")


def test_written_fact_survives_restart(tmp_path):
    s1 = _store(tmp_path)
    s1.remember("name", "Ewelina")
    # 'restart' = a brand-new process/object loading the same file.
    s2 = _store(tmp_path)
    assert s2.get("name") == "Ewelina"


def test_edit_sticks(tmp_path):
    s = _store(tmp_path)
    s.remember("coffee_order", "flat white")
    s.remember("coffee_order", "oat flat white")   # upsert = 'no, I meant ...'
    assert MemoryStore(path=tmp_path / "store.json").get("coffee_order") == "oat flat white"


def test_hand_edit_is_respected(tmp_path):
    p = tmp_path / "store.json"
    s = _store(tmp_path)
    s.remember("city", "Warsaw")
    # Hand-edit the human-readable file directly (emergency hatch).
    data = json.loads(p.read_text())
    data["city"] = "Kraków"                         # accepts the plain-string shape too
    p.write_text(json.dumps(data))
    assert MemoryStore(path=p).get("city") == "Kraków"


def test_forget_removes(tmp_path):
    s = _store(tmp_path)
    s.remember("temp", "delete me")
    s.forget("temp")
    assert MemoryStore(path=tmp_path / "store.json").get("temp") is None
    with pytest.raises(KeyError):
        s.forget("temp")                            # forgetting a missing key errors


def test_backup_left_on_overwrite(tmp_path):
    s = _store(tmp_path)
    s.remember("a", "1")
    s.remember("b", "2")                            # second write moves prior to .bak
    assert (tmp_path / "store.json.bak").exists()


def test_empty_and_missing_values_rejected(tmp_path):
    s = _store(tmp_path)
    with pytest.raises(ValueError):
        s.remember("", "x")
    with pytest.raises(ValueError):
        s.remember("k", "")


def test_corrupt_file_does_not_crash(tmp_path):
    p = tmp_path / "store.json"
    p.write_text("{ this is not json")
    s = MemoryStore(path=p)                          # must not raise
    assert s.all() == {}
    assert (tmp_path / "store.json.corrupt").exists()


def test_agent_injects_facts_as_data(tmp_path):
    from core.agent import Agent
    s = _store(tmp_path)
    s.remember("name", "Ewelina")
    agent = Agent(memory=s)
    sysprompt = agent._effective_system()
    assert "Ewelina" in sysprompt
    assert "not instructions" in sysprompt          # labelled as data, not commands
