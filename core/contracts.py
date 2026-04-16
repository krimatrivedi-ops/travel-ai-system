from abc import ABC, abstractmethod
from typing import Any, Dict

class Agent(ABC):
    """
    Standard interface for all agents in the Travel AI System.
    
    Rules:
    - Every agent MUST follow this contract.
    - No agent can directly modify global state.
    - All output must be an explicit dictionary.
    - No hidden side effects.
    """

    @abstractmethod
    def name(self) -> str:
        """Returns the unique name of the agent."""
        pass

    @abstractmethod
    def execute(self, input_data: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the agent logic based on the provided input and current local state.
        
        Args:
            input_data: The specific input for this execution step.
            state: The context or history relevant to this agent.
            
        Returns:
            A dictionary containing the agent's response or resulting action.
        """
        pass
