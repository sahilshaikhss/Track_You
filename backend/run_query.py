from model.effnet_cbir import EffNetCBIR

cbir_model = EffNetCBIR()
cbir_model.build_image_database("static/individual_photos")

query_path = "static/query_image/query.jpg"
results, distances = cbir_model.query_image(query_path)

print("Top matches:", results)
print("Distances:", distances)
cbir_model.visualize_results(query_path, results, distances)
from matplotlib import pyplot as plt
import numpy as np
