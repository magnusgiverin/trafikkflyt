import os
import json
import pandas as pd
import geopandas as gpd
from shapely.wkt import loads


class TeliaDataProcessor:
    def __init__(self, 
                 daily_folder="data/telia/daily", 
                 hourly_folder="data/telia/hourly", 
                 shapefile_path="data/telia/shapefile/flux_trondheim.shp", 
                 output_html="output/telia-map.html"):
        """
        Parametre:
          daily_folder: Mappebane til daglige Telia-data (CSV-filer)
          hourly_folder: Mappebane til timelige Telia-data (CSV-filer)
          shapefile_path: Filbane til Shapefile som inneholder vei-geometri
          output_html: Filbane for generert Leaflet-kart (HTML)
        """
        self.daily_folder = daily_folder
        self.hourly_folder = hourly_folder
        self.shapefile_path = shapefile_path
        self.output_html = output_html

        self.daily_data = None
        self.hourly_data = None
        self.way_mapping = None
        self.telia_summary = None
        self.combined_df = None

    def load_telia_data(self):
        """Laster alle CSV-filer i de oppgitte mappene og kombinerer dem til én DataFrame per type."""
        
        def load_csvs_from_folder(folder):
            """Hjelpefunksjon for å finne og slå sammen alle CSV-filer i en mappe."""
            if not os.path.exists(folder):
                raise FileNotFoundError(f"Mappen {folder} eksisterer ikke.")

            csv_files = [f for f in os.listdir(folder) if f.endswith(".csv")]
            if not csv_files:
                raise FileNotFoundError(f"Ingen CSV-filer funnet i {folder}")
            
            df_list = []
            for file in csv_files:
                file_path = os.path.join(folder, file)
                df = pd.read_csv(file_path, sep=";")  # Juster separator hvis nødvendig
                df_list.append(df)

            return pd.concat(df_list, ignore_index=True)

        # Laste daglige data
        self.daily_data = load_csvs_from_folder(self.daily_folder)
        print(f"✅ Lastet inn {len(self.daily_data)} rader fra daglige Telia-data.")

        # Laste timelige data
        self.hourly_data = load_csvs_from_folder(self.hourly_folder)
        print(f"✅ Lastet inn {len(self.hourly_data)} rader fra timelige Telia-data.")

    def load_shapefile(self):
        """Laster inn Shapefile med veigeometri og `way_id`."""
        if not os.path.exists(self.shapefile_path):
            raise FileNotFoundError(f"❌ Shapefile {self.shapefile_path} eksisterer ikke!")

        gdf = gpd.read_file(self.shapefile_path)
        print(f"✅ Lastet inn {len(gdf)} veier fra Shapefile.")

        # Se etter riktig kolonne for `way_id`
        way_id_column = "way_id" if "way_id" in gdf.columns else gdf.columns[0]  # Anta første kolonne hvis ikke eksplisitt way_id
        self.way_mapping = gdf[[way_id_column, "geometry"]]

        print(f"📌 Bruker '{way_id_column}' som way_id.")
        return self.way_mapping

    def aggregate_telia_data(self):
        """Organizes Telia-data per way_id and hour."""
        if self.hourly_data is None:
            raise Exception("🚨 Kjør først load_telia_data() for å laste inn CSV-filene.")

        self.telia_summary = (
            self.hourly_data.groupby(["way_id", "hour"])["people"]
            .mean()
            .reset_index()
        )
        return self.telia_summary

    def merge_data(self):
        """Slår sammen Telia-data med vei-geometri basert på way_id."""
        if self.telia_summary is None:
            raise Exception("🚨 Kjør aggregate_telia_data() før sammenslåing.")
        if self.way_mapping is None:
            self.load_shapefile()

        self.combined_df = pd.merge(self.way_mapping, self.telia_summary, on="way_id", how="left")
        print("🔗 Data slått sammen:")
        print(self.combined_df.head())
        return self.combined_df

    def generate_map(self):
        """Genererer et Leaflet-kart med en slider for time-based traffic visualization."""
        if self.combined_df is None:
            raise Exception("🚨 Kjør merge_data() før kartgenerering.")

        min_val = self.combined_df["people"].min()
        max_val = self.combined_df["people"].max()

        def generate_color(val):
            """Genererer en farge fra grønn til rød basert på trafikkmengde."""
            norm_value = (val - min_val) / (max_val - min_val) if max_val > min_val else 0
            r = int(norm_value * 255)
            g = int((1 - norm_value) * 255)
            return f"rgb({r},{g},0)"

        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Telia Traffic Flow</title>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css"/>
            <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        </head>
        <body>
            <input id="hour-slider" type="range" min="0" max="23" value="0" step="1" style="width: 100%;">
            <p>Hour: <span id="current-hour">0</span></p>
            <div id="map" style="height: 100vh;"></div>
            <script>
                var map = L.map('map').setView([63.4305, 10.3951], 12);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

                var layers = {};
        """

        for hour in range(24):
            html_content += f"layers[{hour}] = L.layerGroup([]);\n"

        for _, row in self.combined_df.iterrows():
            if pd.notna(row["geometry"]) and pd.notna(row["people"]):
                shape = row["geometry"]
                coordinates = [[y, x] for x, y in shape.coords]
                color = generate_color(row["people"])
                hour = int(row["hour"])
                html_content += f"""
                    L.polyline({json.dumps(coordinates)}, {{ color: '{color}', weight: 3, opacity: 1.0 }}).addTo(layers[{hour}]);
                """

        html_content += """
                map.addLayer(layers[0]);

                document.getElementById('hour-slider').addEventListener('input', function(e) {
                    var selectedHour = e.target.value;
                    document.getElementById('current-hour').innerText = selectedHour;

                    for (var h = 0; h < 24; h++) {
                        if (map.hasLayer(layers[h])) {
                            map.removeLayer(layers[h]);
                        }
                    }
                    map.addLayer(layers[selectedHour]);
                });
            </script>
        </body>
        </html>
        """

        with open(self.output_html, "w") as file:
            file.write(html_content)

        print(f"✅ Generert kart med time-slider i {self.output_html}")


# 🚀 **Kjør klassen**
if __name__ == "__main__":
    processor = TeliaDataProcessor()
    processor.load_telia_data()
    processor.aggregate_telia_data()
    processor.load_shapefile()
    processor.merge_data()
    processor.generate_map()