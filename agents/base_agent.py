from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseAgent(ABC):
    """
    Abstract base class for all grant automation agents.
    """
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.context: Dict[str, Any] = {}

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process the input data and return results.
        Must be implemented by concrete agent classes.
        """
        pass

    def update_context(self, new_context: Dict[str, Any]) -> None:
        """
        Update the agent's context with new information.
        """
        self.context.update(new_context)

    @abstractmethod
    async def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """
        Validate the input data before processing.
        Must be implemented by concrete agent classes.
        """
        pass
