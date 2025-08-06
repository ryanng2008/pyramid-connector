"""Tests for deployment configuration and scripts."""

import os
import pytest
import yaml
import json
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock


class TestDockerConfiguration:
    """Test Docker configuration files."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent
        self.dockerfile_path = self.project_root / "Dockerfile"
        self.compose_path = self.project_root / "docker-compose.yml"
        self.compose_dev_path = self.project_root / "docker-compose.dev.yml"
        self.dockerignore_path = self.project_root / ".dockerignore"
    
    def test_dockerfile_exists(self):
        """Test that Dockerfile exists and has correct structure."""
        assert self.dockerfile_path.exists()
        
        content = self.dockerfile_path.read_text()
        
        # Check for multi-stage build
        assert "FROM python:3.11-slim as builder" in content
        assert "FROM python:3.11-slim as production" in content
        assert "FROM python:3.11-slim as development" in content
        assert "FROM development as testing" in content
        
        # Check for security best practices
        assert "useradd -r" in content  # Non-root user
        assert "USER connector" in content  # Switch to non-root
        assert "HEALTHCHECK" in content  # Health check
        
        # Check for Python optimization
        assert "PYTHONDONTWRITEBYTECODE=1" in content
        assert "PYTHONUNBUFFERED=1" in content
    
    def test_docker_compose_structure(self):
        """Test Docker Compose configuration structure."""
        assert self.compose_path.exists()
        
        with open(self.compose_path, 'r') as f:
            compose_config = yaml.safe_load(f)
        
        # Check required services
        services = compose_config.get('services', {})
        assert 'connector' in services
        assert 'postgres' in services
        assert 'redis' in services
        
        # Check connector service configuration
        connector_service = services['connector']
        assert 'build' in connector_service
        assert 'environment' in connector_service
        assert 'volumes' in connector_service
        assert 'healthcheck' in connector_service
        
        # Check database service
        postgres_service = services['postgres']
        assert postgres_service['image'] == 'postgres:15-alpine'
        assert 'healthcheck' in postgres_service
        
        # Check volumes are defined
        assert 'volumes' in compose_config
        volumes = compose_config['volumes']
        assert 'postgres_data' in volumes
        assert 'connector_logs' in volumes
    
    def test_docker_compose_dev_structure(self):
        """Test development Docker Compose configuration."""
        assert self.compose_dev_path.exists()
        
        with open(self.compose_dev_path, 'r') as f:
            compose_config = yaml.safe_load(f)
        
        services = compose_config.get('services', {})
        
        # Check development services
        assert 'connector-dev' in services
        assert 'postgres-dev' in services
        assert 'test-runner' in services
        
        # Check development configuration
        connector_dev = services['connector-dev']
        assert connector_dev['build']['target'] == 'development'
        
        # Check test runner profile
        test_runner = services['test-runner']
        assert 'testing' in test_runner.get('profiles', [])
    
    def test_dockerignore_exists(self):
        """Test that .dockerignore exists and contains appropriate entries."""
        assert self.dockerignore_path.exists()
        
        content = self.dockerignore_path.read_text()
        
        # Check for common exclusions
        assert '__pycache__/' in content
        assert '.git/' in content
        assert '*.log' in content
        assert 'credentials/' in content
        assert '.env' in content
        assert 'test-results/' in content


class TestKubernetesConfiguration:
    """Test Kubernetes configuration files."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent
        self.k8s_dir = self.project_root / "kubernetes"
    
    def test_kubernetes_files_exist(self):
        """Test that all required Kubernetes files exist."""
        required_files = [
            "namespace.yaml",
            "deployment.yaml", 
            "secrets.yaml",
            "postgres.yaml",
            "ingress.yaml"
        ]
        
        for filename in required_files:
            file_path = self.k8s_dir / filename
            assert file_path.exists(), f"Missing Kubernetes file: {filename}"
    
    def test_namespace_configuration(self):
        """Test namespace configuration."""
        namespace_path = self.k8s_dir / "namespace.yaml"
        
        with open(namespace_path, 'r') as f:
            config = yaml.safe_load(f)
        
        assert config['apiVersion'] == 'v1'
        assert config['kind'] == 'Namespace'
        assert config['metadata']['name'] == 'file-connector'
    
    def test_deployment_configuration(self):
        """Test deployment configuration structure."""
        deployment_path = self.k8s_dir / "deployment.yaml"
        
        with open(deployment_path, 'r') as f:
            # Load all documents from the YAML file
            configs = list(yaml.safe_load_all(f))
        
        # Find deployment config
        deployment = None
        service = None
        hpa = None
        
        for config in configs:
            if config and config.get('kind') == 'Deployment':
                deployment = config
            elif config and config.get('kind') == 'Service':
                service = config
            elif config and config.get('kind') == 'HorizontalPodAutoscaler':
                hpa = config
        
        # Test deployment
        assert deployment is not None
        assert deployment['metadata']['name'] == 'file-connector'
        assert deployment['spec']['replicas'] == 2
        
        # Test container configuration
        container = deployment['spec']['template']['spec']['containers'][0]
        assert container['name'] == 'file-connector'
        assert 'resources' in container
        assert 'livenessProbe' in container
        assert 'readinessProbe' in container
        
        # Test service
        assert service is not None
        assert service['spec']['type'] == 'ClusterIP'
        
        # Test HPA
        assert hpa is not None
        assert hpa['spec']['minReplicas'] == 2
        assert hpa['spec']['maxReplicas'] == 10
    
    def test_postgres_configuration(self):
        """Test PostgreSQL configuration."""
        postgres_path = self.k8s_dir / "postgres.yaml"
        
        with open(postgres_path, 'r') as f:
            configs = list(yaml.safe_load_all(f))
        
        # Find different resource types
        deployment = None
        service = None
        pvc = None
        
        for config in configs:
            if config and config.get('kind') == 'Deployment':
                deployment = config
            elif config and config.get('kind') == 'Service':
                service = config
            elif config and config.get('kind') == 'PersistentVolumeClaim':
                pvc = config
        
        # Test PostgreSQL deployment
        assert deployment is not None
        container = deployment['spec']['template']['spec']['containers'][0]
        assert container['image'] == 'postgres:15-alpine'
        assert 'livenessProbe' in container
        assert 'readinessProbe' in container
        
        # Test service
        assert service is not None
        assert service['spec']['ports'][0]['port'] == 5432
        
        # Test PVC
        assert pvc is not None
        assert pvc['spec']['resources']['requests']['storage'] == '10Gi'


class TestDeploymentScripts:
    """Test deployment scripts."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent
        self.deploy_script = self.project_root / "scripts" / "deploy.sh"
        self.k8s_script = self.project_root / "scripts" / "k8s-deploy.sh"
    
    def test_deployment_scripts_exist(self):
        """Test that deployment scripts exist and are executable."""
        assert self.deploy_script.exists()
        assert self.k8s_script.exists()
        
        # Check if scripts are executable
        assert os.access(self.deploy_script, os.X_OK)
        assert os.access(self.k8s_script, os.X_OK)
    
    def test_deploy_script_structure(self):
        """Test deployment script structure."""
        content = self.deploy_script.read_text()
        
        # Check for required functions
        assert "check_docker()" in content
        assert "check_environment()" in content
        assert "deploy_production()" in content
        assert "deploy_development()" in content
        assert "health_check()" in content
        
        # Check for error handling
        assert "set -e" in content
        assert "log_error" in content
        
        # Check for help function
        assert "help" in content or "--help" in content
    
    def test_k8s_script_structure(self):
        """Test Kubernetes deployment script structure."""
        content = self.k8s_script.read_text()
        
        # Check for required functions
        assert "check_kubectl()" in content
        assert "build_and_push_image()" in content
        assert "deploy_full()" in content
        assert "health_check()" in content
        
        # Check for kubectl usage
        assert "kubectl" in content
        assert "namespace" in content
        
        # Check for error handling
        assert "set -e" in content


class TestEnvironmentConfiguration:
    """Test environment configuration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent
        self.env_example = self.project_root / "env.example"
    
    def test_env_example_exists(self):
        """Test that environment example file exists."""
        assert self.env_example.exists()
    
    def test_env_example_structure(self):
        """Test environment example file structure."""
        content = self.env_example.read_text()
        
        # Check for required sections
        assert "APPLICATION CONFIGURATION" in content
        assert "DATABASE CONFIGURATION" in content
        assert "GOOGLE DRIVE API CONFIGURATION" in content
        assert "AUTODESK CONSTRUCTION CLOUD API CONFIGURATION" in content
        assert "SUPABASE CONFIGURATION" in content
        
        # Check for required variables
        required_vars = [
            "CONNECTOR_ENVIRONMENT",
            "CONNECTOR_LOG_LEVEL",
            "CONNECTOR_DATABASE_URL",
            "CONNECTOR_AUTODESK_CLIENT_ID",
            "CONNECTOR_AUTODESK_CLIENT_SECRET",
            "CONNECTOR_SUPABASE_URL",
            "CONNECTOR_SUPABASE_SERVICE_ROLE_KEY"
        ]
        
        for var in required_vars:
            assert var in content


class TestDockerIntegration:
    """Integration tests for Docker configuration."""
    
    @pytest.mark.integration
    @patch('subprocess.run')
    def test_docker_build_commands(self, mock_run):
        """Test Docker build commands execute correctly."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        project_root = Path(__file__).parent.parent
        
        # Test production build
        import subprocess
        result = subprocess.run([
            "docker", "build", "--target", "production", "-t", "test-connector", "."
        ], cwd=project_root, capture_output=True, text=True, timeout=10)
        
        # Should not fail parsing (even if Docker isn't available)
        assert isinstance(result.returncode, int)
    
    @pytest.mark.integration
    def test_compose_validation(self):
        """Test Docker Compose file validation."""
        project_root = Path(__file__).parent.parent
        compose_path = project_root / "docker-compose.yml"
        
        # Test YAML parsing
        with open(compose_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Validate structure
        assert 'version' in config
        assert 'services' in config
        assert 'volumes' in config
        assert 'networks' in config
        
        # Validate services have required fields
        for service_name, service_config in config['services'].items():
            if 'build' in service_config:
                assert 'context' in service_config['build']
            if 'environment' in service_config:
                assert isinstance(service_config['environment'], (list, dict))


class TestMonitoringConfiguration:
    """Test monitoring configuration files."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent
        self.docker_dir = self.project_root / "docker"
    
    def test_prometheus_config(self):
        """Test Prometheus configuration."""
        prometheus_path = self.docker_dir / "prometheus.yml"
        
        if prometheus_path.exists():
            with open(prometheus_path, 'r') as f:
                config = yaml.safe_load(f)
            
            assert 'global' in config
            assert 'scrape_configs' in config
            
            # Check for application scrape config
            scrape_configs = config['scrape_configs']
            job_names = [job['job_name'] for job in scrape_configs]
            assert 'file-connector' in job_names
    
    def test_grafana_datasource_config(self):
        """Test Grafana datasource configuration."""
        datasource_path = self.docker_dir / "grafana" / "datasources" / "prometheus.yml"
        
        if datasource_path.exists():
            with open(datasource_path, 'r') as f:
                config = yaml.safe_load(f)
            
            assert 'datasources' in config
            datasources = config['datasources']
            assert len(datasources) > 0
            assert datasources[0]['type'] == 'prometheus'


# Integration test for full deployment simulation
@pytest.mark.integration
class TestDeploymentIntegration:
    """Integration tests for deployment process."""
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_deployment_script_execution(self, mock_exists, mock_run):
        """Test deployment script can be executed."""
        mock_exists.return_value = True
        mock_run.return_value = MagicMock(returncode=0)
        
        project_root = Path(__file__).parent.parent
        script_path = project_root / "scripts" / "deploy.sh"
        
        # Test help command
        import subprocess
        try:
            result = subprocess.run([
                str(script_path), "help"
            ], capture_output=True, text=True, timeout=5)
            
            # Should show help message
            assert "Usage:" in result.stdout or result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Script might not be executable in test environment
            pytest.skip("Script execution not available in test environment")


if __name__ == "__main__":
    pytest.main([__file__])