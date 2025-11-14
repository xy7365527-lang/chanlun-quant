import json
from typing import Any, Dict, List, Optional, Union

from chanlun_quant.agents.orchestrators.ta_orchestrator import TAOrchestrator


class AgentsAdapter:
    def __init__(self, orchestrator: TAOrchestrator):
        """
        Initialize the adapter with a TradingAgents orchestrator instance.
        """
        self.orchestrator = orchestrator

    def ask_json(self, prompt: str, **kwargs) -> Union[Dict[str, Any], List[Any], None]:
        """
        Send a prompt to the orchestrator and ensure the response is in JSON format.
        Returns a Python dict (or list) parsed from the JSON response.
        
        Args:
            prompt: Natural language prompt
            **kwargs: Additional parameters (e.g., symbol, trade_date for TradingAgentsGraph)
            
        Returns:
            Parsed JSON response as dict or list, or None if response is empty
            
        Raises:
            ValueError: If the response is not valid JSON
        """
        # Get the response from the underlying TradingAgents orchestrator.
        response = self.orchestrator.ask(prompt, **kwargs)

        # If the response is a string, attempt to parse it as JSON.
        if isinstance(response, str):
            response_str = response.strip()
            if not response_str:
                return None
            try:
                return json.loads(response_str)
            except json.JSONDecodeError as e:
                # If the response isn't pure JSON, raise an error for now.
                raise ValueError(f"Orchestrator response is not valid JSON: {e}")

        # If the orchestrator returns a dict or list (already parsed JSON), return it directly.
        if isinstance(response, dict) or isinstance(response, list):
            return response

        # If it's some other type (e.g., a custom object), convert to string and try to parse JSON.
        try:
            return json.loads(str(response))
        except Exception:
            # As a fallback, return the raw response if JSON parsing fails.
            return response
