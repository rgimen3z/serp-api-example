from __future__ import annotations

import argparse
import json
import os
import sys
from calendar import monthrange
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


SERPAPI_ENDPOINT = "https://serpapi.com/search"


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            os.environ.setdefault(key, value)


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day)


def parse_args() -> argparse.Namespace:
    default_outbound = add_months(date.today(), 3)
    default_return = default_outbound + timedelta(days=14)

    parser = argparse.ArgumentParser(
        description=(
            "Search SerpApi Google Flights for flights from San Diego to Madrid, "
            "defaulting to a round trip three months from today."
        )
    )
    parser.add_argument("--from", dest="departure_id", default="SAN", help="Departure airport code.")
    parser.add_argument("--to", dest="arrival_id", default="MAD", help="Arrival airport code.")
    parser.add_argument(
        "--outbound-date",
        default=default_outbound.isoformat(),
        help="Outbound date in YYYY-MM-DD format. Defaults to three months from today.",
    )
    parser.add_argument(
        "--return-date",
        default=default_return.isoformat(),
        help="Return date in YYYY-MM-DD format. Defaults to 14 days after outbound.",
    )
    parser.add_argument(
        "--one-way",
        action="store_true",
        help="Search one-way flights instead of a round trip.",
    )
    parser.add_argument("--adults", type=int, default=1, help="Number of adult passengers.")
    parser.add_argument("--currency", default="USD", help="Currency code for returned prices.")
    parser.add_argument("--travel-class", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--max-results", type=int, default=10, help="Maximum flights to print.")
    parser.add_argument(
        "--outbound-candidates",
        type=int,
        default=3,
        help="Round-trip only: number of top outbound flights to fetch return options for.",
    )
    parser.add_argument(
        "--return-options",
        type=int,
        default=2,
        help="Round-trip only: number of return flights to print per outbound flight.",
    )
    parser.add_argument(
        "--deep-search",
        action="store_true",
        help="Ask SerpApi for Google Flights browser-equivalent results. Slower.",
    )
    parser.add_argument(
        "--show-hidden",
        action="store_true",
        help="Include hidden Google Flights results.",
    )
    parser.add_argument(
        "--save-json",
        help="Optional path to save the full SerpApi JSON response.",
    )
    return parser.parse_args()


def build_params(args: argparse.Namespace, api_key: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "engine": "google_flights",
        "api_key": api_key,
        "departure_id": args.departure_id,
        "arrival_id": args.arrival_id,
        "outbound_date": args.outbound_date,
        "currency": args.currency,
        "hl": "en",
        "gl": "us",
        "type": "2" if args.one_way else "1",
        "travel_class": args.travel_class,
        "adults": args.adults,
        "sort_by": "1",
    }

    if not args.one_way:
        params["return_date"] = args.return_date
    if args.deep_search:
        params["deep_search"] = "true"
    if args.show_hidden:
        params["show_hidden"] = "true"

    return params


def build_return_params(params: dict[str, Any], departure_token: str) -> dict[str, Any]:
    return {
        key: value
        for key, value in params.items()
        if key
        in {
            "engine",
            "api_key",
            "departure_id",
            "arrival_id",
            "outbound_date",
            "return_date",
            "currency",
            "hl",
            "gl",
            "type",
            "travel_class",
            "adults",
            "deep_search",
        }
    } | {"departure_token": departure_token}


def fetch_flights(params: dict[str, Any]) -> dict[str, Any]:
    url = f"{SERPAPI_ENDPOINT}?{urlencode(params)}"
    with urlopen(url, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def minutes_to_duration(minutes: int | None) -> str:
    if minutes is None:
        return "unknown duration"
    hours, remainder = divmod(minutes, 60)
    return f"{hours}h {remainder}m"


def format_leg(leg: dict[str, Any]) -> str:
    departure = leg.get("departure_airport", {})
    arrival = leg.get("arrival_airport", {})
    flight_number = leg.get("flight_number", "unknown flight")
    airline = leg.get("airline", "Unknown airline")
    dep_id = departure.get("id", "?")
    arr_id = arrival.get("id", "?")
    dep_time = departure.get("time", "unknown departure")
    arr_time = arrival.get("time", "unknown arrival")
    duration = minutes_to_duration(leg.get("duration"))
    return f"    {flight_number} {airline}: {dep_id} {dep_time} -> {arr_id} {arr_time} ({duration})"


def format_flight(index: int, flight: dict[str, Any]) -> str:
    price = flight.get("price")
    price_display = f"${price:,}" if isinstance(price, int) else "price unavailable"
    total_duration = minutes_to_duration(flight.get("total_duration"))
    stops = max(len(flight.get("flights", [])) - 1, 0)
    emissions = flight.get("carbon_emissions", {}).get("difference_percent")
    emission_display = f", emissions {emissions:+d}% vs typical" if isinstance(emissions, int) else ""

    lines = [
        f"{index}. {price_display} | {total_duration} | {stops} stop{'s' if stops != 1 else ''}{emission_display}"
    ]
    lines.extend(format_leg(leg) for leg in flight.get("flights", []))
    return "\n".join(lines)


def all_flights(results: dict[str, Any]) -> list[dict[str, Any]]:
    return [*results.get("best_flights", []), *results.get("other_flights", [])]


def print_search_header(results: dict[str, Any]) -> None:
    if error := results.get("error"):
        raise RuntimeError(error)

    metadata = results.get("search_metadata", {})
    status = metadata.get("status", "unknown")
    google_url = metadata.get("google_flights_url")
    parameters = results.get("search_parameters", {})

    print(f"Search status: {status}")
    print(
        "Route: "
        f"{parameters.get('departure_id', '?')} -> {parameters.get('arrival_id', '?')} | "
        f"Outbound: {parameters.get('outbound_date', '?')} | "
        f"Return: {parameters.get('return_date', 'one-way')}"
    )
    if google_url:
        print(f"Google Flights URL: {google_url}")
    print()


def print_results(results: dict[str, Any], max_results: int) -> None:
    print_search_header(results)

    flights = all_flights(results)
    if not flights:
        print("No flights found.")
        return

    for index, flight in enumerate(flights[:max_results], start=1):
        print(format_flight(index, flight))
        print()


def print_round_trip_results(
    departure_results: dict[str, Any], params: dict[str, Any], outbound_candidates: int, return_options: int
) -> None:
    print_search_header(departure_results)

    departures = all_flights(departure_results)
    if not departures:
        print("No departure flights found.")
        return

    for index, departure in enumerate(departures[:outbound_candidates], start=1):
        print(f"Outbound option {index}")
        print(format_flight(index, departure))

        departure_token = departure.get("departure_token")
        if not departure_token:
            print("  No departure_token returned, so return options could not be fetched.")
            print()
            continue

        return_results = fetch_flights(build_return_params(params, departure_token))
        returns = all_flights(return_results)

        if not returns:
            print("  No return flights found for this outbound option.")
            print()
            continue

        print("  Return options:")
        for return_index, return_flight in enumerate(returns[:return_options], start=1):
            formatted = format_flight(return_index, return_flight)
            print("\n".join(f"  {line}" for line in formatted.splitlines()))
        print()


def main() -> int:
    load_env_file()
    args = parse_args()
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key or api_key == "your_serpapi_private_key_here":
        print("Missing SERPAPI_API_KEY. Add your private SerpApi key to .env before running this script.", file=sys.stderr)
        return 2

    params = build_params(args, api_key)
    results = fetch_flights(params)

    if args.save_json:
        with open(args.save_json, "w", encoding="utf-8") as file:
            json.dump(results, file, indent=2)
            file.write("\n")

    if args.one_way:
        print_results(results, args.max_results)
    else:
        print_round_trip_results(results, params, args.outbound_candidates, args.return_options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
