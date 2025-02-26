from shapely.geometry import Polygon
import osmnx as ox
import networkx as nx
import matplotlib.pyplot as plt


use_all_of_trondheim = False
remove_bridge = True
place_name = "Trondheim, Norway"

# Define a polygon (Example: central Trondheim area)
polygon = Polygon([
    (10.35, 63.41),  # Southwest corner
    (10.42, 63.41),  # Southeast
    (10.42, 63.44),  # Northeast
    (10.35, 63.44),  # Northwest
])

# TRUE use_all_of_trondheim is true, use the whole area of Trondheim
# 
if use_all_of_trondheim:
    G = ox.graph_from_place(place_name, network_type='drive', simplify=True)
else:
    G = ox.graph_from_polygon(polygon, network_type='drive', simplify=True)


# If remove bridge is true Remove Elgeseter Bridge from the map
if remove_bridge:
    north_end_coords = (10.3955, 63.4284)  # Midtbyen side
    south_end_coords = (10.3965, 63.4261)  # Elgeseter side

    # Find the nearest nodes in the graph
    north_node = 3051860254 
    south_node = 54465660
    
    print(f"North End Node: {north_node}")
    print(f"South End Node: {south_node}")

    # Find all edges along the bridge
    edges_to_remove = []
    for u, v, key in G.edges(keys=True):
        if (u == north_node or v == north_node) or (u == south_node or v == south_node):
            edges_to_remove.append((u, v, key))

    # Remove edges
    for edge in edges_to_remove:
        try:
            G.remove_edge(*edge)
            print(f"Removed edge: {edge}")
        except Exception as e:
            print(f"Could not remove edge {edge}: {e}")
        
G_undirected = nx.Graph(G)

# Calculate centrality measures
node_centrality = nx.betweenness_centrality(G_undirected)
# Get the top 5 nodes by centrality
top_nodes = sorted(node_centrality.items(), key=lambda x: x[1], reverse=True)[:5]
# Color the nodes according to their centrality
node_color = [node_centrality.get(node, 0) for node in G.nodes()]

fig, ax = ox.plot_graph(
    G, 
    node_color=node_color, 
    node_size=20,
    edge_linewidth=1.5
)