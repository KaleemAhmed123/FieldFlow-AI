"""The Toolbox: read dispatch, action refusal with a reason, atomic reserve (NFR-5), and the
decision trace composed from real read tools. In-memory SQLite + fakes, no infra."""

from __future__ import annotations

from app.db.models import Case
from app.services import case_service
from fieldflow_contract import make_event
from sqlalchemy import select


# --- Read tools: safe lookups return data -------------------------------------------------
def test_read_tool_returns_data(toolbox):
    res = toolbox.call("salesforce.get_asset", assetId="AST-1")
    assert res.ok
    assert res.data["model"].startswith("Daikin")


def test_unknown_tool_is_refused_not_raised(toolbox):
    res = toolbox.call("salesforce.get_spaceship", craftId="X")
    assert not res.ok and "unknown tool" in res.reason


def test_missing_arg_is_refused(toolbox):
    res = toolbox.call("salesforce.get_asset")  # no assetId
    assert not res.ok and "missing args" in res.reason


# --- Action tools: the function decides, and refuses an illegal call with a reason ---------
def test_reserve_action_refuses_when_stock_gone(toolbox, inventory):
    inventory.set_stock("CAP-492", 0)  # another case grabbed the part
    res = toolbox.call("inventory.reserve", partNo="CAP-492", qty=1)
    assert not res.ok
    assert "no stock" in res.reason


def test_reserve_action_is_atomic(toolbox, inventory):
    inventory.set_stock("CAP-492", 1)
    first = toolbox.call("inventory.reserve", partNo="CAP-492", qty=1)
    second = toolbox.call("inventory.reserve", partNo="CAP-492", qty=1)
    assert first.ok and not second.ok  # one holds it, the other is refused — no oversell


def test_reschedule_confirm_refuses_unknown_appointment(toolbox):
    res = toolbox.call("reschedule.confirm", appointmentId="SA-NOPE", slotId="t-today-1")
    assert not res.ok and "unknown appointment" in res.reason


def test_reschedule_confirm_executes_on_valid_appointment(toolbox):
    res = toolbox.call("reschedule.confirm", appointmentId="SA-19281", slotId="t-today-1")
    assert res.ok and res.data["status"] == "RESCHEDULED"


# --- describe(): the controlled surface, kinds intact --------------------------------------
def test_describe_lists_reads_and_actions(toolbox):
    surface = {t["name"]: t["kind"] for t in toolbox.describe()}
    assert surface["salesforce.get_asset"] == "read"
    assert surface["inventory.reserve"] == "action"
    assert surface["reschedule.confirm"] == "action"


# --- Context is composed via read tools, and toolsUsed reflects the real calls -------------
async def _case(sessionmaker, cid: str) -> Case:
    async with sessionmaker() as s:
        return (await s.execute(select(Case).where(Case.correlation_id == cid))).scalar_one()


async def test_context_composed_from_read_tools_and_toolsused_is_real(sessionmaker, graph):
    event = make_event(work_order_id="WO-TOOLS", reason="technician_delay")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)

    case = await _case(sessionmaker, "WO-TOOLS")
    # Context was assembled from the four granular Salesforce reads.
    assert case.context["customer"]["name"] == "Kaleem Ahmed"
    assert case.context["asset"]["model"].startswith("Daikin")
    assert case.context["technician"]["skills"] == ["daikin-inverter"]
    # toolsUsed is the real composition — no hard-coded list, no find_part (no part needed here).
    assert case.decision_trace["toolsUsed"] == [
        "salesforce.get_appointment", "salesforce.get_customer",
        "salesforce.get_asset", "salesforce.get_technician",
    ]


async def test_toolsused_includes_find_part_when_a_part_is_needed(sessionmaker, graph):
    event = make_event(work_order_id="WO-TOOLS-PART", reason="part_missing")
    async with sessionmaker() as s:
        await case_service.handle_event(s, event, graph=graph)

    case = await _case(sessionmaker, "WO-TOOLS-PART")
    assert "inventory.find_part" in case.decision_trace["toolsUsed"]
