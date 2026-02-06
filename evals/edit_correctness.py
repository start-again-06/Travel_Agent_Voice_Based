
"""Edit correctness evaluation for itinerary modifications.

Checks:
1. Voice edits only modify intended sections
2. No unintended changes elsewhere in the itinerary
"""
import re
import logging
from typing import Dict, List, Any, Optional, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger("evals.edit_correctness")


class EditCorrectnessEval:
    """Evaluates correctness of itinerary edits."""

    def __init__(self):
        self.results = []

    def parse_itinerary_sections(self, itinerary_text: str) -> Dict[str, str]:
        """
        Parse itinerary into sections for comparison.

        Args:
            itinerary_text: Raw itinerary markdown text

        Returns:
            Dict mapping section IDs to content
        """
        sections = {}
        current_section = None
        current_content = []

        lines = itinerary_text.split('\n')

        for line in lines:
            # Match day headers
            day_match = re.match(r'^#\s*Day\s+(\d+):', line)
            if day_match:
                # Save previous section
                if current_section:
                    sections[current_section] = '\n'.join(current_content)

                # Start new section
                day_num = day_match.group(1)
                current_section = f"day_{day_num}"
                current_content = [line]

            # Match travel tips section
            elif re.match(r'^\*\*Travel Tips:', line):
                if current_section:
                    sections[current_section] = '\n'.join(current_content)

                current_section = "travel_tips"
                current_content = [line]

            else:
                if current_section:
                    current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_content)

        return sections

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity ratio between two texts.

        Args:
            text1: First text
            text2: Second text

        Returns:
            Similarity ratio (0.0 to 1.0)
        """
        return SequenceMatcher(None, text1, text2).ratio()

    def find_differences(
        self,
        original_sections: Dict[str, str],
        edited_sections: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Find differences between original and edited sections.

        Args:
            original_sections: Original itinerary sections
            edited_sections: Edited itinerary sections

        Returns:
            List of differences found
        """
        differences = []

        # Check all sections from original
        all_sections = set(original_sections.keys()) | set(edited_sections.keys())

        for section_id in all_sections:
            original_content = original_sections.get(section_id, "")
            edited_content = edited_sections.get(section_id, "")

            # Calculate similarity
            similarity = self.calculate_similarity(original_content, edited_content)

            # If not identical, mark as changed
            if similarity < 1.0:
                differences.append({
                    "section": section_id,
                    "similarity": similarity,
                    "original_length": len(original_content),
                    "edited_length": len(edited_content),
                    "change_type": self._classify_change(original_content, edited_content),
                })

        return differences

    def _classify_change(self, original: str, edited: str) -> str:
        """
        Classify the type of change made.

        Args:
            original: Original text
            edited: Edited text

        Returns:
            Change classification
        """
        if not original and edited:
            return "addition"
        elif original and not edited:
            return "deletion"
        elif len(edited) > len(original) * 1.5:
            return "major_addition"
        elif len(edited) < len(original) * 0.5:
            return "major_deletion"
        else:
            return "modification"

    def detect_unintended_changes(
        self,
        differences: List[Dict[str, Any]],
        intended_sections: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Detect changes that were not intended.

        Args:
            differences: All differences found
            intended_sections: List of section IDs that were supposed to change

        Returns:
            List of unintended changes
        """
        unintended = []

        for diff in differences:
            section = diff["section"]

            # Check if this section was supposed to change
            is_intended = any(
                intended_section in section or section in intended_section
                for intended_section in intended_sections
            )

            if not is_intended:
                unintended.append({
                    **diff,
                    "reason": "Section changed but was not in intended edit scope"
                })

        return unintended

    def evaluate(
        self,
        original_itinerary: str,
        edited_itinerary: str,
        edit_instruction: Optional[str] = None,
        intended_sections: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate edit correctness.

        Args:
            original_itinerary: Original itinerary text
            edited_itinerary: Edited itinerary text
            edit_instruction: Optional edit instruction from user
            intended_sections: Optional list of sections that should change

        Returns:
            Evaluation results
        """
        logger.info("Running Edit Correctness Evaluation...")

        # Parse both versions
        original_sections = self.parse_itinerary_sections(original_itinerary)
        edited_sections = self.parse_itinerary_sections(edited_itinerary)

        # Find all differences
        differences = self.find_differences(original_sections, edited_sections)

        # If no intended sections specified, try to infer from edit instruction
        if not intended_sections and edit_instruction:
            intended_sections = self._infer_intended_sections(edit_instruction)

        # Detect unintended changes
        unintended_changes = []
        if intended_sections:
            unintended_changes = self.detect_unintended_changes(
                differences,
                intended_sections
            )

        # Determine if evaluation passed
        passed = len(unintended_changes) == 0

        # Build results
        issues = []
        for change in unintended_changes:
            issues.append(
                f"Unintended change in section '{change['section']}': "
                f"{change['change_type']} (similarity: {change['similarity']:.2%})"
            )

        # Summary
        summary = {
            "total_sections_original": len(original_sections),
            "total_sections_edited": len(edited_sections),
            "total_changes": len(differences),
            "intended_changes": len(differences) - len(unintended_changes),
            "unintended_changes": len(unintended_changes),
        }

        return {
            "eval_type": "edit_correctness",
            "passed": passed,
            "summary": summary,
            "differences": differences,
            "unintended_changes": unintended_changes,
            "issues": issues,
        }

    def _infer_intended_sections(self, edit_instruction: str) -> List[str]:
        """
        Infer which sections should change based on edit instruction.

        Args:
            edit_instruction: User's edit instruction

        Returns:
            List of section IDs that should change
        """
        intended = []
        instruction_lower = edit_instruction.lower()

        # Look for day mentions
        day_matches = re.findall(r'day\s+(\d+)', instruction_lower)
        for day_num in day_matches:
            intended.append(f"day_{day_num}")

        # Look for time period mentions
        if "morning" in instruction_lower:
            intended.append("morning")
        if "afternoon" in instruction_lower:
            intended.append("afternoon")
        if "evening" in instruction_lower:
            intended.append("evening")

        # Look for tips mentions
        if "tip" in instruction_lower or "advice" in instruction_lower:
            intended.append("travel_tips")

        # If nothing specific found, assume any day could change
        if not intended:
            intended.append("day_")

        return intended

    def compare_activities(
        self,
        original_itinerary: str,
        edited_itinerary: str
    ) -> Dict[str, Any]:
        """
        Compare activities line-by-line for detailed analysis.

        Args:
            original_itinerary: Original itinerary text
            edited_itinerary: Edited itinerary text

        Returns:
            Detailed activity comparison
        """
        original_activities = self._extract_activities(original_itinerary)
        edited_activities = self._extract_activities(edited_itinerary)

        added = []
        removed = []
        modified = []

        # Find removed activities
        for orig_activity in original_activities:
            if orig_activity not in edited_activities:
                # Check if it was modified
                found_similar = False
                for edit_activity in edited_activities:
                    similarity = self.calculate_similarity(orig_activity, edit_activity)
                    if similarity > 0.6:  # Threshold for "modified"
                        modified.append({
                            "original": orig_activity,
                            "edited": edit_activity,
                            "similarity": similarity
                        })
                        found_similar = True
                        break

                if not found_similar:
                    removed.append(orig_activity)

        # Find added activities
        for edit_activity in edited_activities:
            if edit_activity not in original_activities:
                # Check if it's already in modified list
                already_counted = any(
                    m["edited"] == edit_activity for m in modified
                )
                if not already_counted:
                    added.append(edit_activity)

        return {
            "added_activities": added,
            "removed_activities": removed,
            "modified_activities": modified,
            "total_changes": len(added) + len(removed) + len(modified)
        }

    def _extract_activities(self, itinerary_text: str) -> List[str]:
        """
        Extract all activity lines from itinerary.

        Args:
            itinerary_text: Itinerary text

        Returns:
            List of activity descriptions
        """
        activities = []
        lines = itinerary_text.split('\n')

        for line in lines:
            # Match activity lines: * Morning/Afternoon/Evening: ...
            if re.match(r'^\*\s*(Morning|Afternoon|Evening)', line, re.IGNORECASE):
                activities.append(line.strip())

        return activities
