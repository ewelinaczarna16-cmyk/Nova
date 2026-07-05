"""Heartbeat smoke tests (Tier 5). Cover the spec's verify points:
surfaces once, holds during quiet hours then delivers, a restart resumes the schedule
without refiring, items are dismissible, a still-running check is skipped, and a
consequential background action times out into a note instead of acting."""
from datetime import datetime

from heartbeat import (Check, HeartbeatState, Heartbeat, NotificationCenter, FakeChannel)
from heartbeat.checks import daily_digest
from tools import ToolRegistry
from tools.builtin import register_builtin_tools


def _epoch(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi).timestamp()


def _tools():
    reg = ToolRegistry(dry_run=False)
    register_builtin_tools(reg)
    return reg


def _hb(tmp_path, checks, channel=None, quiet=("22:00", "08:00"), approver=None):
    state = HeartbeatState(path=tmp_path / "state.json")
    channel = channel or FakeChannel()
    center = NotificationCenter(state=state, channel=channel,
                                quiet_start=quiet[0], quiet_end=quiet[1])
    hb = Heartbeat(checks, center, state, tools=_tools(),
                   approval_timeout=1, background_approver=approver, log=lambda *_: None)
    return hb, channel, state, center


def _digest_check(**kw):
    return Check(name="daily_digest", run=daily_digest, schedule=kw.get("schedule", {"at": "08:00"}))


def test_trigger_surfaces_once(tmp_path):
    hb, channel, _, _ = _hb(tmp_path, [_digest_check()])
    daytime = _epoch(2026, 1, 1, 9)          # outside quiet hours
    out = hb.trigger("daily_digest", now=daytime)
    assert out and "Morning" in out
    assert len(channel.sent) == 1            # exactly one text went out


def test_held_in_quiet_hours_then_delivered(tmp_path):
    hb, channel, _, center = _hb(tmp_path, [_digest_check()])
    night = _epoch(2026, 1, 1, 23)           # inside 22:00–08:00
    notice = center.surface("bedtime ping", now=night)
    assert notice["held"] and channel.sent == []      # held, NOT sent
    # later, out of quiet hours, the tick flushes it
    center.flush_held(now=_epoch(2026, 1, 2, 9))
    assert channel.sent == ["bedtime ping"]           # delivered, not lost


def test_restart_resumes_without_refiring(tmp_path):
    channel = FakeChannel()
    sched = {"every_seconds": 1000}
    hb1, _, state, _ = _hb(tmp_path, [_digest_check(schedule=sched)], channel=channel)
    t0 = _epoch(2026, 1, 1, 9)
    hb1.tick(now=t0)                          # first sight -> schedule forward, no fire
    assert channel.sent == []
    hb1.tick(now=t0 + 1001)                   # now due -> fires once
    assert len(channel.sent) == 1
    # "restart": brand-new objects, same state file on disk
    hb2, _, _, _ = _hb(tmp_path, [_digest_check(schedule=sched)], channel=channel)
    hb2.state = HeartbeatState(path=tmp_path / "state.json")
    hb2.center.state = hb2.state
    hb2.tick(now=t0 + 1002)                   # next_due is in the future -> no refire
    assert len(channel.sent) == 1


def test_dismiss_clears_item(tmp_path):
    hb, _, _, center = _hb(tmp_path, [_digest_check()])
    n = center.surface("something", now=_epoch(2026, 1, 1, 9))
    assert len(center.pending()) == 1
    assert center.dismiss(n["id"]) is True
    assert center.pending() == []


def test_still_running_check_is_skipped(tmp_path):
    hb, channel, state, _ = _hb(tmp_path, [_digest_check(schedule={"every_seconds": 1})])
    t0 = _epoch(2026, 1, 1, 9)
    state.set_next_due("daily_digest", t0 - 1)        # make it due
    hb._running.add("daily_digest")                   # pretend it's mid-run
    hb.tick(now=t0)
    assert channel.sent == []                         # skipped, not stacked


def test_consequential_background_action_times_out_to_note(tmp_path):
    did = {"ran": False}

    def risky_check(ctx):
        # A check that wants to do something consequential in the background.
        ctx.request_action("send the weekly email", consequential=True,
                           do_it=lambda: did.__setitem__("ran", True))
        return None

    check = Check(name="risky", run=risky_check, schedule={"every_seconds": 1})
    hb, channel, _, _ = _hb(tmp_path, [check], approver=None)   # no approver -> times out
    hb.trigger("risky", now=_epoch(2026, 1, 1, 9))
    assert did["ran"] is False                        # action did NOT run
    assert any("Skipped" in s for s in channel.sent)  # left a note instead
