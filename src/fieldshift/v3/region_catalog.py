"""Illustrative operational planning zones, NOT official AEZ polygons.

Every zone intentionally discloses whether a nearby archived POWER *point*
exists. The catalog must not be used for point-in-polygon decisions until the
published BAMIS/BARC AEZ GIS polygons and a versioned crosswalk are imported.
"""
from __future__ import annotations

from typing import Any

AEZ_REFERENCE = 'https://www.bamis.gov.bd/en/page/aezs-maps/'
# A point is only an anchor in the region, never a zonal spatial mean.
ZONES: tuple[dict[str, Any], ...] = (
    {"id": 'teesta_north', "name_bn": 'উত্তরাঞ্চল ও তিস্তা সমভূমি', "name_en": 'Teesta & northern plain', "examples": 'Rangpur, Dinajpur', "risks": ['drought','river_flood'], "anchors": ['rangpur']},
    {"id": 'barind', "name_bn": 'বরেন্দ্র ও উত্তর-পশ্চিম', "name_en": 'Barind dryland', "examples": 'Rajshahi, Naogaon', "risks": ['heat','water_scarcity'], "anchors": ['rajshahi']},
    {"id": 'jamuna_char', "name_bn": 'যমুনা বন্যা সমভূমি ও চর', "name_en": 'Jamuna floodplain & chars', "examples": 'Jamalpur, Sirajganj', "risks": ['flood','erosion'], "anchors": []},
    {"id": 'old_brahmaputra', "name_bn": 'পুরাতন ব্রহ্মপুত্র ও মধ্য সমভূমি', "name_en": 'Old Brahmaputra plain', "examples": 'Mymensingh', "risks": ['monsoon_flood','water_availability'], "anchors": ['mymensingh']},
    {"id": 'madhupur_terrace', "name_bn": 'মধুপুর টেরেস', "name_en": 'Madhupur terrace', "examples": 'Tangail, Gazipur', "risks": ['runoff','soil_variation'], "anchors": []},
    {"id": 'haor', "name_bn": 'উত্তর-পূর্ব হাওর', "name_en": 'Northeastern haor', "examples": 'Sunamganj, Sylhet', "risks": ['flash_flood','waterlogging'], "anchors": []},
    {"id": 'lower_meghna', "name_bn": 'নিম্ন মেঘনা ও পূর্ব-মধ্য', "name_en": 'Lower Meghna floodplain', "examples": 'Cumilla, Brahmanbaria', "risks": ['flood','drainage'], "anchors": []},
    {"id": 'ganges_inland', "name_bn": 'গঙ্গা প্লাবনভূমি (অ-লবণাক্ত)', "name_en": 'Ganges inland plain', "examples": 'Kushtia, Chuadanga', "risks": ['dry_season_water','heat'], "anchors": []},
    {"id": 'southwest_delta', "name_bn": 'দক্ষিণ-পশ্চিম লবণাক্ত ডেল্টা', "name_en": 'Southwest saline delta', "examples": 'Satkhira, Khulna', "risks": ['salinity','tidal_flood'], "anchors": ['khulna']},
    {"id": 'south_central_coast', "name_bn": 'দক্ষিণ-মধ্য উপকূল', "name_en": 'South-central coast', "examples": 'Barishal, Patuakhali', "risks": ['cyclone','waterlogging'], "anchors": ['barishal']},
    {"id": 'southeast_coast', "name_bn": 'দক্ষিণ-পূর্ব উপকূলীয় সমভূমি', "name_en": 'Southeast coastal plain', "examples": 'Chattogram, Cox’s Bazar', "risks": ['heavy_rain','runoff'], "anchors": ['chattogram']},
    {"id": 'hill_tracts', "name_bn": 'পার্বত্য চট্টগ্রাম', "name_en": 'Chittagong Hill Tracts', "examples": 'Rangamati, Bandarban', "risks": ['erosion','slope'], "anchors": ['rangamati']},
)


def zone_catalog() -> dict[str, Any]:
    return {
        'zones': [{**zone, 'classification': 'proposed_operational_only',
                   'polygon_available': False, 'official_aez_crosswalk_verified': False,
                   'source_area_claim': 'none', 'point_is_zone_average': False}
                  for zone in ZONES],
        'notice': 'These 12 zones are a proposed user-interface grouping, not the official 30 AEZ boundaries. '
                  'An archive anchor is a point sample, NOT the zone average. No farm-specific mapping is implied.',
        'official_aez_reference': AEZ_REFERENCE,
        'status': 'provisional_no_polygons',
    }
