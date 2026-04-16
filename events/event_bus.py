from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

class EventType(Enum):
    WEATHER_CHANGE = "WEATHER_CHANGE"
    USER_EDIT = "USER_EDIT"
    PLACE_CLOSED = "PLACE_CLOSED"

@dataclass(frozen=True)
class Event:
    """Represents a single event in the system."""
    type: EventType
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None

# Internal append-only event log.
_event_log: List[Event] = []

def emit_event(event_type: EventType, payload: Dict[str, Any], source: Optional[str] = None) -> Event:
    """
    Emits an event into the system's global event bus.
    
    Args:
        event_type: The category of the event.
        payload: Data associated with the event.
        source: The name of the agent or component that emitted the event.
        
    Returns:
        The newly created Event object.
    """
    global _event_log
    
    new_event = Event(
        type=event_type,
        payload=payload,
        source=source
    )
    
    _event_log.append(new_event)
    return new_event

def get_events(event_type: Optional[EventType] = None) -> List[Event]:
    """
    Retrieves the event log, optionally filtered by type.
    
    Args:
        event_type: Optional filter for event types.
        
    Returns:
        A list of Event objects.
    """
    if event_type:
        return [e for e in _event_log if e.type == event_type]
    return list(_event_log)

def clear_events():
    """Clears the event log."""
    global _event_log
    _event_log = []
