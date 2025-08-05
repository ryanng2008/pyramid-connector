"""Main application entry point."""

import asyncio
import signal
import sys
from pathlib import Path

from .config.settings import get_settings
from .utils.logging import setup_logging, get_logger


class FileConnectorApp:
    """Main File Connector application."""
    
    def __init__(self):
        """Initialize the application."""
        self.settings = get_settings()
        self.logger = get_logger("FileConnector")
        self.running = False
        
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
        
        # TODO: Initialize database
        # TODO: Initialize API clients
        # TODO: Initialize scheduler
        
        self.running = True
        self.logger.info("File Connector started successfully")
        
    async def shutdown(self):
        """Application shutdown."""
        self.logger.info("Shutting down File Connector")
        self.running = False
        
        # TODO: Stop scheduler
        # TODO: Close database connections
        # TODO: Close API client sessions
        
        self.logger.info("File Connector stopped")
        
    async def run(self):
        """Run the main application loop."""
        await self.startup()
        
        try:
            while self.running:
                # Main application loop
                # TODO: This will be replaced with the scheduler
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
        finally:
            await self.shutdown()


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