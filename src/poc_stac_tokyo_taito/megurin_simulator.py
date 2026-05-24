import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

logger = logging.getLogger(__name__)

def time_to_seconds(t_str: str) -> int:
    """Convert hh:mm:ss string to seconds from midnight."""
    try:
        parts = t_str.strip().split(":")
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s
    except Exception as e:
        logger.warning(f"Failed to parse time '{t_str}': {e}")
        return 0

def seconds_to_time(seconds: int) -> str:
    """Convert seconds from midnight to hh:mm:ss string."""
    h = (seconds // 3600) % 24
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

class MegurinSimulator:
    def __init__(self, megurin_dir: Path):
        self.megurin_dir = megurin_dir
        self.stops: Dict[str, Dict[str, Any]] = {}
        self.routes: Dict[str, Dict[str, Any]] = {}
        self.trips: Dict[str, Dict[str, Any]] = {}
        self.stop_times_by_trip: Dict[str, List[Dict[str, Any]]] = {}
        self.is_loaded = False
        self.load_gtfs()

    def load_gtfs(self):
        """Load and parse Megurin GTFS-JP text files."""
        try:
            self._load_stops()
            self._load_routes()
            self._load_trips()
            self._load_stop_times()
            self.is_loaded = True
            logger.info("Successfully loaded Megurin GTFS data for simulator.")
        except Exception as e:
            logger.error(f"Failed to load Megurin GTFS data: {e}", exc_info=True)
            self.is_loaded = False

    def _load_stops(self):
        path = self.megurin_dir / "stops.txt"
        if not path.exists():
            logger.error(f"stops.txt not found in {self.megurin_dir}")
            return
        
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stop_id = row["stop_id"]
                self.stops[stop_id] = {
                    "stop_name": row["stop_name"],
                    "lat": float(row["stop_lat"]),
                    "lon": float(row["stop_lon"])
                }
        logger.info(f"Loaded {len(self.stops)} stops from stops.txt")

    def _load_routes(self):
        path = self.megurin_dir / "routes.txt"
        if not path.exists():
            logger.error(f"routes.txt not found in {self.megurin_dir}")
            return
        
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                route_id = row["route_id"]
                # Default colors if missing
                route_color = row.get("route_color", "000000").strip()
                if not route_color:
                    route_color = "000000"
                self.routes[route_id] = {
                    "route_short_name": row.get("route_short_name", ""),
                    "route_long_name": row.get("route_long_name", ""),
                    "route_color": f"#{route_color}" if not route_color.startswith("#") else route_color
                }
        logger.info(f"Loaded {len(self.routes)} routes from routes.txt")

    def _load_trips(self):
        path = self.megurin_dir / "trips.txt"
        if not path.exists():
            logger.error(f"trips.txt not found in {self.megurin_dir}")
            return
        
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trip_id = row["trip_id"]
                self.trips[trip_id] = {
                    "route_id": row["route_id"],
                    "service_id": row["service_id"],
                    "trip_headsign": row.get("trip_headsign", "")
                }
        logger.info(f"Loaded {len(self.trips)} trips from trips.txt")

    def _load_stop_times(self):
        path = self.megurin_dir / "stop_times.txt"
        if not path.exists():
            logger.error(f"stop_times.txt not found in {self.megurin_dir}")
            return
        
        # Temporary structure to accumulate times, then sort
        temp_stop_times: Dict[str, List[Dict[str, Any]]] = {}
        
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trip_id = row["trip_id"]
                if trip_id not in temp_stop_times:
                    temp_stop_times[trip_id] = []
                
                temp_stop_times[trip_id].append({
                    "stop_id": row["stop_id"],
                    "arrival_seconds": time_to_seconds(row["arrival_time"]),
                    "departure_seconds": time_to_seconds(row["departure_time"]),
                    "stop_sequence": int(row["stop_sequence"]),
                    "arrival_time": row["arrival_time"],
                    "departure_time": row["departure_time"]
                })
        
        # Sort by stop_sequence for each trip
        for trip_id, stop_list in temp_stop_times.items():
            self.stop_times_by_trip[trip_id] = sorted(stop_list, key=lambda x: x["stop_sequence"])
            
        logger.info(f"Loaded stop_times for {len(self.stop_times_by_trip)} trips from stop_times.txt")

    def get_active_service_ids(self) -> List[str]:
        """Determine which service_ids are active today."""
        weekday = datetime.now().weekday()  # Monday is 0, Sunday is 6
        active = ["毎日"]
        if weekday in [5, 6]:  # Saturday, Sunday
            active.append("土日祝")
        else:
            active.append("平日")
        return active

    def get_bus_positions_geojson(self, current_seconds: int) -> Dict[str, Any]:
        """
        Simulate the bus positions at current_seconds.
        Returns a GeoJSON FeatureCollection.
        """
        features = []
        if not self.is_loaded:
            return {"type": "FeatureCollection", "features": []}

        active_services = self.get_active_service_ids()
        
        feature_id = 1
        for trip_id, trip_info in self.trips.items():
            # Filter trips active for today
            if trip_info["service_id"] not in active_services:
                continue

            # Get scheduled stops for this trip
            stop_times = self.stop_times_by_trip.get(trip_id)
            if not stop_times or len(stop_times) < 2:
                continue

            # Check if trip is currently running
            start_time = stop_times[0]["departure_seconds"]
            end_time = stop_times[-1]["arrival_seconds"]
            
            if not (start_time <= current_seconds <= end_time):
                continue  # Trip is not currently running
            
            # Find the current position (between stop i and stop i+1, or exactly at stop i)
            lon, lat = None, None
            props = {
                "trip_id": trip_id,
                "route_id": trip_info["route_id"],
                "trip_headsign": trip_info["trip_headsign"]
            }
            
            # Resolve route details
            route = self.routes.get(trip_info["route_id"], {})
            props["route_name"] = route.get("route_long_name", "めぐりん")
            props["route_color"] = route.get("route_color", "#888888")
            
            # Determine position
            # 1. Check if the bus is exactly at/inside a stop (停車中)
            at_stop = False
            for stop_time in stop_times:
                arr_sec = stop_time["arrival_seconds"]
                dep_sec = stop_time["departure_seconds"]
                if arr_sec <= current_seconds <= dep_sec:
                    # Bus is stopped at this stop
                    stop = self.stops.get(stop_time["stop_id"])
                    if stop:
                        lat, lon = stop["lat"], stop["lon"]
                        props["status"] = "stopped"
                        props["current_stop_id"] = stop_time["stop_id"]
                        props["current_stop_name"] = stop["stop_name"]
                        props["prev_stop_id"] = stop_time["stop_id"]
                        props["prev_stop_name"] = stop["stop_name"]
                        props["prev_stop_time"] = stop_time["departure_time"]
                        
                        # Find next stop
                        next_seq = stop_time["stop_sequence"] + 1
                        next_stop_time = next((s for s in stop_times if s["stop_sequence"] == next_seq), None)
                        if next_stop_time:
                            next_stop = self.stops.get(next_stop_time["stop_id"])
                            props["next_stop_id"] = next_stop_time["stop_id"]
                            props["next_stop_name"] = next_stop.get("stop_name", "") if next_stop else ""
                            props["next_stop_time"] = next_stop_time["arrival_time"]
                        else:
                            props["next_stop_id"] = ""
                            props["next_stop_name"] = "終点"
                            props["next_stop_time"] = ""
                            
                        at_stop = True
                        break
            
            # 2. Check if the bus is moving between stops (移動中)
            if not at_stop:
                for i in range(len(stop_times) - 1):
                    stop_curr = stop_times[i]
                    stop_next = stop_times[i+1]
                    
                    dep_sec = stop_curr["departure_seconds"]
                    arr_sec = stop_next["arrival_seconds"]
                    
                    if dep_sec <= current_seconds <= arr_sec:
                        # Moving between stop i and stop i+1
                        duration = arr_sec - dep_sec
                        ratio = 0.0
                        if duration > 0:
                            ratio = (current_seconds - dep_sec) / duration
                        
                        curr_stop = self.stops.get(stop_curr["stop_id"])
                        next_stop = self.stops.get(stop_next["stop_id"])
                        
                        if curr_stop and next_stop:
                            lat = curr_stop["lat"] + (next_stop["lat"] - curr_stop["lat"]) * ratio
                            lon = curr_stop["lon"] + (next_stop["lon"] - curr_stop["lon"]) * ratio
                            
                            props["status"] = "moving"
                            props["prev_stop_id"] = stop_curr["stop_id"]
                            props["prev_stop_name"] = curr_stop["stop_name"]
                            props["prev_stop_time"] = stop_curr["departure_time"]
                            props["next_stop_id"] = stop_next["stop_id"]
                            props["next_stop_name"] = next_stop["stop_name"]
                            props["next_stop_time"] = stop_next["arrival_time"]
                            props["progress"] = ratio
                            
                            break

            if lat is not None and lon is not None:
                features.append({
                    "type": "Feature",
                    "id": feature_id,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    },
                    "properties": props
                })
                feature_id += 1

        return {
            "type": "FeatureCollection",
            "features": features
        }
