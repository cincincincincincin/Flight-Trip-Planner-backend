import os
import sys
import json
import time
import psycopg2
from psycopg2.extras import Json

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL environment variable is missing!")
        sys.exit(1)
    
    # Wait for DB to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            conn = psycopg2.connect(db_url)
            return conn
        except psycopg2.OperationalError as e:
            print(f"Waiting for database to be ready... ({i+1}/{max_retries})")
            time.sleep(2)
    print("Database connection failed.")
    sys.exit(1)

def is_db_initialized(cur):
    try:
        cur.execute("SELECT to_regclass('public.countries');")
        if cur.fetchone()[0] is None:
            return False
            
        cur.execute("SELECT COUNT(*) FROM countries;")
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
                print("Database is already initialized. Skipping initialization.")
                return

            print("Database not initialized. Running initialization script...")

            print("Executing 01_schema.sql...")
            with open(os.path.join(dir_path, "01_schema.sql"), "r", encoding="utf-8") as f:
                cur.execute(f.read())
            
            print("Loading JSON data...")
            queries = [
                ("countries.json", """
                    INSERT INTO countries (code, name, name_translations, currency, wikipedia_link)
                    SELECT elem->>'code', elem->>'name', elem->'name_translations', elem->>'currency', elem->>'wikipedia_link'
                    FROM jsonb_array_elements(%s::jsonb) AS elem;
                """),
                ("cities.json", """
                    INSERT INTO cities (code, name, name_translations, country_code, time_zone, coordinates)
                    SELECT elem->>'code', elem->>'name', elem->'name_translations', elem->>'country_code', elem->>'time_zone', elem->'coordinates'
                    FROM jsonb_array_elements(%s::jsonb) AS elem;
                """),
                ("airlines.json", """
                    INSERT INTO airlines (code, name, name_translations, is_lowcost)
                    SELECT elem->>'code', elem->>'name', elem->'name_translations', COALESCE((elem->>'is_lowcost')::BOOLEAN, FALSE)
                    FROM jsonb_array_elements(%s::jsonb) AS elem;
                """),
                ("airports.json", """
                    INSERT INTO airports (code, name, name_translations, city_code, country_code, time_zone, coordinates, urls)
                    SELECT elem->>'code', elem->>'name', elem->'name_translations', elem->>'city_code', elem->>'country_code', elem->>'time_zone', elem->'coordinates', elem->'urls'
                    FROM jsonb_array_elements(%s::jsonb) AS elem;
                """),
                # ("planes.json", """
                #     INSERT INTO planes (code, name)
                #     SELECT elem->>'code', elem->>'name'
                #     FROM jsonb_array_elements(%s::jsonb) AS elem;
                # """)
            ]
            
            for filename, query in queries:
                filepath = os.path.join(dir_path, "init_data", filename)
                print(f"Loading {filename}...")
                with open(filepath, "r", encoding="utf-8") as f:
                    data_json = json.load(f)
                
                batch_size = 5000
                for i in range(0, len(data_json), batch_size):
                    batch = data_json[i:i + batch_size]
                    cur.execute(query, (json.dumps(batch),))

            print("Executing 02_post_data_schema.sql...")
            with open(os.path.join(dir_path, "02_post_data_schema.sql"), "r", encoding="utf-8") as f:
                cur.execute(f.read())
            
            conn.commit()
            print("Database initialization complete.")

    except Exception as e:
        conn.rollback()
        print(f"Initialization failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
