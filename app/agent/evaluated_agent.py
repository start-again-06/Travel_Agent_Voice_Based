
import logging
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from app.evals import EvaluationRunner

logger = logging.getLogger("evaluated-agent")


class EvaluatedAgentWrapper:
    """
    Wraps the agent to run evaluations in the background.

    This wrapper:
    - Tracks tool calls (search_places, retrieve_travel_guides)
    - Runs evaluations after itinerary generation
    - Saves results to evaluation_results.json
    - Does NOT change existing agent behavior
    """

    def __init__(self, agent, output_dir: str = "."):
        """
        Initialize the evaluated agent wrapper.

        Args:
            agent: The base agent graph
            output_dir: Directory to save evaluation results
        """
        self.agent = agent
        self.eval_runner = EvaluationRunner()
        self.output_dir = Path(output_dir)

        # Track context for evaluations
        self.search_results = {}
        self.travel_times = {}
        self.last_itinerary = None
        self.original_itinerary = None
        self.edit_instruction = None

        logger.info("Evaluated agent wrapper initialized")

    def _extract_itinerary(self, text: str) -> Optional[str]:
  
        if "---ITINERARY---" in text:
            parts = text.split("---ITINERARY---")
            if len(parts) > 1:
                return parts[1].strip()
        return None

    def _parse_search_results(self, tool_output: str) -> list:
        """Parse search results from tool output."""
        try:
            # Tool returns string representation of list
            # e.g., "[{'name': 'Museum', 'rating': 4.5}, ...]"
            import ast
            return ast.literal_eval(tool_output)
        except Exception as e:
            logger.warning(f"Could not parse search results: {e}")
            return []

    def _track_tool_call(self, tool_name: str, tool_output: str, arguments: dict):
        """Track tool calls for evaluation context."""
        if tool_name == "search_places":
            category = arguments.get("category", "unknown")
            results = self._parse_search_results(tool_output)

            if results:
                if category not in self.search_results:
                    self.search_results[category] = []
                self.search_results[category].extend(results)

                logger.debug(
                    f"Tracked {len(results)} search results for category '{category}'"
                )

        elif tool_name == "estimate_travel_time":
            # Extract travel time from output
            # Format: "Duration: 25.5 mins, Distance: 10.2 km"
            match = re.search(r'Duration: ([\d.]+) mins', tool_output)
            if match:
                duration = float(match.group(1))
                # Store travel times (we'll organize by day later)
                if "all_times" not in self.travel_times:
                    self.travel_times["all_times"] = []
                self.travel_times["all_times"].append(duration)

    def _run_evaluations(self, itinerary_text: str, is_edit: bool = False):
        """
        Run evaluations and save results.

        Args:
            itinerary_text: The itinerary markdown text
            is_edit: Whether this is an edit operation
        """
        try:
            logger.info("Running evaluations in background...")

            # Build evaluation context
            context = {
                "search_results": self.search_results if self.search_results else None,
            }

            # Add travel times if available
            if self.travel_times.get("all_times"):
                # Organize travel times by day (simple approach: split evenly)
                all_times = self.travel_times["all_times"]
                # For now, assign all to day 1 (could be improved)
                context["travel_times"] = {1: all_times}

            # Add edit context if this is an edit
            if is_edit and self.original_itinerary:
                context["original_itinerary"] = self.original_itinerary
                context["edit_instruction"] = self.edit_instruction

            # Run evaluations
            results = self.eval_runner.run_all_evals(
                itinerary_text=itinerary_text,
                context=context
            )

            # Save results to file
            output_file = self.output_dir / "evaluation_results.json"
            self.eval_runner.save_results(results, str(output_file))

            # Log summary
            overall = results["overall"]
            if overall["all_passed"]:
                logger.info("✓ Itinerary passed all evaluations")
            else:
                logger.warning(
                    f"✗ Itinerary has {overall['total_issues']} evaluation issues"
                )
                for issue in overall["all_issues"][:5]:  # Log first 5 issues
                    logger.warning(f"  - {issue}")

        except Exception as e:
            logger.error(f"Evaluation failed: {e}", exc_info=True)

    async def astream(self, input_data, config, **kwargs):
        """
        Stream from agent and run evaluations when itinerary is generated.

        This method wraps the agent's astream to:
        1. Track tool calls
        2. Detect itinerary generation
        3. Run evaluations in background
        4. Pass through all events unchanged
        """
        is_edit_operation = False
        last_message_content = ""

        # Check if this is an edit operation
        messages = input_data.get("messages", [])
        if messages:
            # Look for edit indicators in recent messages
            for msg in messages[-3:]:
                if isinstance(msg, tuple):
                    content = msg[1] if len(msg) > 1 else ""
                else:
                    content = getattr(msg, "content", "")

                content_lower = str(content).lower()
                if any(word in content_lower for word in ["change", "update", "modify", "edit", "replace"]):
                    is_edit_operation = True
                    self.edit_instruction = content
                    break

        # Stream events from the base agent
        async for event in self.agent.astream(input_data, config, **kwargs):
            # Pass through the event unchanged
            yield event

            # Track events for evaluation
            for node, values in event.items():
                if node == "chatbot":
                    # Get the message content
                    if "messages" in values and values["messages"]:
                        last_msg = values["messages"][-1]
                        last_message_content = getattr(last_msg, "content", "")

                        # Check for tool calls
                        tool_calls = getattr(last_msg, "tool_calls", None)
                        if tool_calls:
                            logger.debug(
                                f"Agent called tools: {[tc.get('name', tc.get('id', 'unknown')) for tc in tool_calls]}"
                            )

                elif node == "tools":
                    # Track tool results
                    if "messages" in values and values["messages"]:
                        for tool_msg in values["messages"]:
                            # Extract tool name and content
                            tool_name = getattr(tool_msg, "name", None)
                            tool_content = getattr(tool_msg, "content", "")

                            # Get arguments from the previous chatbot message
                            # (This is a simplified approach - in production you'd track this more carefully)
                            if tool_name:
                                self._track_tool_call(tool_name, tool_content, {})

        # After streaming is complete, check if itinerary was generated
        itinerary_text = self._extract_itinerary(last_message_content)

        if itinerary_text:
            # Check if this is a new itinerary or an edit
            if self.last_itinerary and itinerary_text != self.last_itinerary:
                # This is an edit
                if not self.original_itinerary:
                    # First edit - save original
                    self.original_itinerary = self.last_itinerary

                logger.info("Detected itinerary edit")
                self._run_evaluations(itinerary_text, is_edit=True)

            elif not self.last_itinerary:
                # This is the first itinerary
                logger.info("Detected new itinerary generation")
                self._run_evaluations(itinerary_text, is_edit=False)

            # Update last itinerary
            self.last_itinerary = itinerary_text

    async def ainvoke(self, input_data, config, **kwargs):
        """
        Invoke the agent (non-streaming).

        Collects all events and returns final state.
        """
        final_state = None
        async for event in self.astream(input_data, config, **kwargs):
            final_state = event
        return final_state

    def reset_context(self):
        """Reset evaluation context (call between sessions)."""
        self.search_results = {}
        self.travel_times = {}
        self.last_itinerary = None
        self.original_itinerary = None
        self.edit_instruction = None
        logger.info("Evaluation context reset")
