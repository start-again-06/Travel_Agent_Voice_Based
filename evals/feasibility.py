
"""Feasibility evaluation for itineraries.

Checks:
1. Daily duration ≤ available time
2. Reasonable travel times between activities
3. Pace consistency (not too rushed or too slow)
"""
import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger("evals.feasibility")


class FeasibilityEval:
    """Evaluates itinerary feasibility."""

    # Time windows for activities (in hours)
    TIME_WINDOWS = {
        "morning": {"start": 9, "end": 12, "duration": 3},
        "afternoon": {"start": 14, "end": 17, "duration": 3},
        "evening": {"start": 18, "end": 22, "duration": 4},
    }

    # Thresholds
    MAX_TRAVEL_TIME_MINUTES = 60  # Max reasonable travel between activities
    MIN_ACTIVITY_DURATION_MINUTES = 30  # Min time at each activity
    MAX_ACTIVITIES_PER_DAY = 10  # Max activities in a single day
    IDEAL_ACTIVITIES_PER_DAY = 6  # Ideal number of activities

    def __init__(self):
        self.results = []

    def parse_itinerary(self, itinerary_text: str) -> List[Dict[str, Any]]:
        """
        Parse itinerary text to extract structured day plans.

        Args:
            itinerary_text: Raw itinerary markdown text

        Returns:
            List of day plans with activities
        """
        days = []
        current_day = None

        # Split by lines
        lines = itinerary_text.split('\n')

        for line in lines:
            line = line.strip()

            # Match day headers: # Day 1: 2024-01-15 - Theme
            day_match = re.match(r'^#\s*Day\s+(\d+):\s*(.+?)\s*-\s*(.+)', line)
            if day_match:
                if current_day:
                    days.append(current_day)

                day_num = int(day_match.group(1))
                date_str = day_match.group(2).strip()
                theme = day_match.group(3).strip()

                current_day = {
                    "day": day_num,
                    "date": date_str,
                    "theme": theme,
                    "activities": []
                }

            # Match activities: * Morning (9 AM - 12 PM): Activity description
            # Or: * Morning: Activity description
            activity_match = re.match(
                r'^\*\s*(Morning|Afternoon|Evening)(?:\s*\(([^)]+)\))?\s*:\s*(.+)',
                line,
                re.IGNORECASE
            )
            if activity_match and current_day:
                time_period = activity_match.group(1).lower()
                time_range = activity_match.group(2)
                description = activity_match.group(3).strip()

                activity = {
                    "time_period": time_period,
                    "time_range": time_range,
                    "description": description,
                }

                current_day["activities"].append(activity)

        # Add last day
        if current_day:
            days.append(current_day)

        return days

    def check_daily_duration(self, day_plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if daily activities fit within available time.

        Args:
            day_plan: Single day's plan

        Returns:
            Evaluation result
        """
        activities = day_plan.get("activities", [])
        total_time_periods = len(activities)

        issues = []

        # Check if we have activities in time slots
        time_periods_used = set()
        for activity in activities:
            time_period = activity.get("time_period", "").lower()
            if time_period in self.TIME_WINDOWS:
                time_periods_used.add(time_period)

        # Calculate total available hours
        total_available_hours = sum(
            self.TIME_WINDOWS[period]["duration"]
            for period in time_periods_used
        )

        # Check if too many activities
        if total_time_periods > self.MAX_ACTIVITIES_PER_DAY:
            issues.append(
                f"Too many activities ({total_time_periods}). "
                f"Max recommended: {self.MAX_ACTIVITIES_PER_DAY}"
            )

        # Check if duplicate time periods (multiple activities in same slot)
        time_period_counts = {}
        for activity in activities:
            period = activity.get("time_period", "").lower()
            time_period_counts[period] = time_period_counts.get(period, 0) + 1

        for period, count in time_period_counts.items():
            if count > 1:
                issues.append(
                    f"Multiple activities ({count}) scheduled for {period}. "
                    "This may be too rushed."
                )

        return {
            "day": day_plan.get("day"),
            "date": day_plan.get("date"),
            "check": "daily_duration",
            "passed": len(issues) == 0,
            "total_activities": total_time_periods,
            "total_available_hours": total_available_hours,
            "issues": issues,
        }

    def check_travel_times(
        self,
        day_plan: Dict[str, Any],
        travel_time_estimates: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Check if travel times between activities are reasonable.

        Args:
            day_plan: Single day's plan
            travel_time_estimates: Optional list of travel times in minutes

        Returns:
            Evaluation result
        """
        activities = day_plan.get("activities", [])
        issues = []

        # If travel time estimates provided, validate them
        if travel_time_estimates:
            for i, travel_time in enumerate(travel_time_estimates):
                if travel_time > self.MAX_TRAVEL_TIME_MINUTES:
                    issues.append(
                        f"Travel time between activity {i+1} and {i+2} "
                        f"is {travel_time:.1f} minutes. "
                        f"Max recommended: {self.MAX_TRAVEL_TIME_MINUTES} minutes."
                    )
        else:
            # Without actual estimates, check if activities have locations
            has_locations = any(
                "lat" in str(activity) or "location" in str(activity).lower()
                for activity in activities
            )

            if not has_locations and len(activities) > 3:
                issues.append(
                    "No location data found for activities. "
                    "Unable to verify travel times."
                )

        return {
            "day": day_plan.get("day"),
            "date": day_plan.get("date"),
            "check": "travel_times",
            "passed": len(issues) == 0,
            "travel_estimates": travel_time_estimates or [],
            "issues": issues,
        }

    def check_pace_consistency(self, day_plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if the day's pace is consistent and reasonable.

        Args:
            day_plan: Single day's plan

        Returns:
            Evaluation result
        """
        activities = day_plan.get("activities", [])
        num_activities = len(activities)
        issues = []

        # Check if too few activities (underplanned)
        if num_activities < 2:
            issues.append(
                f"Only {num_activities} activity planned. "
                "Consider adding more activities for a full day."
            )

        # Check if pace is too rushed
        elif num_activities > self.IDEAL_ACTIVITIES_PER_DAY:
            issues.append(
                f"{num_activities} activities may be too rushed. "
                f"Ideal: {self.IDEAL_ACTIVITIES_PER_DAY} or fewer per day."
            )

        # Check for balanced distribution across time periods
        time_periods = [a.get("time_period", "").lower() for a in activities]
        morning_count = time_periods.count("morning")
        afternoon_count = time_periods.count("afternoon")
        evening_count = time_periods.count("evening")

        # Warn if only one time period is used
        periods_used = sum([
            1 for count in [morning_count, afternoon_count, evening_count]
            if count > 0
        ])

        if periods_used == 1 and num_activities > 1:
            issues.append(
                "All activities are in the same time period. "
                "Consider spreading across morning, afternoon, and evening."
            )

        return {
            "day": day_plan.get("day"),
            "date": day_plan.get("date"),
            "check": "pace_consistency",
            "passed": len(issues) == 0,
            "num_activities": num_activities,
            "morning_activities": morning_count,
            "afternoon_activities": afternoon_count,
            "evening_activities": evening_count,
            "issues": issues,
        }

    def evaluate(
        self,
        itinerary_text: str,
        travel_times: Optional[Dict[int, List[float]]] = None
    ) -> Dict[str, Any]:
        """
        Run all feasibility checks on the itinerary.

        Args:
            itinerary_text: Raw itinerary markdown text
            travel_times: Optional dict mapping day number to travel times list

        Returns:
            Complete evaluation results
        """
        logger.info("Running Feasibility Evaluation...")

        # Parse itinerary
        days = self.parse_itinerary(itinerary_text)

        if not days:
            return {
                "eval_type": "feasibility",
                "passed": False,
                "error": "Could not parse itinerary",
                "results": []
            }

        all_results = []
        all_passed = True

        # Run checks for each day
        for day_plan in days:
            day_num = day_plan.get("day")

            # Check 1: Daily duration
            duration_result = self.check_daily_duration(day_plan)
            all_results.append(duration_result)
            if not duration_result["passed"]:
                all_passed = False

            # Check 2: Travel times
            day_travel_times = None
            if travel_times and day_num in travel_times:
                day_travel_times = travel_times[day_num]

            travel_result = self.check_travel_times(day_plan, day_travel_times)
            all_results.append(travel_result)
            if not travel_result["passed"]:
                all_passed = False

            # Check 3: Pace consistency
            pace_result = self.check_pace_consistency(day_plan)
            all_results.append(pace_result)
            if not pace_result["passed"]:
                all_passed = False

        # Summary
        summary = {
            "total_days": len(days),
            "total_checks": len(all_results),
            "passed_checks": sum(1 for r in all_results if r["passed"]),
            "failed_checks": sum(1 for r in all_results if not r["passed"]),
        }

        return {
            "eval_type": "feasibility",
            "passed": all_passed,
            "summary": summary,
            "results": all_results,
        }
