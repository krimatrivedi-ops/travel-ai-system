import json
from typing import Any, Dict
from core.contracts import Agent
from services.llm_service import call_llm

class PersonaAgent(Agent):
    """
    PersonaAgent converts user input into a structured persona object using an LLM,
    intelligently merging with existing preferences.
    """

    def name(self) -> str:
        return "persona_agent"

    def execute(self, input_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes user input to update the travel persona.
        """
        user_text = input_data.get("user_input", "")
        # Assuming state might be a dictionary or object with a persona attribute
        existing_persona = state.get("persona", {}) if isinstance(state, dict) else getattr(state, "persona", {})

        system_prompt = """
        You are a travel persona modeling agent.
        Convert user input into structured travel preferences.
        If an existing persona is provided, UPDATE it intelligently.
        - Preserve previous preferences unless explicitly changed.
        - Infer missing values.
        - Return ONLY JSON.
        """
        
        user_prompt = f"Existing Persona: {json.dumps(existing_persona)}\n\nNew User Input: {user_text}"
        
        response_json = call_llm(system_prompt, user_prompt)
        
        try:
            return json.loads(response_json)
        except json.JSONDecodeError:
            return existing_persona
