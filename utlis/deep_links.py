import urllib.parse
from datetime import datetime


class DeepLinkGenerator:

    @staticmethod
    def get_flight_link(origin: str, destination: str, travel_date: str) -> str:
        """
        Generates pre-filtered Google Flights URL.
        Opens Google Flights directly with origin, destination, and exact departure date.
        """
        base_url = "https://www.google.com/travel/flights"
        query_text = f"Flights to {destination.upper()} from {origin.upper()} on {travel_date}"
        encoded_query = urllib.parse.quote(query_text)
        return f"{base_url}?q={encoded_query}&curr=INR"

    @staticmethod
    def get_train_link(from_station: str, to_station: str, travel_date: str) -> str:
        """
        Generates ConfirmTkt / IRCTC direct booking search URL.
        Format required: DD-MM-YYYY
        """
        try:
            # Convert YYYY-MM-DD to DD-MM-YYYY
            dt = datetime.strptime(travel_date, "%Y-%m-%d")
            formatted_date = dt.strftime("%d-%m-%Y")
        except Exception:
            formatted_date = travel_date

        from_stn = from_station.upper()
        to_stn = to_station.upper()
        
        # ConfirmTkt pre-filled routing URL (seamless mobile + web)
        return f"https://www.confirmtkt.com/rbooking-d/trains/from/{from_stn}/to/{to_stn}?date={formatted_date}"

    @staticmethod
    def get_bus_link(from_city: str, to_city: str, travel_date: str) -> str:
        """
        Generates pre-filled RedBus query link.
        """
        from_slug = from_city.strip().lower().replace(" ", "-")
        to_slug = to_city.strip().lower().replace(" ", "-")
        return f"https://www.redbus.in/bus-tickets/{from_slug}-to-{to_slug}"