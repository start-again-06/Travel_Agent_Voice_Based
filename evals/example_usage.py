
"""Example usage of the evaluation system."""
import logging
from app.evals.runner import EvaluationRunner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Sample itinerary for testing
SAMPLE_ITINERARY = """
I've created a 2-day travel plan for Paris. Explore iconic landmarks and French cuisine!

---ITINERARY---
# Day 1: 2024-02-15 - Classic Paris
* Morning (9 AM - 12 PM): Visit the Eiffel Tower
* Afternoon (2 PM - 5 PM): Explore the Louvre Museum
* Evening (6 PM onwards): Dinner at a Champs-Élysées restaurant

# Day 2: 2024-02-16 - Art & Culture
* Morning (9 AM - 12 PM): Tour Notre-Dame Cathedral
* Afternoon (2 PM - 5 PM): Walk through Montmartre
* Evening (6 PM onwards): Visit Sacré-Cœur Basilica

**Travel Tips:**
* The Paris Metro is efficient for getting around. [Source: Wikivoyage - Paris - Get Around]
* Book museum tickets in advance to avoid long queues. [Source: Wikivoyage - Paris - See]
* May experience rain in February, bring an umbrella.
"""

# Sample search results (what the agent retrieved)
SAMPLE_SEARCH_RESULTS = {
    "museum": [
        {"name": "Louvre Museum", "rating": 4.7, "source": "Foursquare"},
        {"name": "Musée d'Orsay", "rating": 4.8, "source": "Foursquare"},
    ],
    "restaurant": [
        {"name": "Le Jules Verne", "rating": 4.5, "source": "Foursquare"},
        {"name": "L'Atelier de Joël Robuchon", "rating": 4.6, "source": "Foursquare"},
    ],
    "historical": [
        {"name": "Eiffel Tower", "lat": 48.8584, "lon": 2.2945, "source": "OpenStreetMap"},
        {"name": "Notre-Dame Cathedral", "lat": 48.8530, "lon": 2.3499, "source": "OpenStreetMap"},
        {"name": "Sacré-Cœur Basilica", "lat": 48.8867, "lon": 2.3431, "source": "OpenStreetMap"},
    ]
}

# Sample travel times (in minutes) between activities for each day
SAMPLE_TRAVEL_TIMES = {
    1: [25.0, 15.0],  # Day 1: Eiffel Tower -> Louvre (25 min), Louvre -> Champs-Élysées (15 min)
    2: [20.0, 18.0],  # Day 2: Notre-Dame -> Montmartre (20 min), Montmartre -> Sacré-Cœur (18 min)
}


def example_full_evaluation():
    """Run a full evaluation with all checks."""
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Full Evaluation")
    print("=" * 70)

    runner = EvaluationRunner()

    # Run all evaluations
    results = runner.run_all_evals(
        itinerary_text=SAMPLE_ITINERARY,
        context={
            "search_results": SAMPLE_SEARCH_RESULTS,
            "travel_times": SAMPLE_TRAVEL_TIMES,
        }
    )

    # Generate and print report
    report = runner.generate_report(results)
    print("\n" + report)

    # Save results to file
    runner.save_results(results, "eval_results.json")


def example_feasibility_only():
    """Run only feasibility evaluation."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: Feasibility Evaluation Only")
    print("=" * 70)

    runner = EvaluationRunner()

    # Run feasibility evaluation
    results = runner.run_feasibility_eval(
        itinerary_text=SAMPLE_ITINERARY,
        travel_times=SAMPLE_TRAVEL_TIMES
    )

    print("\nFeasibility Results:")
    print(f"Passed: {results['passed']}")
    print(f"Summary: {results['summary']}")


def example_grounding_only():
    """Run only grounding evaluation."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Grounding Evaluation Only")
    print("=" * 70)

    runner = EvaluationRunner()

    # Run grounding evaluation
    results = runner.run_grounding_eval(
        itinerary_text=SAMPLE_ITINERARY,
        search_results=SAMPLE_SEARCH_RESULTS
    )

    print("\nGrounding Results:")
    print(f"Passed: {results['passed']}")
    print(f"Summary: {results['summary']}")

    # Show POI grounding details
    for result in results['results']:
        if result['check'] == 'poi_grounding':
            print(f"\nPOI Grounding Rate: {result['grounding_percentage']:.1f}%")
            print(f"Grounded POIs: {result['grounded_pois']}")
            print(f"Ungrounded POIs: {result['ungrounded_pois']}")


def example_edit_correctness():
    """Run edit correctness evaluation."""
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Edit Correctness Evaluation")
    print("=" * 70)

    runner = EvaluationRunner()

    # Simulate an edit
    ORIGINAL_ITINERARY = SAMPLE_ITINERARY
    EDITED_ITINERARY = SAMPLE_ITINERARY.replace(
        "* Afternoon (2 PM - 5 PM): Explore the Louvre Museum",
        "* Afternoon (2 PM - 5 PM): Visit Musée d'Orsay"
    )

    # Run edit correctness evaluation
    results = runner.run_edit_correctness_eval(
        original_itinerary=ORIGINAL_ITINERARY,
        edited_itinerary=EDITED_ITINERARY,
        edit_instruction="Change the afternoon activity on Day 1 to Musée d'Orsay"
    )

    print("\nEdit Correctness Results:")
    print(f"Passed: {results['passed']}")
    print(f"Summary: {results['summary']}")
    print(f"Total Changes: {results['summary']['total_changes']}")
    print(f"Unintended Changes: {results['summary']['unintended_changes']}")


if __name__ == "__main__":
    # Run all examples
    example_full_evaluation()
    example_feasibility_only()
    example_grounding_only()
    example_edit_correctness()

    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)
