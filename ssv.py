import subprocess
import json
import os
from shapely.wkt import loads
from shapely.geometry import MultiLineString, LineString
from pyproj import Transformer

def split_bounding_box(bbox, grid_size):
    """
    Split a bounding box into smaller sub-boxes based on a grid size.
    bbox: Tuple of (min_x, min_y, max_x, max_y)
    grid_size: Number of sub-boxes to create along each axis (e.g., 2 for 2x2 grid).
    Returns a list of sub-boxes.
    """
    min_x, min_y, max_x, max_y = bbox
    x_step = (max_x - min_x) / grid_size
    y_step = (max_y - min_y) / grid_size

    sub_boxes = []
    for i in range(grid_size):
        for j in range(grid_size):
            sub_min_x = min_x + i * x_step
            sub_min_y = min_y + j * y_step
            sub_max_x = sub_min_x + x_step
            sub_max_y = sub_min_y + y_step
            sub_boxes.append((sub_min_x, sub_min_y, sub_max_x, sub_max_y))

    return sub_boxes

def fetch_nvdb_kartutsnitt(bbox):
    """
    Fetch data for a given bounding box (kartutsnitt) and save it to a JSON file.
    bbox: Tuple of (min_x, min_y, max_x, max_y).
    Returns a list of object IDs extracted from the response.
    """
    min_x, min_y, max_x, max_y = bbox
    curl_command = [
        "curl",
        "-X", "GET",
        "https://nvdbapiles-v3.atlas.vegvesen.no/vegobjekter/540",
        "-G",
        "--data", f"kartutsnitt={min_x},{min_y},{max_x},{max_y}",
        "--data", "kommune=5001",
        "--data", "segmentering=false",
        "--data", "inkluder=metadata,lokasjon,geometri",
        "-H", "accept: application/vnd.vegvesen.nvdb-v3-rev1+json, application/json",
        "-H", "x-client: Vegkart",
        "-H", "x-client-session: f494b285-ec81-436c-ae44-a852ecceab42"
    ]

    try:
        result = subprocess.run(curl_command, capture_output=True, text=True, check=True)
        response_json = json.loads(result.stdout)

        # Extract object IDs from the response
        object_ids = [obj["id"] for obj in response_json.get("objekter", [])]
        return object_ids

    except subprocess.CalledProcessError as e:
        print(f"Error occurred during kartutsnitt fetch: {e}")
    except json.JSONDecodeError:
        print("Failed to parse JSON response for kartutsnitt.")

    return []

def fetch_object_details(object_id):
    """
    Fetch details for a specific object by ID from the API or load it from the local file if it exists.
    """
    filename = f"data/svv/object_ids/{object_id}.json"

    # Check if the file already exists locally
    if os.path.exists(filename):
        # If file exists, load the data from the file
        with open(filename, "r", encoding="utf-8") as file:
            response_json = json.load(file)
        print(f"Object {object_id} loaded from {filename}")
    else:
        # If file doesn't exist, make the API call
        curl_command = [
            "curl", "-X", "GET",
            f"https://nvdbapiles-v3.atlas.vegvesen.no/vegobjekter/540/{object_id}/1",
            "-G",
            "--data-urlencode", "dybde=1",
            "--data-urlencode", "inkluder=lokasjon,metadata,egenskaper,relasjoner,geometri",
            "-H", "accept: application/vnd.vegvesen.nvdb-v3-rev1+json, application/json",
            "-H", "x-client: Vegkart",
            "-H", "x-client-session: f494b285-ec81-436c-ae44-a852ecceab42"
        ]

        try:
            result = subprocess.run(curl_command, capture_output=True, text=True, check=True)
            response_json = json.loads(result.stdout)

            # Save the response to a file
            with open(filename, "w", encoding="utf-8") as file:
                json.dump(response_json, file, ensure_ascii=False, indent=4)

            print(f"Object {object_id} details saved to {filename}")

        except subprocess.CalledProcessError as e:
            print(f"Error occurred while fetching object {object_id}: {e}")
            return None, None
        except json.JSONDecodeError:
            print(f"Failed to parse JSON response for object {object_id}.")
            return None, None

    # Extract geometry and ÅDT from the response (either from the API or local file)
    ådt_value = None
    geometry = None

    geometry = response_json["geometri"]["wkt"]

    # Extract ÅDT value (assuming it's part of 'egenskaper')
    for egenskap in response_json.get("egenskaper", []):
        
        if egenskap["id"] == 4623:
            ådt_value = egenskap["verdi"]

    return geometry, ådt_value

def generate_color(ådt_value, min_ådt, max_ådt):
    """
    Generate a color based on ÅDT value using a linear scale from min_ådt to max_ådt.
    The color will range from green (low ÅDT) to red (high ÅDT).
    """
    # Normalize the ÅDT value between 0 and 1
    norm_value = (ådt_value - min_ådt) / (max_ådt - min_ådt)

    # Interpolate to create a color: From green to red
    r = int(norm_value * 255)  # Red component (from 0 to 255)
    g = int((1 - norm_value) * 255)  # Green component (from 255 to 0)
    b = 0  # Blue component (fixed at 0 for red-green gradient)

    return f"rgb({r},{g},{b})"

def transform_coordinates(coords, transformer):
    """
    Transform a list of coordinates using the given transformer.
    Handles both 2D and 3D coordinates by ignoring the z-dimension.
    Input: [(x1, y1), (x2, y2), ...] or [(x1, y1, z1), ...]
    Output: [(lat1, lon1), (lat2, lon2), ...]
    """
    return [transformer.transform(x, y) for x, y, *_ in coords]

def generate_map(roads_data, input_crs="EPSG:32633", output_crs="EPSG:4326"):
    """
    Generate an HTML file with a Leaflet map displaying roads based on WKT geometry and ÅDT values.
    """
    # Create a transformer for coordinate systems
    transformer = Transformer.from_crs(input_crs, output_crs, always_xy=True)

    # Extract min and max ÅDT values
    ådt_values = [value for _, value in roads_data if value is not None]
    min_ådt = min(ådt_values) if ådt_values else 0
    max_ådt = max(ådt_values) if ådt_values else 10000  # Default max value if no ÅDT data

    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Road Map</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css"/>
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
    </head>
    <body>
        <div id="map" style="height: 1500px;"></div>
        <script>
            var map = L.map('map').setView([63.4305, 10.3951], 12);  // Example coordinates for Trondheim
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                opacity: 0.3  
            }).addTo(map);
    """

    # Loop through the roads data and add polylines
    for geometry, ådt_value in roads_data:
        if geometry is not None and ådt_value is not None:
            # Parse the WKT geometry to extract coordinates
            shape = loads(geometry)
            if shape.geom_type == "MultiLineString":
                for line in shape.geoms:  # Use .geoms to iterate over LineString components
                    transformed_coords = transform_coordinates(line.coords, transformer)
                    coordinates = [[lat, lon] for lon, lat in transformed_coords]
                    color = generate_color(ådt_value, min_ådt, max_ådt)
                    html_content += f"""
                        L.polyline({json.dumps(coordinates)}, {{
                            color: '{color}',
                            weight: 3,
                            opacity: 1.0
                        }}).addTo(map).bindPopup('ÅDT: {ådt_value}');
                    """
            elif shape.geom_type == "LineString":
                transformed_coords = transform_coordinates(shape.coords, transformer)
                coordinates = [[lat, lon] for lon, lat in transformed_coords]
                color = generate_color(ådt_value, min_ådt, max_ådt)
                html_content += f"""
                    L.polyline({json.dumps(coordinates)}, {{
                        color: '{color}',
                        weight: 3,
                        opacity: 1.0
                    }}).addTo(map).bindPopup('ÅDT: {ådt_value}');
                """

    html_content += """
        </script>
    </body>
    </html>
    """

    # Save the HTML file
    with open("output/svv-map.html", "w", encoding="utf-8") as file:
        file.write(html_content)
        print("Map HTML file generated as 'ssv-map.html'")
        
if __name__ == "__main__":
    # Create output directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/svv", exist_ok=True)

    # Define the initial bounding box
    initial_bbox = (250000,7000000,300000,7100000)

    # Split the bounding box into smaller sub-boxes (e.g., 2x2 grid)
    grid_size = 20
    sub_boxes = split_bounding_box(initial_bbox, grid_size)

    # Step 1: Fetch kartutsnitt for each sub-box and aggregate object IDs
    object_ids_file = "data/svv/all_object_ids.json"
    all_object_ids = []

    # Check if the object IDs file already exists
    if os.path.exists(object_ids_file):
        # Load the object IDs from the file
        with open(object_ids_file, "r", encoding="utf-8") as file:
            all_object_ids = json.load(file)
        print(f"Loaded object IDs from {object_ids_file}")
    else:
        for bbox in sub_boxes:
            print(f"Fetching data for sub-box: {bbox}")
            object_ids = fetch_nvdb_kartutsnitt(bbox)
            all_object_ids.extend(object_ids)

    # Remove duplicate object IDs (if any)
    all_object_ids = list(set(all_object_ids))

    # Save the object IDs to a JSON file
    with open(object_ids_file, "w", encoding="utf-8") as file:
        json.dump(all_object_ids, file, ensure_ascii=False, indent=4)
    print(f"Saved object IDs to {object_ids_file}")

    # Step 2: Fetch details for each object ID and collect geometry and ÅDT values
    roads_data = []
    for object_id in all_object_ids:
        geometry, ådt_value = fetch_object_details(object_id)
        if geometry and ådt_value is not None:
            roads_data.append((geometry, ådt_value))

    # Step 3: Generate the map
    generate_map(roads_data)