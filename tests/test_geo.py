from ww_geo import bearing, distance_km, distance_to_path_km, point_in_polygon


def test_distance_taipei_to_champi_position():
    assert 480 < distance_km(25.033, 121.565, 21.2, 125.0) < 560


def test_distance_across_the_dateline():
    assert distance_km(24.2, 180.0, 24.2, -179.2) < 100


def test_bearing_of_a_typhoon_southeast_of_taipei():
    assert bearing(25.033, 121.565, 21.2, 125.0) == "SE"


def test_distance_to_forecast_path():
    path = [(20.9, 125.4), (22.2, 124.3), (23.9, 123.3), (25.7, 122.8)]
    assert 100 < distance_to_path_km(24.83, 121.77, path) < 180  # 礁溪


def test_point_in_polygon():
    square = [(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)]
    assert point_in_polygon(5, 5, square) and not point_in_polygon(15, 5, square)


def test_point_in_polygon_across_the_antimeridian():
    ring = [(10, 179), (10, -179), (20, -179), (20, 179)]
    assert point_in_polygon(15, 179.5, ring) and point_in_polygon(15, -179.5, ring)
    assert not point_in_polygon(15, 178.5, ring) and not point_in_polygon(15, -178.5, ring)
    assert not point_in_polygon(15, 0, ring)


def test_point_in_polygon_ray_through_a_vertex():
    diamond = [(0, 5), (5, 10), (10, 5), (5, 0)]  # the ray at lat 5 passes exactly through two vertices
    assert point_in_polygon(5, 5, diamond)
    assert not point_in_polygon(5, -1, diamond) and not point_in_polygon(5, 11, diamond)


def test_distance_to_a_one_point_path_is_the_distance_to_that_point():
    assert abs(distance_to_path_km(25.033, 121.565, [(21.2, 125.0)]) - distance_km(25.033, 121.565, 21.2, 125.0)) < 15
