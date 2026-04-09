# tags.py
# Canonical checkbox slugs and labels for food preference blocks (mockup-aligned).

FOOD_LIKE_CHOICES: dict[str, str] = {
    "street_food": "Street food",
    "spicy": "Spicy",
    "seafood": "Seafood",
    "noodles": "Noodles",
    "local_specialties": "Local specialties",
}

FOOD_DISLIKE_CHOICES: dict[str, str] = {
    "very_sweet": "Very sweet",
    "offal": "Offal",
    "raw_fish": "Raw fish",
    "heavy_cream": "Heavy cream",
    "fast_food_chains": "Fast food chains",
}

DIETARY_CHOICES: dict[str, str] = {
    "vegetarian": "Vegetarian",
    "vegan": "Vegan",
    "halal": "Halal",
    "kosher": "Kosher",
    "gluten_free": "Gluten-free",
}

SEASON_CHOICES: dict[str, str] = {
    "spring": "Spring (Mar–May)",
    "summer": "Summer (Jun–Aug)",
    "autumn": "Autumn (Sep–Nov)",
    "winter": "Winter (Dec–Feb)",
}

MONTH_CHOICES: dict[str, str] = {
    str(i): m
    for i, m in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}
