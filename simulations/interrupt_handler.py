"""Handles HITL interrupt detection and response generation."""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class InterruptHandler:
    """Detects and responds to LangGraph interrupts during simulation."""

    def generate_email_response(
        self,
        interrupt_msg: str,
        customer_email: str,
        persona: Dict
    ) -> str:
        """
        Generate natural-sounding email response based on persona.

        Args:
            interrupt_msg: The interrupt value from agent (e.g., "Please provide your email:")
            customer_email: Actual email from scenario customer data
            persona: Customer persona dict with communication_style

        Returns:
            Natural response string to pass to Command(resume=...)

        Examples:
            >>> handler.generate_email_response(
            ...     interrupt_msg="Please provide your email:",
            ...     customer_email="priya.patel@icloud.com",
            ...     persona={"communication_style": "Professional, expects precision"}
            ... )
            "My email is priya.patel@icloud.com"

            >>> # For casual persona:
            "It's sarah.chen@gmail.com"

            >>> # For corporate:
            "Our email is it.purchasing@finance.com"
        """
        # Get communication style from persona
        style = persona.get("communication_style", "").lower()
        sentiment = persona.get("sentiment", "neutral").lower()

        # Match response to persona style
        if "formal" in style or "corporate" in style or "business" in style:
            response = f"Our email is {customer_email}"
        elif "casual" in style or "friendly" in style or "informal" in style:
            response = f"It's {customer_email}"
        elif sentiment == "negative" or "frustrated" in style or "angry" in style:
            # Negative personas might be curt or impatient
            response = customer_email  # Just the email, no pleasantries
        else:
            # Default neutral response
            response = f"My email is {customer_email}"

        logger.debug(f"Generated email response for {customer_email}: {response}")
        return response

    def is_interrupt_present(self, result: Dict) -> bool:
        """Check if result contains an interrupt."""
        return "__interrupt__" in result and len(result["__interrupt__"]) > 0

    def extract_interrupt_value(self, result: Dict) -> Optional[str]:
        """Extract the interrupt message."""
        if not self.is_interrupt_present(result):
            return None
        return result["__interrupt__"][0].get("value", "")
