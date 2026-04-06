import os
import sys
import json
import time
import psycopg2
from psycopg2.extras import Json

def get_db_connection():
    # Funkcja realizująca połączenie z bazą danych PostgreSQL przy użyciu psycopg2
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL environment variable missing")
        sys.exit(1)
    
    # Mechanizm oczekiwania na gotowość bazy danych który zabezpiecza aplikację podczas startu w środowisku Docker
    max_retries = 30
    for i in range(max_retries):
        try:
            conn = psycopg2.connect(db_url)
            return conn
        except psycopg2.OperationalError as e:
            print(f"Waiting for database to be ready {i+1} of {max_retries}")
            time.sleep(2)
    print("Database connection failed")
    sys.exit(1)

def is_db_initialized(cur):
    # Sprawdzenie czy główne tabele systemu zostały już utworzone i czy zawierają dane startowe
    try:
        cur.execute("SELECT to_regclass('public.cities');")
        if cur.fetchone()[0] is None:
            return False

        cur.execute("SELECT COUNT(*) FROM cities;")
        count = cur.fetchone()[0]
        return count > 0
    except psycopg2.Error:
        return False

def init_db():
    dir_path = os.path.dirname(os.path.realpath(__file__))
    conn = get_db_connection()
    conn.autocommit = False
    
    try:
        with conn.cursor() as cur:
            if is_db_initialized(cur):
                print("Database already initialized skipping process")
                return

            print("Database not initialized starting initialization script")

            print("Executing schema 01 schema sql")
            with open(os.path.join(dir_path, "01_schema.sql"), "r", encoding="utf-8") as f:
                cur.execute(f.read())
            
            print("Loading JSON data")
            queries = [
                ("cities.json", """
                    INSERT INTO cities (code, name, name_translations, country_code, coordinates)
                    SELECT elem->>'code', elem->>'name', elem->'name_translations', elem->>'country_code', elem->'coordinates'
                    FROM jsonb_array_elements(%s::jsonb) AS elem;
                """),
                ("airlines.json", """
                    INSERT INTO airlines (code, name)
                    SELECT elem->>'code', elem->>'name'
                    FROM jsonb_array_elements(%s::jsonb) AS elem;
                """),
                ("airports.json", """
                    INSERT INTO airports (code, name, name_translations, city_code, country_code, time_zone, coordinates, urls)
                    SELECT elem->>'code', elem->>'name', elem->'name_translations', elem->>'city_code', elem->>'country_code', elem->>'time_zone', elem->'coordinates', elem->'urls'
                    FROM jsonb_array_elements(%s::jsonb) AS elem;
                """),
            ]
            
            for filename, query in queries:
                filepath = os.path.join(dir_path, "init_data", filename)
                print(f"Loading file {filename}")
                with open(filepath, "r", encoding="utf-8") as f:
                    data_json = json.load(f)
                
                batch_size = 5000
                for i in range(0, len(data_json), batch_size):
                    # Przetwarzanie dużych zbiorów danych w paczkach po pięć tysięcy rekordów w celu optymalizacji pamięci operacyjnej
                    batch = data_json[i:i + batch_size]
                    cur.execute(query, (json.dumps(batch),))

            print("Executing schema 02 post data schema sql")
            with open(os.path.join(dir_path, "02_post_data_schema.sql"), "r", encoding="utf-8") as f:
                cur.execute(f.read())
            
            # Zatwierdzenie wszystkich operacji w jednej transakcji co gwarantuje spójność danych po zakończeniu skryptu
            conn.commit()
            print("Database initialization complete")

    except Exception as e:
        conn.rollback()
        print(f"Initialization failed {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
