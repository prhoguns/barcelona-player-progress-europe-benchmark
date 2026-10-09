"""Supported leagues, their source codes and club names on each source."""
from __future__ import annotations

CURRENT_SEASON = 2026  # 2026/27

LEAGUES = {
    "la-liga": {
        "name": "La Liga", "football_data": "SP1", "openfootball": "es.1",
        "default_club": "Barcelona",
    },
    "premier-league": {
        "name": "Premier League", "football_data": "E0", "openfootball": "en.1",
        "default_club": "Arsenal",
    },
}

# football-data.co.uk club name -> English Wikipedia club article used in
# "<season> <article> season" page titles. Clubs missing here still get team
# forecasts; they only lack Wikipedia player data.
WIKIPEDIA = {
    # La Liga
    "Alaves": "Deportivo Alavés", "Ath Bilbao": "Athletic Bilbao", "Ath Madrid": "Atlético Madrid",
    "Barcelona": "FC Barcelona", "Betis": "Real Betis", "Celta": "RC Celta de Vigo",
    "Elche": "Elche CF", "Espanol": "RCD Espanyol", "Getafe": "Getafe CF", "Girona": "Girona FC",
    "Granada": "Granada CF", "La Coruna": "Deportivo de La Coruña", "Las Palmas": "UD Las Palmas",
    "Leganes": "CD Leganés", "Levante": "Levante UD", "Malaga": "Málaga CF", "Mallorca": "RCD Mallorca",
    "Osasuna": "CA Osasuna", "Oviedo": "Real Oviedo", "Real Madrid": "Real Madrid CF",
    "Santander": "Racing de Santander", "Sevilla": "Sevilla FC", "Sociedad": "Real Sociedad",
    "Valencia": "Valencia CF", "Valladolid": "Real Valladolid", "Vallecano": "Rayo Vallecano",
    "Villarreal": "Villarreal CF", "Cadiz": "Cádiz CF", "Almeria": "UD Almería", "Eibar": "SD Eibar",
    "Huesca": "SD Huesca",
    # Premier League
    "Arsenal": "Arsenal F.C.", "Aston Villa": "Aston Villa F.C.", "Bournemouth": "AFC Bournemouth",
    "Brentford": "Brentford F.C.", "Brighton": "Brighton & Hove Albion F.C.", "Burnley": "Burnley F.C.",
    "Chelsea": "Chelsea F.C.", "Coventry": "Coventry City F.C.", "Crystal Palace": "Crystal Palace F.C.",
    "Everton": "Everton F.C.", "Fulham": "Fulham F.C.", "Hull": "Hull City A.F.C.",
    "Ipswich": "Ipswich Town F.C.", "Leeds": "Leeds United F.C.", "Leicester": "Leicester City F.C.",
    "Liverpool": "Liverpool F.C.", "Luton": "Luton Town F.C.", "Man City": "Manchester City F.C.",
    "Man United": "Manchester United F.C.", "Newcastle": "Newcastle United F.C.",
    "Nott'm Forest": "Nottingham Forest F.C.", "Sheffield United": "Sheffield United F.C.",
    "Southampton": "Southampton F.C.", "Sunderland": "Sunderland A.F.C.", "Tottenham": "Tottenham Hotspur F.C.",
    "West Ham": "West Ham United F.C.", "Wolves": "Wolverhampton Wanderers F.C.", "Watford": "Watford F.C.",
    "Norwich": "Norwich City F.C.", "West Brom": "West Bromwich Albion F.C.",
}


def season_label(start_year: int) -> str:
    return f"{start_year}/{(start_year + 1) % 100:02d}"
