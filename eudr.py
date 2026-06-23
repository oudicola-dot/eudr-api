import ee

# ----------------------------
# INIT EE
# ----------------------------
def init_ee(project_id):
    ee.Initialize(project=project_id)


# ----------------------------
# AREA
# ----------------------------
def get_area(lat, lon, radius=1000):
    point = ee.Geometry.Point([lon, lat])
    return point.buffer(radius)


# ----------------------------
# FOREST 2020 (FIX SAFE DATASET)
# ----------------------------
def forest_2020(area):

    img = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")

    treecover = img.select("treecover2000")

    value = treecover.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=area,
        scale=30
    ).get("treecover2000")

    return value.getInfo()


# ----------------------------
# NDVI CURRENT (SAFE SENTINEL)
# ----------------------------
def ndvi_current(area):

    img = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
        .filterBounds(area) \
        .filterDate("2023-01-01", "2025-01-01") \
        .median()

    ndvi = img.normalizedDifference(["B8", "B4"])

    value = ndvi.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=area,
        scale=10
    ).get("nd")

    # FIX SAFE
    if value is None:
        return 0

    return value.getInfo()


# ----------------------------
# DEFORESTATION AFTER 2020
# ----------------------------
def deforestation_after_2020(area):

    img = ee.Image("UMD/hansen/global_forest_change_2025_v1_13")

    loss = img.select("lossyear")

    # years > 20 = post 2020
    post2020 = loss.gt(20)

    value = post2020.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=area,
        scale=30
    ).get("lossyear")

    if value is None:
        return 0

    return value.getInfo()