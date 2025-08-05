"""Database connection and session management."""

import os
from typing import Generator, Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from .models import Base
from ..config.settings import get_settings
from ..utils.logging import get_logger


logger = get_logger("database")


class DatabaseManager:
    """Database connection and session manager."""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database manager."""
        self.settings = get_settings()
        self.database_url = database_url or self.settings.database.url
        
        # Configure engine based on database type
        if self.database_url.startswith("sqlite"):
            # SQLite configuration
            self.engine = create_engine(
                self.database_url,
                poolclass=StaticPool,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 20
                },
                echo=False  # Set to True for SQL debug logging
            )
        else:
            # PostgreSQL or other databases
            self.engine = create_engine(
                self.database_url,
                pool_pre_ping=True,
                pool_recycle=300,
                echo=False
            )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info("Database manager initialized", database_url=self.database_url)
    
    def create_tables(self):
        """Create all database tables."""
        try:
            # Ensure data directory exists for SQLite
            if self.database_url.startswith("sqlite"):
                db_path = self.database_url.replace("sqlite:///", "")
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
            
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error("Failed to create database tables", error=str(e))
            raise
    
    def drop_tables(self):
        """Drop all database tables."""
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.info("Database tables dropped successfully")
        except Exception as e:
            logger.error("Failed to drop database tables", error=str(e))
            raise
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()
    
    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Database transaction rolled back", error=str(e))
            raise
        finally:
            session.close()
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self.session_scope() as session:
                session.execute(text("SELECT 1"))
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error("Database connection test failed", error=str(e))
            return False
    
    def get_table_info(self) -> dict:
        """Get information about database tables."""
        try:
            metadata = MetaData()
            metadata.reflect(bind=self.engine)
            
            table_info = {}
            for table_name, table in metadata.tables.items():
                table_info[table_name] = {
                    "columns": [col.name for col in table.columns],
                    "primary_keys": [col.name for col in table.primary_key],
                    "foreign_keys": [
                        {
                            "column": fk.parent.name,
                            "references": f"{fk.column.table.name}.{fk.column.name}"
                        }
                        for fk in table.foreign_keys
                    ]
                }
            
            logger.info("Retrieved table information", tables=list(table_info.keys()))
            return table_info
        except Exception as e:
            logger.error("Failed to get table information", error=str(e))
            raise


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def init_database(database_url: Optional[str] = None, create_tables: bool = True) -> DatabaseManager:
    """Initialize the database."""
    global _db_manager
    _db_manager = DatabaseManager(database_url)
    
    if create_tables:
        _db_manager.create_tables()
    
    # Test connection
    if not _db_manager.test_connection():
        raise RuntimeError("Failed to establish database connection")
    
    return _db_manager


def get_db_session() -> Generator[Session, None, None]:
    """Dependency function to get database session (for FastAPI, etc.)."""
    db_manager = get_db_manager()
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()


def close_database():
    """Close database connections."""
    global _db_manager
    if _db_manager:
        _db_manager.engine.dispose()
        _db_manager = None
        logger.info("Database connections closed")