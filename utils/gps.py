import math


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """回傳兩個座標之間的距離（公尺）"""
    R = 6_371_000  # 地球半徑（公尺）
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
