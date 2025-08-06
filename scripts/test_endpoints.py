#!/usr/bin/env python3
"""
Endpoint Testing Script for File Connector

This script tests connectivity and authentication for all configured endpoints
without performing a full sync. It's useful for verifying configuration
before running the main connector.

Usage:
    python scripts/test_endpoints.py [OPTIONS]

Examples:
    # Test all endpoints
    python scripts/test_endpoints.py

    # Test only Google Drive endpoints
    python scripts/test_endpoints.py --type google_drive

    # Test with verbose output
    python scripts/test_endpoints.py --verbose

    # Test authentication only (no file listing)
    python scripts/test_endpoints.py --auth-only
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from connector.api_clients import APIClientFactory
from connector.api_clients.base import BaseAPIClient, AuthenticationError, APIConnectionError
from connector.config.loader import ConfigurationLoader
from connector.config.settings import load_settings
from connector.utils.logging import setup_logging, get_logger


class EndpointTester:
    """Test connectivity and authentication for API endpoints."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.logger = get_logger("EndpointTester")
        self.results = {
            "tested_at": datetime.now().isoformat(),
            "endpoints": [],
            "summary": {"total": 0, "passed": 0, "failed": 0}
        }
    
    def _print_header(self):
        """Print test header."""
        print("\n🧪 Testing File Connector Endpoints")
        print("=" * 50)
        print()
    
    def _print_endpoint_header(self, name: str, endpoint_type: str):
        """Print endpoint test header."""
        icon = "📁" if endpoint_type == "google_drive" else "🏗️"
        print(f"{icon} {endpoint_type.replace('_', ' ').title()} Endpoint: {name}")
    
    def _print_success(self, message: str):
        """Print success message."""
        print(f"   ✅ {message}")
    
    def _print_error(self, message: str):
        """Print error message."""
        print(f"   ❌ {message}")
    
    def _print_info(self, message: str):
        """Print info message."""
        if self.verbose:
            print(f"   ℹ️  {message}")
    
    def _print_files(self, files: List[Dict[str, Any]], max_files: int = 3):
        """Print sample files."""
        if not files:
            self._print_info("No files found")
            return
        
        print(f"   📄 Sample files:")
        for file_info in files[:max_files]:
            date_str = file_info.get('date_updated', 'Unknown date')
            if isinstance(date_str, datetime):
                date_str = date_str.strftime('%Y-%m-%d')
            print(f"      - {file_info.get('title', 'Unknown')} ({date_str})")
        
        if len(files) > max_files:
            print(f"      ... and {len(files) - max_files} more files")
    
    async def test_endpoint_authentication(self, client: BaseAPIClient, endpoint_name: str) -> bool:
        """Test endpoint authentication."""
        try:
            self._print_info(f"Testing authentication for {endpoint_name}...")
            authenticated = await client.authenticate()
            
            if authenticated:
                self._print_success("Authentication successful")
                return True
            else:
                self._print_error("Authentication failed")
                return False
                
        except AuthenticationError as e:
            self._print_error(f"Authentication failed: {e}")
            return False
        except Exception as e:
            self._print_error(f"Authentication error: {e}")
            return False
    
    async def test_endpoint_file_listing(
        self, 
        client: BaseAPIClient, 
        endpoint_name: str, 
        max_files: int = 5
    ) -> tuple[bool, List[Dict[str, Any]]]:
        """Test endpoint file listing."""
        try:
            self._print_info(f"Testing file listing for {endpoint_name}...")
            files = []
            
            # Get a small sample of files
            async for file_metadata in client.list_files(max_results=max_files):
                files.append({
                    'title': file_metadata.title,
                    'date_updated': file_metadata.date_updated,
                    'external_id': file_metadata.external_id
                })
            
            if files:
                self._print_success(f"File listing successful (found {len(files)} files)")
                return True, files
            else:
                self._print_info("File listing successful (no files found)")
                return True, []
                
        except APIConnectionError as e:
            self._print_error(f"File listing failed: {e}")
            return False, []
        except Exception as e:
            self._print_error(f"File listing error: {e}")
            return False, []
    
    async def test_endpoint_health(self, client: BaseAPIClient, endpoint_name: str) -> bool:
        """Test endpoint health check."""
        try:
            self._print_info(f"Testing health check for {endpoint_name}...")
            healthy = await client.health_check()
            
            if healthy:
                self._print_success("Health check passed")
                return True
            else:
                self._print_error("Health check failed")
                return False
                
        except Exception as e:
            self._print_error(f"Health check error: {e}")
            return False
    
    async def test_single_endpoint(
        self, 
        endpoint_config: Dict[str, Any], 
        auth_only: bool = False, 
        max_files: int = 5
    ) -> Dict[str, Any]:
        """Test a single endpoint."""
        endpoint_name = endpoint_config.get('name', 'Unnamed Endpoint')
        endpoint_type = endpoint_config.get('endpoint_type') or endpoint_config.get('type')
        
        self._print_endpoint_header(endpoint_name, endpoint_type)
        
        result = {
            "name": endpoint_name,
            "type": endpoint_type,
            "authentication": {"success": False, "error": None},
            "file_listing": {"success": False, "error": None, "files_found": 0},
            "health_check": {"success": False, "error": None},
            "overall_success": False
        }
        
        try:
            # Create API client
            endpoint_details = endpoint_config.get('endpoint_details', {})
            client = APIClientFactory.create_client(endpoint_type, endpoint_details)
            
            # Test authentication
            auth_success = await self.test_endpoint_authentication(client, endpoint_name)
            result["authentication"]["success"] = auth_success
            
            if not auth_success:
                result["authentication"]["error"] = "Authentication failed"
                return result
            
            if not auth_only:
                # Test file listing
                file_success, files = await self.test_endpoint_file_listing(
                    client, endpoint_name, max_files
                )
                result["file_listing"]["success"] = file_success
                result["file_listing"]["files_found"] = len(files)
                
                if file_success:
                    self._print_files(files)
                else:
                    result["file_listing"]["error"] = "File listing failed"
                
                # Test health check
                health_success = await self.test_endpoint_health(client, endpoint_name)
                result["health_check"]["success"] = health_success
                
                if not health_success:
                    result["health_check"]["error"] = "Health check failed"
                
                # Overall success
                result["overall_success"] = auth_success and file_success and health_success
            else:
                result["overall_success"] = auth_success
            
        except Exception as e:
            error_msg = f"Endpoint test failed: {e}"
            self._print_error(error_msg)
            result["authentication"]["error"] = error_msg
        
        print()  # Add spacing between endpoints
        return result
    
    async def test_endpoints(
        self, 
        config_file: Optional[str] = None, 
        endpoint_type_filter: Optional[str] = None,
        auth_only: bool = False,
        max_files: int = 5
    ):
        """Test all configured endpoints."""
        self._print_header()
        
        try:
            # Load configuration
            if config_file and config_file.endswith('.json'):
                # Load JSON endpoints configuration
                with open(config_file, 'r') as f:
                    endpoints_data = json.load(f)
                endpoints = [
                    {
                        'name': f"{ep.get('type', 'Unknown')} Endpoint",
                        'endpoint_type': ep.get('type'),
                        'endpoint_details': ep.get('endpoint_details', {}),
                        **ep
                    }
                    for ep in endpoints_data
                    if ep.get('enabled', True)
                ]
            else:
                # Load YAML connector configuration
                config_loader = ConfigurationLoader()
                config = config_loader.load_configuration(config_file)
                endpoints = [
                    ep for ep in config.endpoints 
                    if ep.is_active and (not endpoint_type_filter or ep.endpoint_type.value == endpoint_type_filter)
                ]
                # Convert to dict format
                endpoints = [
                    {
                        'name': ep.name,
                        'endpoint_type': ep.endpoint_type.value,
                        'endpoint_details': ep.endpoint_details or {},
                        'project_id': ep.project_id,
                        'user_id': ep.user_id
                    }
                    for ep in endpoints
                ]
            
            if not endpoints:
                print("❌ No active endpoints found to test")
                if endpoint_type_filter:
                    print(f"   (filtered by type: {endpoint_type_filter})")
                return
            
            # Filter by endpoint type if specified
            if endpoint_type_filter:
                endpoints = [ep for ep in endpoints if ep['endpoint_type'] == endpoint_type_filter]
                if not endpoints:
                    print(f"❌ No endpoints found for type: {endpoint_type_filter}")
                    return
            
            print(f"Testing {len(endpoints)} endpoint(s)...\n")
            
            # Test each endpoint
            for endpoint_config in endpoints:
                result = await self.test_single_endpoint(
                    endpoint_config, auth_only, max_files
                )
                self.results["endpoints"].append(result)
                
                # Update summary
                self.results["summary"]["total"] += 1
                if result["overall_success"]:
                    self.results["summary"]["passed"] += 1
                else:
                    self.results["summary"]["failed"] += 1
            
            # Print final summary
            self._print_summary()
            
        except FileNotFoundError as e:
            print(f"❌ Configuration file not found: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
            sys.exit(1)
    
    def _print_summary(self):
        """Print test summary."""
        summary = self.results["summary"]
        total = summary["total"]
        passed = summary["passed"]
        failed = summary["failed"]
        
        print("=" * 50)
        print("📊 Test Summary")
        print("=" * 50)
        print(f"Total endpoints tested: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        
        if failed == 0:
            print("\n🎉 All endpoints tested successfully!")
        else:
            print(f"\n⚠️  {failed} endpoint(s) need attention")
            
            # Show failed endpoints
            for endpoint in self.results["endpoints"]:
                if not endpoint["overall_success"]:
                    print(f"   - {endpoint['name']}: ", end="")
                    errors = []
                    if not endpoint["authentication"]["success"]:
                        errors.append("Auth failed")
                    if not endpoint["file_listing"]["success"]:
                        errors.append("File listing failed")
                    if not endpoint["health_check"]["success"]:
                        errors.append("Health check failed")
                    print(", ".join(errors))
        
        print()
    
    def save_results(self, output_file: str):
        """Save test results to JSON file."""
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"📄 Results saved to: {output_file}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Test File Connector endpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Test all endpoints
  %(prog)s --type google_drive               # Test Google Drive only
  %(prog)s --type autodesk_construction_cloud # Test Autodesk only
  %(prog)s --verbose                         # Show detailed output
  %(prog)s --auth-only                       # Test authentication only
  %(prog)s --config config/test.yaml         # Use specific config
  %(prog)s --max-files 10                    # Fetch up to 10 files per endpoint
        """
    )
    
    parser.add_argument(
        "--type", 
        choices=["google_drive", "autodesk_construction_cloud"],
        help="Test only endpoints of specified type"
    )
    parser.add_argument(
        "--config", 
        help="Configuration file path (default: config/connector.yaml or config/endpoints.json)"
    )
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true",
        help="Show verbose output"
    )
    parser.add_argument(
        "--auth-only", 
        action="store_true",
        help="Test authentication only (skip file listing)"
    )
    parser.add_argument(
        "--max-files", 
        type=int, 
        default=5,
        help="Maximum number of files to fetch per endpoint (default: 5)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Save results to JSON file"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Minimal output (only errors and summary)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "ERROR" if args.quiet else ("DEBUG" if args.verbose else "WARNING")
    setup_logging(level=log_level, format_type="console")
    
    # Load environment settings
    try:
        load_settings()
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        print("   Make sure your .env file is configured correctly")
        sys.exit(1)
    
    # Determine config file
    config_file = args.config
    if not config_file:
        # Try to find default config files
        project_dir = Path(__file__).parent.parent
        yaml_config = project_dir / "config" / "connector.yaml"
        json_config = project_dir / "config" / "endpoints.json"
        
        if yaml_config.exists():
            config_file = str(yaml_config)
        elif json_config.exists():
            config_file = str(json_config)
        else:
            print("❌ No configuration file found")
            print("   Expected: config/connector.yaml or config/endpoints.json")
            print("   Or specify with --config option")
            sys.exit(1)
    
    # Create tester and run tests
    tester = EndpointTester(verbose=args.verbose and not args.quiet)
    
    await tester.test_endpoints(
        config_file=config_file,
        endpoint_type_filter=args.type,
        auth_only=args.auth_only,
        max_files=args.max_files
    )
    
    # Save results if requested
    if args.output:
        tester.save_results(args.output)
    
    # Exit with appropriate code
    failed_count = tester.results["summary"]["failed"]
    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    # Set event loop policy for Windows compatibility
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)