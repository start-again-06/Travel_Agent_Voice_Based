
"""Evaluation runner for coordinating all evaluation checks."""
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from .feasibility import FeasibilityEval
from .edit_correctness import EditCorrectnessEval
from .grounding import GroundingEval

logger = logging.getLogger("evals.runner")


class EvaluationRunner:
    """Coordinates and runs all evaluation checks."""

    def __init__(self):
        self.feasibility_eval = FeasibilityEval()
        self.edit_correctness_eval = EditCorrectnessEval()
        self.grounding_eval = GroundingEval()

    def run_all_evals(
        self,
        itinerary_text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run all evaluations on an itinerary.

        Args:
            itinerary_text: The itinerary markdown text
            context: Optional context including:
                - search_results: POI search results
                - travel_times: Travel time estimates
                - original_itinerary: For edit checks
                - edit_instruction: User's edit request

        Returns:
            Complete evaluation results
        """
        logger.info("=" * 60)
        logger.info("Starting Comprehensive Itinerary Evaluation")
        logger.info("=" * 60)

        context = context or {}
        results = {}
        start_time = datetime.now()

        # 1. Feasibility Evaluation
        try:
            logger.info("\n[1/3] Running Feasibility Evaluation...")
            feasibility_result = self.feasibility_eval.evaluate(
                itinerary_text=itinerary_text,
                travel_times=context.get("travel_times")
            )
            results["feasibility"] = feasibility_result
            self._log_eval_result("Feasibility", feasibility_result)
        except Exception as e:
            logger.error(f"Feasibility evaluation failed: {e}")
            results["feasibility"] = {
                "eval_type": "feasibility",
                "passed": False,
                "error": str(e)
            }

        # 2. Grounding & Hallucination Evaluation
        try:
            logger.info("\n[2/3] Running Grounding & Hallucination Evaluation...")
            grounding_result = self.grounding_eval.evaluate(
                itinerary_text=itinerary_text,
                search_results=context.get("search_results")
            )
            results["grounding"] = grounding_result
            self._log_eval_result("Grounding", grounding_result)
        except Exception as e:
            logger.error(f"Grounding evaluation failed: {e}")
            results["grounding"] = {
                "eval_type": "grounding",
                "passed": False,
                "error": str(e)
            }

        # 3. Edit Correctness Evaluation (only if editing)
        if context.get("original_itinerary"):
            try:
                logger.info("\n[3/3] Running Edit Correctness Evaluation...")
                edit_result = self.edit_correctness_eval.evaluate(
                    original_itinerary=context["original_itinerary"],
                    edited_itinerary=itinerary_text,
                    edit_instruction=context.get("edit_instruction"),
                    intended_sections=context.get("intended_sections")
                )
                results["edit_correctness"] = edit_result
                self._log_eval_result("Edit Correctness", edit_result)
            except Exception as e:
                logger.error(f"Edit correctness evaluation failed: {e}")
                results["edit_correctness"] = {
                    "eval_type": "edit_correctness",
                    "passed": False,
                    "error": str(e)
                }

        # Calculate overall metrics
        elapsed_time = (datetime.now() - start_time).total_seconds()

        overall = self._calculate_overall_results(results)
        overall["evaluation_time_seconds"] = elapsed_time

        logger.info("\n" + "=" * 60)
        logger.info("Evaluation Complete")
        logger.info(f"Overall Status: {'✓ PASSED' if overall['all_passed'] else '✗ FAILED'}")
        logger.info(f"Total Evaluations: {overall['total_evals']}")
        logger.info(f"Passed: {overall['passed_evals']}")
        logger.info(f"Failed: {overall['failed_evals']}")
        logger.info(f"Time Elapsed: {elapsed_time:.2f}s")
        logger.info("=" * 60)

        return {
            "overall": overall,
            "evaluations": results,
            "timestamp": datetime.now().isoformat(),
        }

    def run_feasibility_eval(
        self,
        itinerary_text: str,
        travel_times: Optional[Dict[int, List[float]]] = None
    ) -> Dict[str, Any]:
        """
        Run only feasibility evaluation.

        Args:
            itinerary_text: The itinerary markdown text
            travel_times: Optional travel time estimates

        Returns:
            Feasibility evaluation results
        """
        return self.feasibility_eval.evaluate(itinerary_text, travel_times)

    def run_grounding_eval(
        self,
        itinerary_text: str,
        search_results: Optional[Dict[str, List[Dict[str, Any]]]] = None
    ) -> Dict[str, Any]:
        """
        Run only grounding evaluation.

        Args:
            itinerary_text: The itinerary markdown text
            search_results: Optional POI search results

        Returns:
            Grounding evaluation results
        """
        return self.grounding_eval.evaluate(itinerary_text, search_results)

    def run_edit_correctness_eval(
        self,
        original_itinerary: str,
        edited_itinerary: str,
        edit_instruction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run only edit correctness evaluation.

        Args:
            original_itinerary: Original itinerary text
            edited_itinerary: Edited itinerary text
            edit_instruction: Optional edit instruction

        Returns:
            Edit correctness evaluation results
        """
        return self.edit_correctness_eval.evaluate(
            original_itinerary,
            edited_itinerary,
            edit_instruction
        )

    def _calculate_overall_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate overall evaluation metrics."""
        total_evals = len(results)
        passed_evals = sum(
            1 for eval_result in results.values()
            if eval_result.get("passed", False)
        )
        failed_evals = total_evals - passed_evals

        all_passed = passed_evals == total_evals

        # Collect all issues
        all_issues = []
        for eval_name, eval_result in results.items():
            if "issues" in eval_result:
                for issue in eval_result["issues"]:
                    all_issues.append(f"[{eval_name}] {issue}")
            elif "results" in eval_result:
                for sub_result in eval_result["results"]:
                    if "issues" in sub_result:
                        for issue in sub_result["issues"]:
                            all_issues.append(f"[{eval_name}] {issue}")

        return {
            "all_passed": all_passed,
            "total_evals": total_evals,
            "passed_evals": passed_evals,
            "failed_evals": failed_evals,
            "pass_rate": (passed_evals / total_evals * 100) if total_evals > 0 else 0,
            "all_issues": all_issues,
            "total_issues": len(all_issues),
        }

    def _log_eval_result(self, eval_name: str, result: Dict[str, Any]):
        """Log evaluation result summary."""
        passed = result.get("passed", False)
        status = "✓ PASSED" if passed else "✗ FAILED"

        logger.info(f"  {eval_name}: {status}")

        if "summary" in result:
            summary = result["summary"]
            for key, value in summary.items():
                logger.info(f"    - {key}: {value}")

        if not passed and "issues" in result:
            logger.warning(f"  Issues found:")
            for issue in result["issues"]:
                logger.warning(f"    - {issue}")

    def save_results(
        self,
        results: Dict[str, Any],
        output_path: str
    ) -> None:
        """
        Save evaluation results to a JSON file.

        Args:
            results: Evaluation results
            output_path: Path to save results
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logger.info(f"Results saved to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")

    def generate_report(self, results: Dict[str, Any]) -> str:
        """
        Generate a human-readable evaluation report.

        Args:
            results: Evaluation results

        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 70)
        report.append("ITINERARY EVALUATION REPORT")
        report.append("=" * 70)
        report.append(f"Timestamp: {results.get('timestamp', 'N/A')}")
        report.append("")

        overall = results.get("overall", {})
        report.append("OVERALL RESULTS")
        report.append("-" * 70)
        report.append(f"Status: {'✓ PASSED' if overall.get('all_passed') else '✗ FAILED'}")
        report.append(f"Pass Rate: {overall.get('pass_rate', 0):.1f}%")
        report.append(f"Total Issues: {overall.get('total_issues', 0)}")
        report.append("")

        evaluations = results.get("evaluations", {})

        # Feasibility section
        if "feasibility" in evaluations:
            report.append("1. FEASIBILITY EVALUATION")
            report.append("-" * 70)
            feas = evaluations["feasibility"]
            report.append(f"Status: {'✓ PASSED' if feas.get('passed') else '✗ FAILED'}")

            if "summary" in feas:
                summary = feas["summary"]
                report.append(f"Total Days: {summary.get('total_days', 0)}")
                report.append(f"Checks Passed: {summary.get('passed_checks', 0)}/{summary.get('total_checks', 0)}")

            if "results" in feas:
                for result in feas["results"]:
                    if result.get("issues"):
                        report.append(f"\nDay {result.get('day')} Issues:")
                        for issue in result["issues"]:
                            report.append(f"  - {issue}")
            report.append("")

        # Grounding section
        if "grounding" in evaluations:
            report.append("2. GROUNDING & HALLUCINATION EVALUATION")
            report.append("-" * 70)
            ground = evaluations["grounding"]
            report.append(f"Status: {'✓ PASSED' if ground.get('passed') else '✗ FAILED'}")

            if "results" in ground:
                for result in ground["results"]:
                    check_name = result.get("check", "Unknown")
                    report.append(f"\n{check_name.replace('_', ' ').title()}:")

                    if check_name == "poi_grounding":
                        report.append(f"  - Grounded POIs: {result.get('grounded_count', 0)}")
                        report.append(f"  - Ungrounded POIs: {result.get('ungrounded_count', 0)}")
                        report.append(f"  - Grounding Rate: {result.get('grounding_percentage', 0):.1f}%")

                    elif check_name == "tip_citations":
                        report.append(f"  - Total Tips: {result.get('total_tips', 0)}")
                        report.append(f"  - Tips with Citations: {result.get('tips_with_citations', 0)}")
                        report.append(f"  - Citation Rate: {result.get('citation_percentage', 0):.1f}%")

                    elif check_name == "uncertainty_markers":
                        report.append(f"  - Uncertainty Markers Found: {result.get('total_uncertainty_markers', 0)}")

                    if result.get("issues"):
                        for issue in result["issues"]:
                            report.append(f"  - {issue}")
            report.append("")

        # Edit correctness section
        if "edit_correctness" in evaluations:
            report.append("3. EDIT CORRECTNESS EVALUATION")
            report.append("-" * 70)
            edit = evaluations["edit_correctness"]
            report.append(f"Status: {'✓ PASSED' if edit.get('passed') else '✗ FAILED'}")

            if "summary" in edit:
                summary = edit["summary"]
                report.append(f"Total Changes: {summary.get('total_changes', 0)}")
                report.append(f"Intended Changes: {summary.get('intended_changes', 0)}")
                report.append(f"Unintended Changes: {summary.get('unintended_changes', 0)}")

            if edit.get("issues"):
                report.append("\nIssues:")
                for issue in edit["issues"]:
                    report.append(f"  - {issue}")
            report.append("")

        report.append("=" * 70)
        report.append("END OF REPORT")
        report.append("=" * 70)

        return "\n".join(report)
