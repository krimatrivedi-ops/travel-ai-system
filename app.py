import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from runtime.orchestrator import Orchestrator
from agents.replanner_agent import ReplannerAgent
from agents.optimization_agent import OptimizationAgent
from agents.decision_agent import DecisionAgent
from runtime.engine import ReactiveEngine
from state.store import get_state, update_state, reset_state
from events.event_bus import EventType
from services.preference_llm import process_turn
from services.osm_service import fetch_optimization_candidates
from services.pricing_service import enrich_itinerary_pricing
from core.itinerary_schema import (
    finalize_edited_bundle,
    itinerary_has_content,
    validate_edited_itinerary_bundle,
)
from core.optimization_merge import apply_recommendation_to_bundle
from core.preference_schema import merge_trip_snapshot_with_partial
from services.itinerary_store import (
    get_saved_itinerary,
    init_store,
    list_saved_itinerary_summaries,
    save_generated_itinerary,
    update_saved_itinerary_after_replan,
    update_saved_itinerary_bundle,
)
from services.pdf_export import build_itinerary_pdf_bytes, pdf_attachment_filename
from routes.pricing import router as pricing_router
from utils.util import clean_cost, safe_float

logger = logging.getLogger(__name__)

app = FastAPI(title="Travel AI System API")
app.include_router(pricing_router)

# Initialize engine
engine = ReactiveEngine(Orchestrator(), ReplannerAgent())
optimization_agent = OptimizationAgent()
decision_agent = DecisionAgent()


def persona_for_pricing(saved_itinerary_id: Optional[str] = None) -> Dict[str, Any]:
    """Merge session persona with saved-trip snapshot when editing a stored itinerary."""
    st = get_state()
    persona: Dict[str, Any] = dict(st.persona or {})
    if saved_itinerary_id:
        sid = saved_itinerary_id.strip()
        if sid:
            row = get_saved_itinerary(sid)
            if row and isinstance(row.get("persona_snapshot"), dict):
                persona = {**persona, **row["persona_snapshot"]}
    return persona


@app.on_event("startup")
def _startup_init_db() -> None:
    init_store()

class PlanInput(BaseModel):
    user_input: str
    saved_itinerary_id: Optional[str] = None


class ConversationMessage(BaseModel):
    message: str
    saved_itinerary_id: Optional[str] = None

class EventInput(BaseModel):
    event_type: str
    payload: Dict[str, Any]


class ItineraryReplaceBody(BaseModel):
    itinerary: Dict[str, Any]


class SavedItineraryBundleBody(BaseModel):
    itinerary_bundle: Dict[str, Any]


class OptimizeInput(BaseModel):
    user_request: str
    itinerary_bundle: Optional[Dict[str, Any]] = None
    persona: Optional[Dict[str, Any]] = None
    destination: Optional[str] = None


class OptimizeApplyInput(BaseModel):
    itinerary_bundle: Dict[str, Any]
    selected_recommendation_index: int
    optimization_snapshot: Dict[str, Any]
    saved_itinerary_id: Optional[str] = None
    target_day_index: Optional[int] = None
    target_segment_index: Optional[int] = None


class EvaluateDecisionInput(BaseModel):
    user_request: str
    current_itinerary: List[Dict[str, Any]]
    proposed_change: Dict[str, str]
    impact_analysis: Dict[str, Any]
    updated_itinerary: List[Dict[str, Any]]


def _handle_conversation_message(
    message: str, saved_itinerary_id: Optional[str] = None
) -> Dict[str, Any]:
    """Multi-turn preference collection; generates itinerary only when complete."""
    text = (message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message is required")

    snapshot: Optional[Dict[str, Any]] = None
    if saved_itinerary_id:
        sid = saved_itinerary_id.strip()
        if not sid:
            raise HTTPException(status_code=400, detail="saved_itinerary_id is empty")
        row = get_saved_itinerary(sid)
        if not row:
            raise HTTPException(status_code=404, detail="saved itinerary not found")
        snapshot = row.get("persona_snapshot") if isinstance(row.get("persona_snapshot"), dict) else {}

    msgs = list(get_state().conversation_messages)
    session_partial = dict(get_state().partial_persona)
    partial = merge_trip_snapshot_with_partial(snapshot, session_partial)
    msgs.append({"role": "user", "content": text})

    updated, complete, nq = process_turn(msgs, partial)
    merged = merge_trip_snapshot_with_partial(snapshot, updated)

    scope = "trip_saved" if saved_itinerary_id else "session"

    if not complete:
        msgs.append(
            {
                "role": "assistant",
                "content": nq or "Could you share a bit more about your trip?",
            }
        )
        update_state(
            {
                "conversation_phase": "collecting_preferences",
                "partial_persona": merged,
                "conversation_messages": msgs,
                "pending_question": nq,
            }
        )
        return {
            "status": "need_more",
            "question": nq,
            "partial_persona": merged,
            "conversation_phase": "collecting_preferences",
            "preference_scope": scope,
            "replan_from_saved": bool(saved_itinerary_id),
        }

    result = engine.generate_from_structured_persona(merged, text)
    itin = result.get("current_itinerary")
    fail_code = result.get("failure")

    if not result.get("success") or not itinerary_has_content(itin):
        if fail_code == "overpass_unavailable":
            fail_q = (
                "The public map service timed out (this happens when their servers are busy). "
                "Your trip details are saved — please press **Send** again in a few seconds to retry, "
                "or try again in a minute."
            )
        elif fail_code == "planner_failed":
            fail_q = (
                "We found places on the map but couldn’t finish building the plan. "
                "Press **Send** once more to retry generation."
            )
        else:
            fail_q = (
                "We couldn’t find enough named places for that area in our map data. "
                "Please reply with a **specific city** you’ll stay in (e.g. Kathmandu instead of Nepal), "
                "and we’ll generate your itinerary again."
            )
        msgs.append({"role": "assistant", "content": fail_q})
        update_state(
            {
                "conversation_messages": msgs,
                "partial_persona": merged,
                "pending_question": fail_q,
                "conversation_phase": "collecting_preferences",
            }
        )
        return {
            "status": "need_more",
            "question": fail_q,
            "failure": fail_code,
            "partial_persona": merged,
            "conversation_phase": "collecting_preferences",
            "current_itinerary": itin,
            "persona": get_state().persona,
            "preference_scope": scope,
            "replan_from_saved": bool(saved_itinerary_id),
        }

    dest = updated.get("destination", "your destination")
    dur = updated.get("trip_duration", "")
    ack = f"Thanks — your itinerary for {dest}"
    if dur:
        ack += f" ({dur})"
    ack += " is ready on the right."
    msgs.append({"role": "assistant", "content": ack})
    update_state(
        {
            "conversation_messages": msgs,
            "partial_persona": get_state().persona,
            "pending_question": None,
        }
    )
    persona_out = result.get("persona") or {}
    if saved_itinerary_id:
        update_saved_itinerary_after_replan(saved_itinerary_id.strip(), persona_out, itin)
        saved_id = saved_itinerary_id.strip()
    else:
        saved_id = save_generated_itinerary(persona_out, itin)
    return {
        "status": "generated",
        "question": None,
        "partial_persona": get_state().persona,
        "conversation_phase": "generated",
        "current_itinerary": itin,
        "persona": persona_out,
        "saved_itinerary_id": saved_id,
        "preference_scope": scope,
        "replan_from_saved": bool(saved_itinerary_id),
    }

@app.get("/", response_class=FileResponse)
async def read_index():
    return "ui/index.html"

@app.post("/plan")
async def plan_trip(input: PlanInput):
    """Send a travel message through the preference flow (same as POST /conversation/message)."""
    try:
        return _handle_conversation_message(
            input.user_input, saved_itinerary_id=input.saved_itinerary_id
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversation/message")
async def conversation_message(body: ConversationMessage):
    """Continue or complete preference collection; itinerary is generated when prefs are complete."""
    try:
        return _handle_conversation_message(
            body.message, saved_itinerary_id=body.saved_itinerary_id
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversation/reset")
async def conversation_reset():
    """Clear session for a new trip request."""
    reset_state()
    return {"ok": True, "conversation_phase": "idle"}

@app.post("/event/simulate")
async def simulate_event(input: EventInput):
    """Simulates an external event (weather, edit, etc.)."""
    try:
        # Map input string to EventType
        event_map = {
            "rain": EventType.WEATHER_CHANGE,
            "user_edit": EventType.USER_EDIT,
            "place_closed": EventType.PLACE_CLOSED
        }
        
        etype = event_map.get(input.event_type.lower())
        if not etype:
            raise HTTPException(status_code=400, detail="Invalid event type")
            
        return engine.trigger_event(etype, input.payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/itinerary/optimize")
async def optimize_itinerary(body: OptimizeInput):
    """
    Dynamically update and optimize itinerary based on user modification.
    Follows STEP 1-7 logic from prompt30, enriched with prompt31 decision analysis.
    """
    try:
        state = get_state()
        bundle = body.itinerary_bundle or state.itinerary
        if not itinerary_has_content(bundle):
            raise HTTPException(status_code=400, detail="No itinerary content to optimize")

        persona: Dict[str, Any] = dict(state.persona or {})
        if body.persona:
            persona = {**persona, **body.persona}
        if body.destination and str(body.destination).strip():
            persona["destination"] = str(body.destination).strip()
        dest = str(persona.get("destination", "Paris") or "Paris").strip() or "Paris"

        candidates, status, opt_intent = fetch_optimization_candidates(dest, body.user_request)

        # We need a flat list of segments for the OptimizationAgent
        all_segments: List[Dict[str, Any]] = []
        for day in bundle.get("days", []):
            all_segments.extend(day.get("segments", []))

        result = optimization_agent.execute(
            {
                "current_itinerary": all_segments,
                "user_request": body.user_request,
                "user_preferences": persona,
                "candidate_places": candidates,
            },
            state.__dict__,
        )

        # Prompt 31: Add smart decision assistant analysis for the top recommendation if available
        decision_analysis = None
        recs = result.get("recommendations")
        preview = result.get("selected_option_preview")
        updated = result.get("updated_itinerary")
        meal_edit = result.get("meal_edit")

        if recs and preview and updated and meal_edit:
            top_rec = recs[0]
            replaced_idx = meal_edit.get("flat_segment_index")
            if replaced_idx is not None and 0 <= replaced_idx < len(all_segments):
                replaced_name = all_segments[replaced_idx].get("place_name", "current location")
                decision_analysis = decision_agent.execute({
                    "user_request": body.user_request,
                    "current_itinerary": all_segments,
                    "proposed_change": {
                        "replace": replaced_name,
                        "with": top_rec.get("name", "Unknown")
                    },
                    "impact_analysis": {
                        "delay_minutes": safe_float(preview.get("delay", "0")),
                        "cost_change": clean_cost(preview.get("cost_change", "0")),
                        "travel_time_added": safe_float(preview.get("travel_time", "0")),
                        "impact_level": preview.get("impact_level", "LOW")
                    },
                    "updated_itinerary": updated
                }, state.__dict__)

        return {
            **result,
            "decision_analysis": decision_analysis,
            "candidate_places": candidates,
            "flat_segment_count": len(all_segments),
            "candidates_fetch_status": status,
            "optimization_intent": opt_intent,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Optimization failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/itinerary/evaluate-decision")
async def evaluate_decision(body: EvaluateDecisionInput):
    """
    Directly evaluate a proposed change using the Smart Travel Decision Assistant (Prompt 31).
    """
    try:
        state = get_state()
        return decision_agent.execute(body.dict(), state.__dict__)
    except Exception as e:
        logger.exception("Decision evaluation failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/itinerary/optimize/apply")
async def optimize_apply(body: OptimizeApplyInput):
    """Apply user's chosen recommendation to the v2 bundle; update session and optionally saved row."""
    snap = body.optimization_snapshot or {}
    recs = snap.get("recommendations")
    if not isinstance(recs, list) or not recs:
        raise HTTPException(
            status_code=400, detail="optimization_snapshot missing recommendations"
        )
    cands = snap.get("candidate_places")
    if not isinstance(cands, list):
        raise HTTPException(
            status_code=400, detail="optimization_snapshot missing candidate_places"
        )
    idx = body.selected_recommendation_index
    if idx < 0 or idx >= len(recs):
        raise HTTPException(
            status_code=400, detail="Invalid selected_recommendation_index"
        )
    if not itinerary_has_content(body.itinerary_bundle):
        raise HTTPException(status_code=400, detail="No itinerary content to apply")
    persona_ctx = persona_for_pricing(body.saved_itinerary_id)
    dest_hint = str(persona_ctx.get("destination") or "").strip() or None
    try:
        merged = apply_recommendation_to_bundle(
            body.itinerary_bundle,
            idx,
            recs,
            cands,
            snap,
            target_day_index=body.target_day_index,
            target_segment_index=body.target_segment_index,
            destination_hint=dest_hint,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    errors: List[str] = validate_edited_itinerary_bundle(merged)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    finalized = finalize_edited_bundle(merged)
    enrich_itinerary_pricing(
        finalized,
        persona_for_pricing(body.saved_itinerary_id),
        run_price_agent=True,
        force_price_agent=True,
    )
    update_state({"itinerary": finalized})
    sid = (body.saved_itinerary_id or "").strip()
    if sid:
        if not get_saved_itinerary(sid):
            raise HTTPException(status_code=404, detail="saved itinerary not found")
        try:
            update_saved_itinerary_bundle(sid, finalized)
        except ValueError:
            raise HTTPException(status_code=404, detail="saved itinerary not found")
    return {"ok": True, "itinerary": finalized}

@app.get("/state")
async def get_system_state():
    """Returns current system state."""
    return engine.get_current_state()

@app.get("/saved")
async def list_saved_itineraries():
    """Summaries for My trips (newest first)."""
    return list_saved_itinerary_summaries()


@app.put("/itinerary")
async def put_session_itinerary(body: ItineraryReplaceBody):
    """
    Replace the in-memory session itinerary (v2 bundle). Used when editing a generated
    plan that is not loaded as a saved-trip-only view. See PUT /saved/{id} when
    viewingSavedSnapshot is true — avoid double-writing the same logical trip.
    """
    errors: List[str] = validate_edited_itinerary_bundle(body.itinerary)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    finalized = finalize_edited_bundle(body.itinerary)
    enrich_itinerary_pricing(
        finalized,
        persona_for_pricing(None),
        run_price_agent=True,
        force_price_agent=True,
    )
    update_state({"itinerary": finalized})
    return {"ok": True, "itinerary": finalized}


@app.put("/saved/{saved_id}")
async def put_saved_itinerary(saved_id: str, body: SavedItineraryBundleBody):
    """Update itinerary_bundle for a saved row (SQLite)."""
    if not get_saved_itinerary(saved_id):
        raise HTTPException(status_code=404, detail="saved itinerary not found")
    errors: List[str] = validate_edited_itinerary_bundle(body.itinerary_bundle)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    finalized = finalize_edited_bundle(body.itinerary_bundle)
    enrich_itinerary_pricing(
        finalized,
        persona_for_pricing(saved_id),
        run_price_agent=True,
        force_price_agent=True,
    )
    try:
        update_saved_itinerary_bundle(saved_id, finalized)
    except ValueError:
        raise HTTPException(status_code=404, detail="saved itinerary not found")
    return {"ok": True, "itinerary_bundle": finalized}


@app.get("/saved/{saved_id}/pdf")
async def download_saved_pdf(saved_id: str):
    """PDF export of stored bundle (snapshot only; no live API calls)."""
    row = get_saved_itinerary(saved_id)
    if not row:
        raise HTTPException(status_code=404, detail="saved itinerary not found")
    try:
        pdf_bytes = build_itinerary_pdf_bytes(row)
    except Exception as e:
        logger.exception("PDF generation failed for saved_id=%s", saved_id)
        raise HTTPException(status_code=500, detail="pdf generation failed") from e
    fname = pdf_attachment_filename(row)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/saved/{saved_id}")
async def get_saved(saved_id: str):
    """Load full persisted itinerary by id (persona snapshot + bundle)."""
    row = get_saved_itinerary(saved_id)
    if not row:
        raise HTTPException(status_code=404, detail="saved itinerary not found")
    return row


@app.get("/itinerary")
async def get_itinerary():
    """Returns the latest itinerary and conversation status."""
    st = get_state()
    return {
        "itinerary": st.itinerary,
        "conversation_phase": st.conversation_phase,
        "pending_question": st.pending_question,
    }
