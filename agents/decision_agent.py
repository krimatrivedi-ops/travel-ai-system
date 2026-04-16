import json
from typing import Any, Dict, List, Optional
from core.contracts import Agent
from services.llm_service import call_llm

class DecisionAgent(Agent):
    """
    A smart travel decision assistant that helps users decide whether a proposed
    itinerary change is a good idea and suggests re-optimization or alternatives.
    """

    def name(self) -> str:
        return "decision_agent"

    def execute(self, input_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates a proposed change and returns a conversational recommendation.
        
        Input:
            user_request: str
            current_itinerary: List[Dict]
            proposed_change: Dict[str, str] (e.g., {"replace": "...", "with": "..."})
            impact_analysis: Dict (delay_minutes, cost_change, travel_time_added, impact_level)
            updated_itinerary: List[Dict]
        """
        user_request = input_data.get("user_request", "")
        current_itinerary = input_data.get("current_itinerary", [])
        proposed_change = input_data.get("proposed_change", {})
        impact_analysis = input_data.get("impact_analysis", {})
        updated_itinerary = input_data.get("updated_itinerary", [])

        system_prompt = """
You are a smart travel decision assistant.
Your job is NOT just to show impact, but to help the user decide whether a change is a good idea and suggest better alternatives when needed.

TASK:
1. Realistic Impact Adjustment: Consider real-world travel behavior (exploration time 1.5–3h, fatigue). Adjust impact if underestimated.
2. Experience Quality Analysis: Classify as RELAXED, BALANCED, RUSHED, or VERY_RUSHED.
3. Decision Recommendation: GOOD IDEA, ACCEPTABLE, NOT IDEAL, or AVOID.
4. Smart Suggestions: Include at least one re-optimization and one alternative.

STYLE:
- Concise but insightful.
- Smart human travel planner tone.
- Interpret numbers, don't just repeat them.
- Prioritize user experience over rigid schedule.

OUTPUT FORMAT (JSON):
{
  "decision": "GOOD IDEA | ACCEPTABLE | NOT IDEAL | AVOID",
  "message": "string",
  "impact_summary": {
    "delay": "string",
    "cost_change": "string",
    "experience": "string"
  },
  "recommendations": [
    { "type": "reoptimize_day", "text": "string" },
    { "type": "alternative_option", "text": "string" }
  ]
}
"""

        user_prompt = f"""
USER_REQUEST: {user_request}
CURRENT_ITINERARY: {json.dumps(current_itinerary, ensure_ascii=False)}
PROPOSED_CHANGE: {json.dumps(proposed_change, ensure_ascii=False)}
IMPACT_ANALYSIS: {json.dumps(impact_analysis, ensure_ascii=False)}
UPDATED_ITINERARY: {json.dumps(updated_itinerary, ensure_ascii=False)}
"""

        response_json = call_llm(system_prompt, user_prompt)

        try:
            return json.loads(response_json)
        except json.JSONDecodeError:
            return {
                "decision": "ACCEPTABLE",
                "message": "I'm having trouble analyzing this specifically, but it seems manageable. Please double check the travel times.",
                "impact_summary": {
                    "delay": f"{impact_analysis.get('delay_minutes', 0)} mins",
                    "cost_change": str(impact_analysis.get('cost_change', '0')),
                    "experience": "BALANCED"
                },
                "recommendations": []
            }
