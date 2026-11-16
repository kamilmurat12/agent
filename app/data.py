
"""Demo dataset and shared vocabularies."""

REGIONS = [
    "South Congress", "South Lamar", "Downtown", "Zilker", "Mueller", "East Austin",
    "Hyde Park", "Cherrywood", "South First", "North Burnet", "Clarksville", "Bouldin Creek",
    "Cedar Park", "Pflugerville", "Downtown Pflugerville", "Round Rock", "Hutto",
    "Cottonwood Crossing", "Georgetown", "Downtown Georgetown", "Leander",
    "Bee Cave", "Steiner Ranch", "Lake Travis", "Lakeway",
    "Westlake", "Tarrytown", "Barton Hills", "Windsor Park", "Riverside",
]

REGION_CITY = {
    "Cedar Park": "Cedar Park", "Pflugerville": "Pflugerville",
    "Downtown Pflugerville": "Pflugerville", "Round Rock": "Round Rock",
    "Hutto": "Hutto", "Cottonwood Crossing": "Hutto",
    "Georgetown": "Georgetown", "Downtown Georgetown": "Georgetown",
    "Leander": "Leander", "Bee Cave": "Bee Cave", "Lake Travis": "Lake Travis",
    "Lakeway": "Lakeway", "Westlake": "Westlake",
}

PROPERTY_TYPES = ["house", "condo", "townhouse"]

FEATURES = [
    "good_schools", "yard", "family_friendly", "quiet_street", "pool", "views",
    "walkable", "modern", "affordable", "office_space", "waterfront", "garage",
]

FEATURE_LABELS = {
    "good_schools": "good schools", "family_friendly": "family friendly",
    "quiet_street": "quiet street", "office_space": "home office",
    "walkable": "walkable", "yard": "yard", "pool": "pool", "views": "views",
    "modern": "modern", "affordable": "affordable", "waterfront": "waterfront",
    "garage": "garage",
}


def feature_label(name):
    return FEATURE_LABELS.get(name, name.replace("_", " "))


DEMO_LISTINGS = [
    {"id": 1, "name": "Modern 3BR Home in South Congress", "region": "South Congress",
     "city": "Austin", "property_type": "house", "price": 515000, "beds": 3, "baths": 2,
     "sqft": 1850, "features": ["good_schools", "yard", "modern"],
     "description": "Renovated 3 bedroom house on a quiet street in South Congress. Fenced yard, top schools nearby."},
    {"id": 2, "name": "Spacious 4BR in Cedar Park, Top Schools", "region": "Cedar Park",
     "city": "Cedar Park", "property_type": "house", "price": 465000, "beds": 4, "baths": 3,
     "sqft": 2480, "features": ["good_schools", "yard", "family_friendly"],
     "description": "Family friendly 4 bedroom home in Cedar Park with a big backyard and top-rated schools."},
    {"id": 3, "name": "New Build 3BR, Hutto", "region": "Cottonwood Crossing",
     "city": "Hutto", "property_type": "house", "price": 389000, "beds": 3, "baths": 2,
     "sqft": 1980, "features": ["good_schools", "yard", "family_friendly"],
     "description": "New construction 3 bedroom house in a family friendly Hutto neighborhood with a yard."},
    {"id": 4, "name": "Bungalow-Style Condo near LBJ", "region": "Cherrywood",
     "city": "Austin", "property_type": "condo", "price": 298000, "beds": 2, "baths": 1,
     "sqft": 940, "features": ["walkable", "affordable", "quiet_street"],
     "description": "Affordable 2 bedroom condo on a quiet street, walkable to coffee shops and the UT area."},
    {"id": 5, "name": "Garden Condo with Private Entrance, SoFi", "region": "South First",
     "city": "Austin", "property_type": "condo", "price": 330000, "beds": 2, "baths": 2,
     "sqft": 1090, "features": ["walkable"],
     "description": "Garden-style 2 bedroom condo with a private entrance, walkable to South First shops."},
    {"id": 6, "name": "Starter Condo near UT Campus", "region": "Hyde Park",
     "city": "Austin", "property_type": "condo", "price": 279000, "beds": 1, "baths": 1,
     "sqft": 720, "features": ["walkable", "affordable"],
     "description": "Starter 1 bedroom condo near UT campus, walkable to everything, great value."},
    {"id": 7, "name": "Historic 3BR near Downtown Pflugerville", "region": "Downtown Pflugerville",
     "city": "Pflugerville", "property_type": "house", "price": 315000, "beds": 3, "baths": 2,
     "sqft": 1580, "features": ["affordable", "family_friendly"],
     "description": "Historic 3 bedroom home near downtown Pflugerville, priced for first-time buyers."},
    {"id": 8, "name": "Hill Country Estate Home, Bee Cave", "region": "Bee Cave",
     "city": "Bee Cave", "property_type": "house", "price": 895000, "beds": 5, "baths": 4,
     "sqft": 3600, "features": ["good_schools", "pool", "views"],
     "description": "Estate home on 1 acre with pool and hill country views. Excellent schools."},
    {"id": 9, "name": "Single-Story 4BR, Steiner Ranch", "region": "Steiner Ranch",
     "city": "Austin", "property_type": "house", "price": 610000, "beds": 4, "baths": 3,
     "sqft": 2890, "features": ["good_schools", "pool", "views", "family_friendly"],
     "description": "Single-story 4 bedroom with pool and greenbelt views in a family friendly master-planned community."},
    {"id": 10, "name": "Downtown Luxury Condo", "region": "Downtown",
     "city": "Austin", "property_type": "condo", "price": 725000, "beds": 2, "baths": 2,
     "sqft": 1450, "features": ["walkable", "views", "modern"],
     "description": "Newly built luxury condo with skyline views, walk score 97, concierge."},
    {"id": 11, "name": "Family Home with Pool, Round Rock", "region": "Round Rock",
     "city": "Round Rock", "property_type": "house", "price": 425000, "beds": 4, "baths": 2,
     "sqft": 2300, "features": ["pool", "yard", "family_friendly", "good_schools"],
     "description": "4 bedroom family home with pool and covered patio in Round Rock, good schools."},
    {"id": 12, "name": "Townhome near Domain", "region": "North Burnet",
     "city": "Austin", "property_type": "townhouse", "price": 445000, "beds": 3, "baths": 2,
     "sqft": 1750, "features": ["walkable", "modern", "garage"],
     "description": "Newly built townhome with attached garage near the Domain, walkable to tech offices."},
    {"id": 13, "name": "Craftsman in Zilker", "region": "Zilker",
     "city": "Austin", "property_type": "house", "price": 780000, "beds": 3, "baths": 2,
     "sqft": 1650, "features": ["walkable", "yard", "views"],
     "description": "Classic craftsman near Zilker Park with a shaded yard and park views."},
    {"id": 14, "name": "South Lamar Bungalow", "region": "South Lamar",
     "city": "Austin", "property_type": "house", "price": 549000, "beds": 3, "baths": 2,
     "sqft": 1520, "features": ["walkable", "yard", "modern"],
     "description": "Updated bungalow on South Lamar, walkable to bars and restaurants, private backyard."},
    {"id": 15, "name": "Waterfront Retreat, Lake Travis", "region": "Lake Travis",
     "city": "Lake Travis", "property_type": "house", "price": 995000, "beds": 5, "baths": 4,
     "sqft": 3800, "features": ["waterfront", "pool", "views"],
     "description": "Lakefront property with private dock, infinity pool and panoramic water views."},
    {"id": 16, "name": "Renovated Condo East Austin", "region": "East Austin",
     "city": "Austin", "property_type": "condo", "price": 420000, "beds": 2, "baths": 1,
     "sqft": 980, "features": ["modern", "walkable", "affordable"],
     "description": "Fully renovated condo in East Austin, walkable to food trucks and bars."},
    {"id": 17, "name": "Quiet Cul-de-Sac Home, Pflugerville", "region": "Pflugerville",
     "city": "Pflugerville", "property_type": "house", "price": 355000, "beds": 3, "baths": 2,
     "sqft": 1750, "features": ["quiet_street", "yard", "family_friendly"],
     "description": "3 bedroom home on a quiet cul-de-sac with fenced yard, family friendly street."},
    {"id": 18, "name": "Garden-Style Condo, Mueller", "region": "Mueller",
     "city": "Austin", "property_type": "condo", "price": 410000, "beds": 2, "baths": 2,
     "sqft": 1150, "features": ["walkable", "modern", "garage"],
     "description": "Garden-style condo in Mueller with tandem garage, walkable to the market district."},
    {"id": 19, "name": "New Townhome with Office, Mueller", "region": "Mueller",
     "city": "Austin", "property_type": "townhouse", "price": 475000, "beds": 3, "baths": 2,
     "sqft": 1720, "features": ["modern", "office_space", "garage", "walkable"],
     "description": "New construction townhome with a dedicated home office and attached garage."},
    {"id": 20, "name": "Lakefront Condo, Lakeway", "region": "Lakeway",
     "city": "Lakeway", "property_type": "condo", "price": 520000, "beds": 2, "baths": 2,
     "sqft": 1250, "features": ["waterfront", "views", "pool"],
     "description": "Lakefront condo with pool access and lake views, resort-style amenities."},
]
