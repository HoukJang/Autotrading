"""
Database Models
SQLAlchemy models for ORM (optional, for future use)
"""

from sqlalchemy.ext.declarative import declarative_base

# Base model for SQLAlchemy (optional for ORM usage)
Base = declarative_base()

# Note: Currently using raw SQL queries with asyncpg for better performance.
# SQLAlchemy models can be added here if ORM is needed in the future.