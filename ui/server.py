from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from runtime.orchestrator import Orchestrator
from runtime.engine import ReactiveEngine
from agents.replanner_agent import ReplannerAgent
from agents.optimization_agent import OptimizationAgent
from agents.decision_agent import DecisionAgent
from events.event_bus import EventType
from routes.pricing import router as pricing_router
from jobs.scheduler import start_scheduler
from services.itinerary_store import init_store, get_saved_itinerary, update_saved_itinerary_bundle
from services.osm_service import fetch_optimization_candidates
from services.pricing_service import enrich_itinerary_pricing
from core.itinerary_schema import (
    itinerary_has_content,
    finalize_edited_bundle,
    validate_edited_itinerary_bundle,
)
from core.optimization_merge import apply_recommendation_to_bundle
from state.store import get_state, update_state
import uvicorn
import logging

logger = logging.getLogger(__name__)

app = FastAPI()
app.include_router(pricing_router)

engine = ReactiveEngine(Orchestrator(), ReplannerAgent())
optimization_agent = OptimizationAgent()
decision_agent = DecisionAgent()


def persona_for_pricing(saved_itinerary_id: Optional[str] = None) -> Dict[str, Any]:
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
async def startup_event():
    init_store()
    start_scheduler()

class PlanRequest(BaseModel):
    user_input: str

class EventRequest(BaseModel):
    event_type: str
    payload: dict

class OptimizeRequest(BaseModel):
    user_request: str
    itinerary_bundle: Optional[Dict[str, Any]] = None
    persona: Optional[Dict[str, Any]] = None
    destination: Optional[str] = None


class OptimizeApplyRequest(BaseModel):
    itinerary_bundle: Dict[str, Any]
    selected_recommendation_index: int
    optimization_snapshot: Dict[str, Any]
    saved_itinerary_id: Optional[str] = None
    target_day_index: Optional[int] = None
    target_segment_index: Optional[int] = None


class EvaluateDecisionRequest(BaseModel):
    user_request: str
    current_itinerary: List[Dict[str, Any]]
    proposed_change: Dict[str, str]
    impact_analysis: Dict[str, Any]
    updated_itinerary: List[Dict[str, Any]]

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Travel AI UI</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="container mt-5">
        <h1>Travel AI System</h1>
        <div class="mb-3">
            <input type="text" id="userInput" class="form-control" placeholder="Enter travel request">
            <button onclick="planTrip()" class="btn btn-primary mt-2">Plan Trip</button>
            <button onclick="simulateEvent('WEATHER_CHANGE', {condition: 'rain'})" class="btn btn-warning mt-2">Simulate Rain</button>
        </div>
        <h3>Itinerary</h3>
        <pre id="itinerary" class="bg-light p-3"></pre>
        <h3>Persona</h3>
        <pre id="persona" class="bg-light p-3"></pre>
        <script>
            async function planTrip() {
                const text = document.getElementById('userInput').value;
                const res = await fetch('/plan', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_input: text})
                });
                const data = await res.json();
                updateUI(data);
            }
            async function simulateEvent(type, payload) {
                await fetch('/event', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({event_type: type, payload: payload})
                });
                refreshState();
            }
            async function refreshState() {
                const res = await fetch('/state');
                const data = await res.json();
                updateUI(data);
            }
            function updateUI(data) {
                document.getElementById('itinerary').innerText = JSON.stringify(data.itinerary || data.current_itinerary, null, 2);
                document.getElementById('persona').innerText = JSON.stringify(data.persona || {}, null, 2);
            }
            setInterval(refreshState, 3000);
        </script>
    </body>
    </html>
    """

@app.post("/plan")
async def plan(req: PlanRequest):
    return engine.run_once(req.user_input)

@app.post("/event")
async def trigger_event(req: EventRequest):
    return engine.trigger_event(EventType(req.event_type), req.payload)

@app.post("/itinerary/optimize")
async def optimize_itinerary(body: OptimizeRequest):
    """
    Dynamically update and optimize itinerary based on user modification.
    Enriched with smart decision analysis.
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

        # Smart decision analysis for the top recommendation
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
                        "delay_minutes": float(preview.get("delay", "0").split()[0]) if isinstance(preview.get("delay"), str) and preview.get("delay").split() else 0,
                        "cost_change": float(preview.get("cost_change", "0").replace("+", "").replace("-", "").replace("₹", "").strip()) if isinstance(preview.get("cost_change"), str) else 0,
                        "travel_time_added": float(top_rec.get("travel_time", "0").split()[0]) if isinstance(top_rec.get("travel_time"), str) and top_rec.get("travel_time").split() else 0,
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


@app.post("/itinerary/optimize/apply")
async def optimize_apply(body: OptimizeApplyRequest):
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


@app.post("/itinerary/evaluate-decision")
async def evaluate_decision(body: EvaluateDecisionRequest):
    """
    Directly evaluate a proposed change using the Smart Travel Decision Assistant.
    """
    try:
        state = get_state()
        return decision_agent.execute(body.dict(), state.__dict__)
    except Exception as e:
        logger.exception("Decision evaluation failed")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state")
async def get_state_endpoint():
    return engine.get_current_state()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
