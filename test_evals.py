
import sys
import json
from app.evals import EvaluationRunner

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


SAMPLE_ITINERARY = """
I've created a 2-day travel plan for Paris. Explore iconic landmarks!


# Day 1: 2024-02-15 - Classic Paris
* Morning (9 AM - 12 PM): Visit the Eiffel Tower
* Afternoon (2 PM - 5 PM): Explore the Louvre Museum
* Evening (6 PM onwards): Dinner at restaurant

# Day 2: 2024-02-16 - Art & Culture
* Morning (9 AM - 12 PM): Tour Notre-Dame Cathedral
* Afternoon (2 PM - 5 PM): Walk through Montmartre
* Evening (6 PM onwards): Visit Sacré-Cœur Basilica

**Travel Tips:**
* The Paris Metro is efficient. [Source: Wikivoyage - Paris - Get Around]
* Book museum tickets in advance. [Source: Wikivoyage - Paris - See]
"""

# Sample search results
SEARCH_RESULTS = {
    "museum": [
        {"name": "Louvre Museum", "rating": 4.7, "source": "Foursquare"},
    ],
    "historical": [
        {"name": "Eiffel Tower", "lat": 48.8584, "lon": 2.2945, "source": "OSM"},
        {"name": "Notre-Dame Cathedral", "lat": 48.8530, "lon": 2.3499, "source": "OSM"},
        {"name": "Sacré-Cœur Basilica", "lat": 48.8867, "lon": 2.3431, "source": "OSM"},
    ]
}

TRAVEL_TIMES = {
    1: [25.0, 15.0],
    2: [20.0, 18.0],
}

def main():
    print("\n" + "=" * 70)
    print("Testing Voice Travel Agent Evaluation System")
    print("=" * 70 + "\n")

    runner = EvaluationRunner()

    # Run all evaluations
    print("Running comprehensive evaluation...")
    results = runner.run_all_evals(
        itinerary_text=SAMPLE_ITINERARY,
        context={
            "search_results": SEARCH_RESULTS,
            "travel_times": TRAVEL_TIMES,
        }
    )

    # Print results
    print("\n" + "=" * 70)
    print("EVALUATION RESULTS")
    print("=" * 70)

    overall = results["overall"]
    print(f"\nOverall Status: {'PASSED' if overall['all_passed'] else 'FAILED'}")
    print(f"Pass Rate: {overall['pass_rate']:.1f}%")
    print(f"Total Issues: {overall['total_issues']}")

    print("\n" + "-" * 70)
    print("Individual Evaluations:")
    print("-" * 70)

    for eval_name, eval_result in results["evaluations"].items():
        status = "PASSED" if eval_result.get("passed", False) else "FAILED"
        print(f"\n{eval_name.upper()}: {status}")

        if "summary" in eval_result:
            for key, value in eval_result["summary"].items():
                print(f"  - {key}: {value}")

        if "issues" in eval_result and eval_result["issues"]:
            print("  Issues:")
            for issue in eval_result["issues"]:
                print(f"    * {issue}")

    # Save results
    output_file = "evaluation_results.json"
    runner.save_results(results, output_file)
    print(f"\n\nDetailed results saved to: {output_file}")

    print("\n" + "=" * 70)
    print("Test Complete!")
    print("=" * 70)

if __name__ == "__main__":
    main()
