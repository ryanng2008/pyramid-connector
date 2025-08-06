# Testing Guide for File Connector

This document provides comprehensive information about testing the File Connector application.

## Table of Contents

- [Overview](#overview)
- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Test Types](#test-types)
- [CI/CD Pipeline](#cicd-pipeline)
- [Quality Standards](#quality-standards)
- [Contributing](#contributing)

## Overview

The File Connector project maintains high quality standards through comprehensive testing, including:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions and workflows
- **Quality Tests**: Ensure code quality and best practices
- **Performance Tests**: Validate performance and identify regressions
- **Security Tests**: Check for security vulnerabilities
- **Deployment Tests**: Validate Docker and Kubernetes configurations

## Test Structure

```
tests/
├── test_database.py          # Database layer tests
├── test_google_drive_client.py # Google Drive API client tests
├── test_autodesk_client.py   # Autodesk API client tests
├── test_core_connector.py    # Core connector logic tests
├── test_configuration.py     # Configuration management tests
├── test_scheduler.py         # Scheduling system tests
├── test_performance.py       # Performance optimization tests
├── test_deployment.py        # Deployment configuration tests
├── test_integration.py       # Integration and end-to-end tests
├── test_quality.py          # Code quality and standards tests
└── fixtures/                # Test fixtures and mock data
    └── mock_credentials.json
```

## Running Tests

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=src/connector --cov-report=html
```

### Using the Test Script

The project includes a comprehensive test script that handles environment setup and runs various test types:

```bash
# Run all tests
./scripts/test.sh all

# Run quick checks (formatting, linting, unit tests)
./scripts/test.sh quick

# Run specific test types
./scripts/test.sh unit
./scripts/test.sh integration
./scripts/test.sh security
./scripts/test.sh performance

# Get help
./scripts/test.sh help
```

### Test Environment Setup

The test script automatically sets up the test environment:

1. **Virtual Environment**: Creates and activates a Python virtual environment
2. **Dependencies**: Installs test dependencies and tools
3. **Test Database**: Configures in-memory SQLite for testing
4. **Mock Services**: Sets up mock credentials and service configurations
5. **Environment Variables**: Configures test-specific environment variables

### Docker-based Testing

For integration tests that require real services:

```bash
# Start test services
docker-compose -f docker-compose.dev.yml up -d postgres-dev redis-dev

# Run integration tests
pytest tests/test_integration.py -m integration

# Clean up
docker-compose -f docker-compose.dev.yml down
```

## Test Types

### Unit Tests

Test individual components in isolation with mocked dependencies.

```bash
# Run all unit tests
pytest tests/ -m "not integration and not performance"

# Run specific test files
pytest tests/test_database.py -v
pytest tests/test_google_drive_client.py -v
```

**Coverage Requirements:**
- Minimum 80% code coverage
- All public methods must be tested
- Error conditions must be tested

### Integration Tests

Test component interactions and complete workflows.

```bash
# Run integration tests
pytest tests/test_integration.py -m integration -v

# Run end-to-end tests
pytest tests/test_integration.py::TestEndToEndWorkflow -v
```

**Integration Test Categories:**
- Database integration with SQLAlchemy
- API client integration with mocked services
- Sync engine workflows
- Performance component integration
- Complete end-to-end workflows

### Quality Tests

Ensure code quality and adherence to best practices.

```bash
# Run quality tests
pytest tests/test_quality.py -v

# Run specific quality checks
./scripts/test.sh lint
./scripts/test.sh security
./scripts/test.sh complexity
```

**Quality Checks:**
- Code formatting (Black)
- Linting (Flake8)
- Type checking (MyPy)
- Security scanning (Bandit, Safety)
- Complexity analysis (Radon, Xenon)
- Documentation coverage

### Performance Tests

Validate performance and identify regressions.

```bash
# Run performance tests
pytest tests/test_integration.py -m benchmark -v

# Generate benchmark reports
pytest tests/test_integration.py::TestPerformanceBenchmarks \
    --benchmark-json=benchmark-results.json
```

**Performance Metrics:**
- Database batch operation performance
- API client response times
- Memory usage profiling
- Concurrent operation efficiency

### Security Tests

Check for security vulnerabilities and best practices.

```bash
# Run security scans
./scripts/test.sh security

# Individual security tools
bandit -r src/
safety check
```

**Security Checks:**
- Static code analysis (Bandit)
- Dependency vulnerability scanning (Safety)
- Hardcoded secret detection
- SQL injection pattern detection
- Input validation verification

## CI/CD Pipeline

The project uses GitHub Actions for continuous integration and deployment:

### Main CI Pipeline (`.github/workflows/ci.yml`)

Runs on every push and pull request:

1. **Code Quality**: Formatting, linting, type checking, security scanning
2. **Unit Tests**: Multi-version Python testing with PostgreSQL and Redis
3. **Integration Tests**: Component integration and end-to-end testing
4. **Docker Build**: Container building and testing
5. **Performance Tests**: Performance regression testing
6. **Security Scan**: Trivy vulnerability scanning
7. **Deployment**: Production deployment (main branch only)

### Quality Assurance Pipeline (`.github/workflows/quality.yml`)

Weekly comprehensive quality assessment:

1. **Code Quality Analysis**: Complexity and maintainability metrics
2. **Test Quality Assessment**: Coverage analysis and test effectiveness
3. **Documentation Quality**: Docstring coverage and style checking
4. **Performance Regression**: Benchmark comparison and memory profiling
5. **Dependency Audit**: Security and license compliance
6. **Code Duplication Detection**: Duplicate code identification
7. **API Compatibility**: API structure analysis

### Pipeline Configuration

**Environment Variables:**
```yaml
PYTHON_VERSION: '3.11'
REGISTRY: ghcr.io
IMAGE_NAME: ${{ github.repository }}
```

**Service Dependencies:**
- PostgreSQL 15 for database testing
- Redis 7 for caching tests
- Docker for container testing

**Artifacts:**
- Test coverage reports
- Security scan results
- Performance benchmarks
- Quality analysis reports

## Quality Standards

### Code Quality Requirements

1. **Formatting**: Black code formatting enforced
2. **Linting**: Flake8 with max line length 100
3. **Type Hints**: MyPy type checking required
4. **Documentation**: Docstrings required for public methods
5. **Complexity**: Maximum cyclomatic complexity B (moderate)
6. **Coverage**: Minimum 80% test coverage

### Security Requirements

1. **No Hardcoded Secrets**: Automated detection and prevention
2. **Input Validation**: Pydantic validation for all inputs
3. **SQL Injection Prevention**: Parameterized queries only
4. **Dependency Security**: Regular vulnerability scanning
5. **Container Security**: Non-root containers, minimal attack surface

### Performance Standards

1. **Database Operations**: Batch operations for large datasets
2. **API Calls**: Connection pooling and rate limiting
3. **Memory Usage**: Efficient data structures and cleanup
4. **Concurrency**: Async/await patterns throughout
5. **Resource Limits**: Configurable connection and batch limits

## Test Configuration

### pytest.ini

Key configuration options:

```ini
[tool:pytest]
testpaths = tests
addopts = 
    --strict-markers
    --cov=src/connector
    --cov-fail-under=80
    --disable-warnings
markers =
    unit: Unit tests
    integration: Integration tests
    performance: Performance tests
    benchmark: Benchmark tests
```

### Test Markers

Use markers to categorize and run specific test types:

```python
@pytest.mark.unit
def test_database_model():
    """Unit test for database model."""
    pass

@pytest.mark.integration
async def test_sync_workflow():
    """Integration test for sync workflow."""
    pass

@pytest.mark.performance
def test_batch_performance():
    """Performance test for batch operations."""
    pass
```

### Fixtures and Mocks

Common test fixtures:

```python
@pytest.fixture
async def db_service():
    """Database service fixture."""
    db_manager = DatabaseManager("sqlite:///:memory:")
    db_manager.create_tables()
    yield DatabaseService(db_manager)
    await db_manager.close()

@pytest.fixture
def mock_api_client():
    """Mock API client fixture."""
    return AsyncMock()
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure PYTHONPATH includes src directory
2. **Database Errors**: Check test database configuration
3. **Async Test Issues**: Use pytest-asyncio and proper async fixtures
4. **Mock Failures**: Verify mock setup and async context managers
5. **Coverage Issues**: Check for missing test files or uncovered code

### Debugging Tests

```bash
# Run with verbose output
pytest -v -s

# Run specific test with debugging
pytest tests/test_database.py::TestDatabaseService::test_create_endpoint -v -s

# Debug with pdb
pytest --pdb tests/test_database.py

# Show local variables on failure
pytest --tb=long --showlocals
```

### Performance Debugging

```bash
# Profile test execution
pytest tests/ --durations=10

# Memory profiling
pytest tests/test_integration.py --profile

# Benchmark comparison
pytest tests/test_integration.py -m benchmark --benchmark-compare-fail=min:5%
```

## Contributing

### Adding New Tests

1. **Test File Naming**: Use `test_*.py` pattern
2. **Test Function Naming**: Use `test_*` pattern
3. **Test Classes**: Use `Test*` pattern for grouping
4. **Docstrings**: Add clear descriptions for test purpose
5. **Markers**: Use appropriate markers for test categorization

### Test Guidelines

1. **Isolation**: Tests should not depend on each other
2. **Deterministic**: Tests should produce consistent results
3. **Fast**: Unit tests should run quickly
4. **Clear**: Test names should clearly indicate what is being tested
5. **Comprehensive**: Cover normal cases, edge cases, and error conditions

### Code Review Checklist

- [ ] All tests pass locally
- [ ] New code has corresponding tests
- [ ] Test coverage meets minimum requirements
- [ ] Security scans pass
- [ ] Performance tests pass
- [ ] Documentation is updated
- [ ] CI pipeline passes

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [coverage.py](https://coverage.readthedocs.io/)
- [Bandit Security Linter](https://bandit.readthedocs.io/)
- [Safety](https://pyup.io/safety/)
- [Black Code Formatter](https://black.readthedocs.io/)
- [Flake8 Linter](https://flake8.pycqa.org/)
- [MyPy Type Checker](https://mypy.readthedocs.io/)