import json
from typing import Any, Dict
from core.contracts import Agent
from services.llm_service import call_llm

class DestinationAgent(Agent):
    """
    DestinationAgent resolves user destination intent using LLM.
    """

    def name(self) -> str:
        return "destination_agent"

    def execute(self, input_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolves destination from user input.
        """
        user_text = input_data.get("user_input", "")

        system_prompt = """
        You are a travel destination resolution agent.
        1. Extract destination from user input.
        2. Classify it as city, country, region, or unclear.
        3. If CITY -> return resolved.
        4. If COUNTRY or REGION -> suggest 3-5 top travel cities.
        5. If UNCLEAR -> return unclear status.
        - Do NOT assume a city if only country is given.
        - Do NOT hallucinate unknown places.
        - Always return structured JSON.
        """
        
        user_prompt = f"User Input: {user_text}"
        
        response_json = call_llm(system_prompt, user_prompt)
        
        try:
            return json.loads(response_json)
        except json.JSONDecodeError:
            return {"status": "unclear", "message": "Could not resolve destination.", "suggested_cities": []}
