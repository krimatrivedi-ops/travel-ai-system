from dataclasses import dataclass, replace, field
from datetime import datetime
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class State:
    """
    Immutable State for the Travel AI System.
    Every update returns a NEW state object.
    """
    user_input: Optional[str] = None
    persona: Dict[str, Any] = field(default_factory=dict)
    # v2: {"itinerary_version": 2, "days": [...]} ; legacy: flat list (deprecated)
    itinerary: Any = field(default_factory=dict)
    pois: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)
    # Preference conversation (multi-turn before planning).
    conversation_phase: str = "idle"  # idle | collecting_preferences | generated
    partial_persona: Dict[str, Any] = field(default_factory=dict)
    conversation_messages: List[Dict[str, str]] = field(default_factory=list)
    pending_question: Optional[str] = None

# Internal singleton-like reference to the current state.
# While it's a global variable, it's only modified through controlled functions.
_current_state = State()

def get_state() -> State:
    """Returns the current state."""
    return _current_state

def update_state(new_data: Dict[str, Any]) -> State:
    """
    Updates the state with new data and returns a NEW immutable State object.
    
    Args:
        new_data: A dictionary containing fields to update.
    
    Returns:
        A NEW instance of State with updated values and a fresh last_updated timestamp.
    """
    global _current_state
    
    # Ensure last_updated is always refreshed on update
    new_data["last_updated"] = datetime.now()
    
    # Use dataclass.replace for immutability
    _current_state = replace(_current_state, **new_data)
    return _current_state

def reset_state() -> State:
    """Resets the state to its initial values."""
    global _current_state
    _current_state = State()
    return _current_state
