from typing import List, Optional, Dict, Any
from src.database import db
from src.models.airport import Airport

class AirportService:

    @staticmethod
    async def get_all_airports(
        country_code: Optional[str] = None,
        city_code: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        lang: str = 'en'
    ) -> List[Airport]:
        """Get all airports with optional filters"""
        lang = lang if lang in ('en', 'pl') else 'en'
        async with db.get_connection() as conn:
            query = f"""
                SELECT
                    code,
                    COALESCE(name_translations->>'{lang}', name) AS name,
                    city_code, country_code,
                    time_zone, coordinates, urls,
                    name_translations
                FROM airports
                WHERE 1=1
            """
            params = []
            param_count = 0

            if country_code:
                param_count += 1
                query += f" AND country_code = ${param_count}"
                params.append(country_code)

            if city_code:
                param_count += 1
                query += f" AND city_code = ${param_count}"
                params.append(city_code)

            query += " ORDER BY name"

            if limit is not None:
                param_count += 1
                query += f" LIMIT ${param_count}"
                params.append(limit)

            if offset > 0:
                param_count += 1
                query += f" OFFSET ${param_count}"
                params.append(offset)

            rows = await conn.fetch(query, *params)

            airports = []
            for row in rows:
                airport_dict = dict(row)
                airports.append(Airport(**airport_dict))

            return airports

    @staticmethod
    async def get_airport_by_code(code: str) -> Optional[Airport]:
        """Get airport by IATA code"""
        async with db.get_connection() as conn:
            row = await conn.fetchrow("""
                SELECT
                    code, name, city_code, country_code,
                    time_zone, coordinates, urls,
                    name_translations
                FROM airports
                WHERE code = $1
            """, code)

            if row:
                return Airport(**dict(row))
            return None

    @staticmethod
    async def get_airports_as_geojson(
        limit: Optional[int] = None,
        lang: str = 'en'
    ) -> Dict[str, Any]:
        """Get airports as GeoJSON features"""
        lang = lang if lang in ('en', 'pl') else 'en'
        async with db.get_connection() as conn:
            query = f"""
                SELECT
                    a.code,
                    COALESCE(a.name_translations->>'{lang}', a.name) AS name,
                    a.city_code, a.country_code,
                    a.time_zone, a.coordinates,
                    COALESCE(c.name_translations->>'{lang}', c.name) AS city_name,
                    co.name as country_name
                FROM airports a
                LEFT JOIN cities c ON a.city_code = c.code
                LEFT JOIN countries co ON a.country_code = co.code
                WHERE 1=1
            """
            params = []
            param_count = 0

            query += " ORDER BY a.name"

            if limit is not None:
                param_count += 1
                query += f" LIMIT ${param_count}"
                params.append(limit)

            rows = await conn.fetch(query, *params)

            features = []
            for row in rows:
                airport_dict = dict(row)
                props = {
                    'code': airport_dict['code'],
                    'name': airport_dict['name'],
                    'city_code': airport_dict['city_code'],
                    'city_name': airport_dict['city_name'],
                    'country_code': airport_dict['country_code'],
                    'country_name': airport_dict['country_name'],
                    'time_zone': airport_dict.get('time_zone'),
                }
                feature = {
                    "type": "Feature",
                    "properties": props,
                    "geometry": None
                }
                if airport_dict.get('coordinates') and 'lat' in airport_dict['coordinates'] and 'lon' in airport_dict['coordinates']:
                    feature["geometry"] = {
                        "type": "Point",
                        "coordinates": [
                            float(airport_dict['coordinates']['lon']),
                            float(airport_dict['coordinates']['lat'])
                        ]
                    }
                if feature.get("geometry"):
                    features.append(feature)

        return {
            "type": "FeatureCollection",
            "features": features
        }

    @staticmethod
    async def get_airports_count(
        country_code: Optional[str] = None
    ) -> int:
        """Get total count of airports"""
        async with db.get_connection() as conn:
            query = "SELECT COUNT(*) FROM airports WHERE 1=1"
            params = []

            if country_code:
                query += " AND country_code = $1"
                params.append(country_code)

            count = await conn.fetchval(query, *params)
            return count or 0

airport_service = AirportService()
