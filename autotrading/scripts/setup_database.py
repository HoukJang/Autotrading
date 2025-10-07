#!/usr/bin/env python3
"""
Database Setup Script
Creates database schema and initial configuration
"""

import os
import sys
import asyncio
import asyncpg
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv()


async def create_database():
    """Create database if it doesn't exist"""
    # Connect to postgres database to create our database
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user='postgres',
        password=os.getenv('POSTGRES_PASSWORD', 'postgres'),
        database='postgres'
    )

    try:
        # Check if database exists
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            os.getenv('DB_NAME', 'trading_db')
        )

        if not exists:
            # Create database
            await conn.execute(f"CREATE DATABASE {os.getenv('DB_NAME', 'trading_db')}")
            print(f"✅ Database '{os.getenv('DB_NAME')}' created successfully")
        else:
            print(f"ℹ️  Database '{os.getenv('DB_NAME')}' already exists")

    finally:
        await conn.close()


async def run_migrations():
    """Run database migrations"""
    # Connect to our database
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
            print(f"❌ Migration file not found: {migration_file}")
            return False

        with open(migration_file, 'r') as f:
            migration_sql = f.read()

        # Execute migration
        await conn.execute(migration_sql)
        print("✅ Database migrations completed successfully")

        # Verify tables were created
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)

        print("\n📊 Created tables:")
        for table in tables:
            print(f"  - {table['tablename']}")

        # Verify configuration was inserted
        config_count = await conn.fetchval("SELECT COUNT(*) FROM system_config")
        print(f"\n⚙️  Configuration entries: {config_count}")

        return True

    except Exception as e:
        print(f"❌ Error running migrations: {e}")
        return False

    finally:
        await conn.close()


async def verify_setup():
    """Verify database setup"""
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
        print(f"\n✅ Database connection successful")
        print(f"📌 PostgreSQL version: {version.split(',')[0]}")

        # Check tables
        required_tables = [
            'market_data_1min',
            'trading_signals',
            'orders',
            'positions',
            'performance_metrics',
            'strategy_performance',
            'system_events',
            'risk_events',
            'system_config'
        ]

        for table in required_tables:
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = $1)",
                table
            )
            if exists:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                print(f"  ✅ {table}: {count} records")
            else:
                print(f"  ❌ {table}: NOT FOUND")

        await conn.close()
        return True

    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        return False


async def main():
    """Main setup function"""
    print("🚀 Starting Database Setup")
    print("=" * 50)

    # Check for .env file
    if not os.path.exists('.env'):
        print("⚠️  Warning: .env file not found")
        print("Creating .env from .env.example...")

        if os.path.exists('.env.example'):
            import shutil
            shutil.copy('.env.example', '.env')
            print("✅ .env file created. Please edit it with your database credentials.")
            print("Then run this script again.")
            return
        else:
            print("❌ .env.example not found. Please create .env file manually.")
            return

    # Validate environment variables
    required_vars = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("Please update your .env file with the required variables.")
        return

    print(f"🔧 Database Configuration:")
    print(f"  Host: {os.getenv('DB_HOST')}")
    print(f"  Port: {os.getenv('DB_PORT')}")
    print(f"  Database: {os.getenv('DB_NAME')}")
    print(f"  User: {os.getenv('DB_USER')}")
    print()

    try:
        # Create database if needed
        print("📦 Creating database...")
        await create_database()

        # Run migrations
        print("\n🔄 Running migrations...")
        success = await run_migrations()

        if success:
            # Verify setup
            print("\n🔍 Verifying setup...")
            if await verify_setup():
                print("\n✨ Database setup completed successfully!")
                print("\nNext steps:")
                print("1. Test IB connection: python scripts/test_ib_connection.py")
                print("2. Start development: python main.py --env development")
            else:
                print("\n⚠️  Database setup completed with warnings")
        else:
            print("\n❌ Database setup failed")

    except Exception as e:
        print(f"\n❌ Setup error: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure PostgreSQL is running")
        print("2. Check your .env file has correct credentials")
        print("3. Verify postgres user has CREATE DATABASE privileges")


if __name__ == "__main__":
    asyncio.run(main())