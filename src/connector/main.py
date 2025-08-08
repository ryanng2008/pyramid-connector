"""Main application entry point."""

import asyncio
import signal
import sys
from pathlib import Path
from aiohttp import web, web_runner
import json
from datetime import datetime, timezone

from .config.settings import get_settings
from .utils.logging import setup_logging, get_logger
from .database import init_database, close_database
from .database.service import DatabaseService
from .config.manager import ConfigManager
from .core.connector import FileConnector
from .scheduler.scheduler_manager import SchedulerManager


class FileConnectorApp:
    """Main File Connector application."""
    
    def __init__(self):
        """Initialize the application."""
        self.settings = get_settings()
        self.logger = get_logger("FileConnector")
        self.running = False
        self.web_app = None
        self.web_runner = None
        self.db_service: DatabaseService | None = None
        self.config_manager: ConfigManager | None = None
        self.connector: FileConnector | None = None
        self.scheduler_manager: SchedulerManager | None = None
        
    async def startup(self):
        """Application startup."""
        self.logger.info(
            "Starting File Connector",
            version=self.settings.version,
            environment=self.settings.environment
        )
        
        # Create necessary directories
        Path("./data").mkdir(exist_ok=True)
        Path("./logs").mkdir(exist_ok=True)
        Path("./secrets").mkdir(exist_ok=True)
        
        # Initialize web server for health checks and metrics
        await self._setup_web_server()
        
        # Initialize database (creates tables if needed)
        init_database(create_tables=True)
        self.db_service = DatabaseService()
        
        # Load configuration and sync endpoints to database
        self.config_manager = ConfigManager(database_service=self.db_service)
        self.config_manager.load_config()
        try:
            self.config_manager.sync_to_database()
        except Exception as e:
            self.logger.warning("Configuration sync failed", error=str(e))
        
        # Initialize connector and scheduler
        self.connector = FileConnector(database_service=self.db_service)
        self.scheduler_manager = SchedulerManager(
            connector=self.connector,
            config_manager=self.config_manager,
            max_concurrent_syncs=self.settings.scheduling.max_concurrent_syncs,
        )
        await self.scheduler_manager.start()
        
        self.running = True
        self.logger.info("File Connector started successfully")
        
    async def shutdown(self):
        """Application shutdown."""
        self.logger.info("Shutting down File Connector")
        self.running = False
        
        # Stop scheduler
        if self.scheduler_manager:
            try:
                await self.scheduler_manager.stop()
            except Exception:
                pass
        
        # Stop web server
        await self._stop_web_server()
        
        # Close database connections
        try:
            close_database()
        except Exception:
            pass
        
        self.logger.info("File Connector stopped")
        
    async def run(self):
        """Run the main application loop."""
        await self.startup()
        
        try:
            while self.running:
                # Keep application running while scheduler handles sync jobs
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
        finally:
            await self.shutdown()
    
    async def _setup_web_server(self):
        """Set up web server for health checks and status."""
        self.web_app = web.Application()
        
        # Add routes
        self.web_app.router.add_get('/health', self._health_handler)
        self.web_app.router.add_get('/status', self._status_handler)
        
        # Start web server
        self.web_runner = web_runner.AppRunner(self.web_app)
        await self.web_runner.setup()
        
        site = web_runner.TCPSite(self.web_runner, '0.0.0.0', 8080)
        await site.start()
        
        self.logger.info("Web server started on http://0.0.0.0:8080")
    
    async def _stop_web_server(self):
        """Stop web server."""
        if self.web_runner:
            await self.web_runner.cleanup()
            self.logger.info("Web server stopped")
    
    async def _health_handler(self, request):
        """Health check endpoint."""
        health_data = {
            "status": "healthy" if self.running else "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": self.settings.version,
            "environment": self.settings.environment,
            "uptime_seconds": 0
        }
        
        status_code = 200 if self.running else 503
        return web.json_response(health_data, status=status_code)
    

    
    async def _status_handler(self, request):
        """Detailed status endpoint."""
        status_data = {
            "application": {
                "name": "File Connector",
                "version": self.settings.version,
                "environment": self.settings.environment,
                "running": self.running,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "components": {
                "database": "healthy",
                "scheduler": "running" if self.scheduler_manager and self.scheduler_manager._is_running else "stopped",
                "api_clients": "configured"
            }
        }
        
        return web.json_response(status_data)


def setup_signal_handlers(app: FileConnectorApp):
    """Set up signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        app.logger.info(f"Received signal {signum}")
        app.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Main entry point."""
    # Set up logging first
    setup_logging()
    
    logger = get_logger("main")
    logger.info("Initializing File Connector application")
    
    # Create application instance
    app = FileConnectorApp()
    
    # Set up signal handlers
    setup_signal_handlers(app)
    
    # Run the application
    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Application failed with error: {e}")
        sys.exit(1)