import sqlite3
import psycopg2
from datetime import datetime
import sys


def migrate_sqlite_to_postgresql():
    """Complete migration from SQLite to PostgreSQL with all tables"""

    print("Starting migration from SQLite to PostgreSQL...")

    # Database connection settings - FIXED to match docker-compose.yml
    pg_settings = {
        "host": "localhost",  # Use localhost when running migration from host
        "database": "netflix_streaming",
        "user": "postgres",
        "password": "netflix_secure_password_123",  # Matches docker-compose.yml
        "port": "5432",
    }

    try:
        # Connect to SQLite
        print("Connecting to SQLite database...")
        sqlite_conn = sqlite3.connect("netflix.db")
        sqlite_conn.row_factory = sqlite3.Row

        # Connect to PostgreSQL
        print("Connecting to PostgreSQL database...")
        pg_conn = psycopg2.connect(**pg_settings)
        pg_cursor = pg_conn.cursor()

        # Drop existing tables (optional - for clean migration)
        print("Dropping existing PostgreSQL tables...")
        drop_tables_sql = """
        DROP TABLE IF EXISTS admin_access_log CASCADE;
        DROP TABLE IF EXISTS access_log CASCADE;
        DROP TABLE IF EXISTS ip_access_requests CASCADE;
        DROP TABLE IF EXISTS movie_requests CASCADE;
        DROP TABLE IF EXISTS ip_whitelist CASCADE;
        DROP TABLE IF EXISTS movies CASCADE;
        DROP TABLE IF EXISTS users CASCADE;
        """
        pg_cursor.execute(drop_tables_sql)
        pg_conn.commit()

        # Create all tables in PostgreSQL
        print("Creating PostgreSQL tables...")
        create_tables_sql = """
        -- Users table
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            password VARCHAR(120) NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Movies table (with series support)
        CREATE TABLE movies (
            id SERIAL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            genre VARCHAR(100),
            duration INTEGER,
            release_year INTEGER,
            video_file VARCHAR(300) NOT NULL,
            thumbnail_file VARCHAR(300),
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            auto_generated_thumb BOOLEAN DEFAULT FALSE,
            is_series BOOLEAN DEFAULT FALSE,
            series_name VARCHAR(200),
            season_number INTEGER,
            episode_number INTEGER,
            episode_title VARCHAR(200)
        );
        
        -- Movie requests table
        CREATE TABLE movie_requests (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            request_type VARCHAR(50) DEFAULT 'movie',
            genre VARCHAR(100),
            release_year INTEGER,
            series_name VARCHAR(200),
            season_number INTEGER,
            episode_number INTEGER,
            imdb_link VARCHAR(300),
            additional_info TEXT,
            status VARCHAR(50) DEFAULT 'pending',
            admin_notes TEXT,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            processed_by INTEGER REFERENCES users(id)
        );
        
        -- IP Whitelist table
        CREATE TABLE ip_whitelist (
            id SERIAL PRIMARY KEY,
            ip_address VARCHAR(45) UNIQUE NOT NULL,
            description TEXT,
            added_by INTEGER REFERENCES users(id),
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        );
        
        -- IP Access Requests table
        CREATE TABLE ip_access_requests (
            id SERIAL PRIMARY KEY,
            ip_address VARCHAR(45) NOT NULL,
            name VARCHAR(100),
            reason TEXT,
            request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(50) DEFAULT 'pending',
            processed_time TIMESTAMP,
            processed_by INTEGER REFERENCES users(id)
        );
        
        -- Admin Access Log table
        CREATE TABLE admin_access_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            ip_address VARCHAR(45),
            access_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action VARCHAR(200),
            success BOOLEAN DEFAULT TRUE
        );
        
        -- General Access Log table
        CREATE TABLE access_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            ip_address VARCHAR(45),
            access_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action VARCHAR(200),
            success BOOLEAN DEFAULT TRUE
        );
        
        -- Create indexes for better performance
        CREATE INDEX idx_movies_series ON movies(series_name, season_number, episode_number);
        CREATE INDEX idx_movies_uploaded ON movies(uploaded_at);
        CREATE INDEX idx_movie_requests_status ON movie_requests(status);
        CREATE INDEX idx_movie_requests_user ON movie_requests(user_id);
        CREATE INDEX idx_ip_whitelist_active ON ip_whitelist(is_active);
        CREATE INDEX idx_access_log_time ON admin_access_log(access_time);
        CREATE INDEX idx_access_log_user ON admin_access_log(user_id);
        """

        pg_cursor.execute(create_tables_sql)
        pg_conn.commit()
        print("PostgreSQL tables created successfully!")

        # Define table migration order (users first due to foreign key dependencies)
        migration_order = [
            "users",
            "movies",
            "movie_requests",
            "ip_whitelist",
            "ip_access_requests",
            "admin_access_log",
            "access_log",
        ]

        total_migrated = 0

        # Migrate data for each table
        for table in migration_order:
            print(f"\nMigrating {table}...")

            # Check if table exists in SQLite
            sqlite_cursor = sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            if not sqlite_cursor.fetchone():
                print(f"Table {table} not found in SQLite, skipping...")
                continue

            # Get data from SQLite
            sqlite_cursor = sqlite_conn.execute(f"SELECT * FROM {table}")
            rows = sqlite_cursor.fetchall()

            if not rows:
                print(f"No data in {table}, skipping...")
                continue

            # Get column names from SQLite
            column_names = [description[0] for description in sqlite_cursor.description]
            print(f"Columns found: {column_names}")

            # Create mapping for data conversion
            def convert_row_data(row, table_name):
                """Convert SQLite row data to PostgreSQL compatible format"""
                converted = list(row)

                # Convert boolean values (SQLite stores as 0/1, PostgreSQL needs TRUE/FALSE)
                if table_name == "users":
                    if "is_admin" in column_names:
                        is_admin_idx = column_names.index("is_admin")
                        converted[is_admin_idx] = bool(converted[is_admin_idx])

                elif table_name == "movies":
                    if "auto_generated_thumb" in column_names:
                        thumb_idx = column_names.index("auto_generated_thumb")
                        converted[thumb_idx] = bool(converted[thumb_idx])
                    if "is_series" in column_names:
                        series_idx = column_names.index("is_series")
                        converted[series_idx] = bool(converted[series_idx])

                elif table_name == "ip_whitelist":
                    if "is_active" in column_names:
                        active_idx = column_names.index("is_active")
                        converted[active_idx] = bool(converted[active_idx])

                elif table_name in ["admin_access_log", "access_log"]:
                    if "success" in column_names:
                        success_idx = column_names.index("success")
                        converted[success_idx] = bool(converted[success_idx])

                return converted

            # Insert data into PostgreSQL
            placeholders = ", ".join(["%s"] * len(column_names))
            columns = ", ".join(column_names)

            # Skip the 'id' column for auto-increment
            if "id" in column_names:
                non_id_columns = [col for col in column_names if col != "id"]
                non_id_placeholders = ", ".join(["%s"] * len(non_id_columns))
                insert_sql = f"INSERT INTO {table} ({', '.join(non_id_columns)}) VALUES ({non_id_placeholders})"
            else:
                insert_sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

            successful_inserts = 0
            for row in rows:
                try:
                    converted_row = convert_row_data(row, table)

                    # Remove 'id' value for auto-increment
                    if "id" in column_names:
                        id_idx = column_names.index("id")
                        row_data = converted_row[:id_idx] + converted_row[id_idx + 1 :]
                    else:
                        row_data = converted_row

                    pg_cursor.execute(insert_sql, tuple(row_data))
                    successful_inserts += 1

                except Exception as e:
                    print(f"Error inserting row into {table}: {e}")
                    print(f"Row data: {row}")
                    print(f"Converted data: {converted_row}")
                    # Continue with next row instead of failing completely

            pg_conn.commit()
            print(
                f"Successfully migrated {successful_inserts}/{len(rows)} rows from {table}"
            )
            total_migrated += successful_inserts

            # Reset sequence for auto-increment columns
            if successful_inserts > 0:
                try:
                    pg_cursor.execute(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}));"
                    )
                    pg_conn.commit()
                    print(f"Reset sequence for {table}")
                except Exception as e:
                    print(f"Could not reset sequence for {table}: {e}")

        print(f"\n🎉 Migration completed successfully!")
        print(f"Total rows migrated: {total_migrated}")

        # Verify migration
        print("\nVerifying migration...")
        for table in migration_order:
            try:
                pg_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = pg_cursor.fetchone()[0]
                print(f"{table}: {count} rows")
            except Exception as e:
                print(f"Could not verify {table}: {e}")

    except psycopg2.Error as e:
        print(f"PostgreSQL error: {e}")
        print("Make sure PostgreSQL is running and the database exists.")
        print(
            "Try: docker-compose exec postgres psql -U postgres -c 'CREATE DATABASE netflix_streaming;'"
        )
        if "pg_conn" in locals():
            pg_conn.rollback()
        return False

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        print("Make sure netflix.db exists in the current directory.")
        return False

    except Exception as e:
        print(f"Migration failed: {e}")
        print(f"Error type: {type(e)}")
        import traceback

        traceback.print_exc()
        if "pg_conn" in locals():
            pg_conn.rollback()
        return False

    finally:
        # Close connections
        if "sqlite_conn" in locals():
            sqlite_conn.close()
            print("SQLite connection closed.")
        if "pg_conn" in locals():
            pg_conn.close()
            print("PostgreSQL connection closed.")

    return True


def verify_sqlite_database():
    """Check what tables exist in SQLite database"""
    print("Checking SQLite database structure...")

    try:
        conn = sqlite3.connect("netflix.db")
        cursor = conn.cursor()

        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            print("No tables found in SQLite database!")
            return False

        print(f"Found {len(tables)} tables in SQLite:")

        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]

            # Get column info
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            print(f"  {table_name}: {count} rows, columns: {column_names}")

        conn.close()
        return True

    except Exception as e:
        print(f"Error checking SQLite database: {e}")
        return False


def test_postgresql_connection():
    """Test PostgreSQL connection"""
    print("Testing PostgreSQL connection...")

    # FIXED: Use same settings as in migrate_sqlite_to_postgresql
    pg_settings = {
        "host": "localhost",
        "database": "netflix_streaming",
        "user": "postgres",
        "password": "netflix_secure_password_123",  # Matches docker-compose.yml
        "port": "5432",
    }

    try:
        conn = psycopg2.connect(**pg_settings)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✅ PostgreSQL connection successful!")
        print(f"Version: {version[0]}")
        conn.close()
        return True

    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure PostgreSQL is running: docker-compose up -d postgres")
        print(
            "2. Create database: docker-compose exec postgres psql -U postgres -c 'CREATE DATABASE netflix_streaming;'"
        )
        print("3. Check password in pg_settings matches your docker-compose.yml")
        return False


if __name__ == "__main__":
    print("Netflix Database Migration Tool")
    print("=" * 50)

    # Step 1: Verify SQLite database
    if not verify_sqlite_database():
        print("❌ SQLite database verification failed!")
        sys.exit(1)

    print()

    # Step 2: Test PostgreSQL connection
    if not test_postgresql_connection():
        print("❌ PostgreSQL connection failed!")
        sys.exit(1)

    print()

    # Step 3: Ask for confirmation
    response = input(
        "Do you want to proceed with migration? This will overwrite existing PostgreSQL data. (y/N): "
    )
    if response.lower() != "y":
        print("Migration cancelled.")
        sys.exit(0)

    # Step 4: Run migration
    if migrate_sqlite_to_postgresql():
        print("\n🎉 Migration completed successfully!")
        print("\nNext steps:")
        print("1. Update your app.py to use PostgreSQL")
        print("2. Test your application with the new database")
        print("3. Keep netflix.db as backup until you're sure everything works")
    else:
        print("\n❌ Migration failed!")
        print("Check the error messages above and try again.")
