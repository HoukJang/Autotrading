#!/usr/bin/env python3
"""
Clean Database Setup Script
Drops existing database and creates fresh schema
WARNING: This will delete all existing data!
"""

import os
import sys
import asyncio
import asyncpg
from pathlib import Path
from dotenv import load_dotenv
import random
import string

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    import locale
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()


def generate_secure_password(length=16):
    """Generate a secure random password"""
    chars = string.ascii_letters + string.digits + "!@#$%^*_+-="
    return ''.join(random.choice(chars) for _ in range(length))


async def drop_existing_database():
    """Drop existing database if it exists"""
    print("[WARNING] Dropping existing database if it exists...")

    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user='postgres',
        password=os.getenv('POSTGRES_PASSWORD', 'postgres'),
        database='postgres'
    )

    try:
        db_name = os.getenv('DB_NAME', 'trading_db')

        # Terminate existing connections
        await conn.execute(f"""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '{db_name}'
            AND pid <> pg_backend_pid()
        """)

        # Drop database
        await conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
        print(f"[OK] Database '{db_name}' dropped successfully")

        # Drop user if exists
        user_name = os.getenv('DB_USER', 'trader')
        await conn.execute(f"DROP USER IF EXISTS {user_name}")
        print(f"[OK] User '{user_name}' dropped successfully")

    finally:
        await conn.close()


async def create_database_and_user():
    """Create fresh database and user"""
    print("\n[INFO] Creating fresh database and user...")

    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user='postgres',
        password=os.getenv('POSTGRES_PASSWORD', 'postgres'),
        database='postgres'
    )

    try:
        db_name = os.getenv('DB_NAME', 'trading_db')
        user_name = os.getenv('DB_USER', 'trader')
        user_password = os.getenv('DB_PASSWORD', generate_secure_password())

        # Create user
        await conn.execute(
            f"CREATE USER {user_name} WITH ENCRYPTED PASSWORD '{user_password}'"
        )
        print(f"[OK] User '{user_name}' created")

        # Create database
        await conn.execute(f"CREATE DATABASE {db_name} OWNER {user_name}")
        print(f"[OK] Database '{db_name}' created with owner '{user_name}'")

        # Grant all privileges
        await conn.execute(f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {user_name}")
        print(f"[OK] All privileges granted to '{user_name}'")

        return user_password

    finally:
        await conn.close()


async def run_migrations():
    """Run database migrations on fresh database"""
    print("\n[INFO] Running migrations on fresh database...")

    # Connect to our new database
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'trader'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME', 'trading_db')
    )

    try:
        # Read migration file
        migration_file = Path(__file__).parent.parent / 'database' / 'migrations' / '001_initial_schema.sql'

        if not migration_file.exists():
            print(f"[ERROR] Migration file not found: {migration_file}")
            return False

        with open(migration_file, 'r') as f:
            migration_sql = f.read()

        # Execute migration
        await conn.execute(migration_sql)
        print("[OK] Database schema created successfully")

        # Verify tables
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)

        print("\n[INFO] Created tables:")
        for table in tables:
            print(f"  - {table['tablename']}")

        # Verify views
        views = await conn.fetch("""
            SELECT viewname FROM pg_views
            WHERE schemaname = 'public'
            ORDER BY viewname
        """)

        if views:
            print("\n[INFO] Created views:")
            for view in views:
                print(f"  - {view['viewname']}")

        # Verify configuration
        config_count = await conn.fetchval("SELECT COUNT(*) FROM system_config")
        print(f"\n[INFO] Default configuration entries: {config_count}")

        # Show some config values
        configs = await conn.fetch("SELECT key, value, description FROM system_config LIMIT 5")
        print("\n[INFO] Sample configuration:")
        for config in configs:
            print(f"  - {config['key']}: {config['value']} ({config['description']})")

        return True

    except Exception as e:
        print(f"[ERROR] Error running migrations: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await conn.close()


async def test_connection():
    """Test the new database connection"""
    print("\n[INFO] Testing database connection...")

    try:
        conn = await asyncpg.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            user=os.getenv('DB_USER', 'trader'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME', 'trading_db')
        )

        # Test basic query
        version = await conn.fetchval('SELECT version()')
        print("[OK] Connection successful!")
        print(f"[INFO] PostgreSQL: {version.split(',')[0]}")

        # Test insert
        await conn.execute("""
            INSERT INTO system_events (event_type, severity, component, message)
            VALUES ('SYSTEM_START', 'INFO', 'setup_script', 'Database setup completed')
        """)

        # Test select
        event_count = await conn.fetchval("SELECT COUNT(*) FROM system_events")
        print(f"[OK] Insert/Select test passed (events: {event_count})")

        await conn.close()
        return True

    except Exception as e:
        print(f"[ERROR] Connection test failed: {e}")
        return False


def update_env_file(password):
    """Update .env file with new password"""
    print("\n[INFO] Updating .env file...")

    env_path = Path(__file__).parent.parent / '.env'
    env_example_path = Path(__file__).parent.parent / '.env.example'

    # If .env doesn't exist, copy from example
    if not env_path.exists() and env_example_path.exists():
        import shutil
        shutil.copy(env_example_path, env_path)
        print("[OK] Created .env from .env.example")

    # Read current .env
    if env_path.exists():
        with open(env_path, 'r') as f:
            lines = f.readlines()

        # Update password
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('DB_PASSWORD='):
                lines[i] = f'DB_PASSWORD={password}\n'
                updated = True
                break

        # If DB_PASSWORD not found, add it
        if not updated:
            lines.append(f'\n# Database credentials (auto-generated)\n')
            lines.append(f'DB_PASSWORD={password}\n')

        # Write back
        with open(env_path, 'w') as f:
            f.writelines(lines)

        print(f"[OK] .env file updated with new password")
        print(f"     Password: {password}")
        print(f"     [WARNING] Keep this password safe!")
    else:
        print("[WARNING] No .env file found. Creating new one...")
        with open(env_path, 'w') as f:
            f.write(f"""# Environment Configuration
ENVIRONMENT=development

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_db
DB_USER=trader
DB_PASSWORD={password}

# Interactive Brokers Configuration
IB_HOST=127.0.0.1
IB_PORT=7497  # TWS: 7497, Gateway: 4001
IB_CLIENT_ID=1

# Risk Management Settings
MAX_POSITION_SIZE=5
MAX_PORTFOLIO_RISK=0.02
MAX_DRAWDOWN=0.05
EMERGENCY_LIQUIDATE_ON_DISCONNECT=true

# Position Sizing
POSITION_SIZING_METHOD=fixed
DEFAULT_POSITION_SIZE=1
POSITION_SIZE_MULTIPLIER=1.0

# PostgreSQL Admin Password (for setup only)
POSTGRES_PASSWORD=postgres

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/trading_system.log
LOG_MAX_BYTES=104857600
LOG_BACKUP_COUNT=10

# Performance
TICK_BUFFER_SIZE=10000
BAR_BUFFER_SIZE=1000
DB_POOL_SIZE=10
EVENT_QUEUE_SIZE=10000
MAX_WORKERS=4

# Data Collection
SAVE_TICK_DATA=false
SAVE_BAR_DATA=true
DATA_RETENTION_DAYS=365

# Monitoring
HEALTH_CHECK_INTERVAL=30
METRICS_INTERVAL=60
PERFORMANCE_CALC_INTERVAL=300
""")
        print(f"[OK] New .env file created with password: {password}")


async def main():
    """Main setup function"""
    print("[INFO] PostgreSQL Clean Setup for Trading System")
    print("=" * 50)
    print("[WARNING] This will DELETE all existing data!")
    print("=" * 50)

    # Confirm action
    response = input("\n[?] Are you sure you want to drop and recreate the database? (yes/no): ")
    if response.lower() != 'yes':
        print("[INFO] Setup cancelled")
        return

    print("\n[INFO] Configuration:")
    print(f"  Host: {os.getenv('DB_HOST', 'localhost')}")
    print(f"  Port: {os.getenv('DB_PORT', 5432)}")
    print(f"  Database: {os.getenv('DB_NAME', 'trading_db')}")
    print(f"  User: {os.getenv('DB_USER', 'trader')}")

    try:
        # Drop existing database
        await drop_existing_database()

        # Create new database and user
        new_password = await create_database_and_user()

        # Update .env file
        update_env_file(new_password)

        # Reload environment with new password
        load_dotenv(override=True)

        # Run migrations
        success = await run_migrations()

        if success:
            # Test connection
            if await test_connection():
                print("\n" + "=" * 50)
                print("[SUCCESS] Database setup completed successfully!")
                print("=" * 50)
                print("\n[INFO] Database Details:")
                print(f"  Host: {os.getenv('DB_HOST')}")
                print(f"  Port: {os.getenv('DB_PORT')}")
                print(f"  Database: {os.getenv('DB_NAME')}")
                print(f"  User: {os.getenv('DB_USER')}")
                print(f"  Password: Saved in .env file")

                print("\n[INFO] Next Steps:")
                print("1. Verify .env file has correct settings")
                print("2. Test IB connection: python scripts/test_ib_connection.py")
                print("3. Run validation: python scripts/test_phase1.py")
            else:
                print("\n[WARNING] Setup completed but connection test failed")
        else:
            print("\n[ERROR] Database setup failed")

    except Exception as e:
        print(f"\n[ERROR] Setup error: {e}")
        import traceback
        traceback.print_exc()
        print("\n[INFO] Troubleshooting:")
        print("1. Ensure PostgreSQL is running")
        print("2. Check postgres user has superuser privileges")
        print("3. Verify no other connections to the database")


if __name__ == "__main__":
    asyncio.run(main())