#!/bin/bash
# Comprehensive testing script for File Connector

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${PROJECT_DIR}/venv"
REPORTS_DIR="${PROJECT_DIR}/test-reports"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Setup test environment
setup_test_environment() {
    log_info "Setting up test environment..."
    
    cd "$PROJECT_DIR"
    
    # Create reports directory
    mkdir -p "$REPORTS_DIR"
    
    # Create virtual environment if it doesn't exist
    if [[ ! -d "$VENV_DIR" ]]; then
        log_info "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi
    
    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install dependencies
    log_info "Installing dependencies..."
    pip install -r requirements.txt
    
    # Install test dependencies
    pip install pytest pytest-asyncio pytest-cov pytest-mock pytest-html pytest-json-report \
                coverage bandit safety flake8 black mypy radon xenon
    
    # Create test environment file
    cat > .env.test << EOF
CONNECTOR_ENVIRONMENT=testing
CONNECTOR_LOG_LEVEL=DEBUG
CONNECTOR_DATABASE_URL=sqlite:///:memory:
CONNECTOR_REDIS_URL=redis://localhost:6379
CONNECTOR_GOOGLE_DRIVE_CREDENTIALS_PATH=./tests/fixtures/mock_credentials.json
CONNECTOR_AUTODESK_CLIENT_ID=test_client_id
CONNECTOR_AUTODESK_CLIENT_SECRET=test_client_secret
CONNECTOR_SUPABASE_URL=http://localhost:54321
CONNECTOR_SUPABASE_SERVICE_ROLE_KEY=test_service_role_key
CONNECTOR_MAX_CONCURRENT_SYNCS=5
EOF
    
    # Create mock credentials for testing
    mkdir -p tests/fixtures
    cat > tests/fixtures/mock_credentials.json << EOF
{
  "type": "service_account",
  "project_id": "test-project",
  "private_key_id": "test-key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\\ntest\\n-----END PRIVATE KEY-----\\n",
  "client_email": "test@test.iam.gserviceaccount.com",
  "client_id": "test-client-id",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token"
}
EOF
    
    log_success "Test environment setup completed"
}

# Run code formatting checks
run_formatting_checks() {
    log_info "Running code formatting checks..."
    
    # Black formatting check
    if black --check --diff src/ tests/; then
        log_success "Black formatting check passed"
    else
        log_error "Black formatting check failed"
        return 1
    fi
}

# Run linting
run_linting() {
    log_info "Running linting checks..."
    
    # Flake8 linting
    if flake8 src/ tests/ --max-line-length=100 --ignore=E203,W503 \
              --tee --output-file="$REPORTS_DIR/flake8-report.txt"; then
        log_success "Flake8 linting passed"
    else
        log_warning "Flake8 linting found issues (see report)"
    fi
}

# Run type checking
run_type_checking() {
    log_info "Running type checking..."
    
    # MyPy type checking
    if mypy src/ --ignore-missing-imports --disallow-untyped-defs \
              --html-report="$REPORTS_DIR/mypy-report" \
              --txt-report="$REPORTS_DIR" --reports; then
        log_success "MyPy type checking passed"
    else
        log_warning "MyPy type checking found issues (see report)"
    fi
}

# Run security checks
run_security_checks() {
    log_info "Running security checks..."
    
    # Bandit security linting
    if bandit -r src/ -f json -o "$REPORTS_DIR/bandit-report.json" \
              -f txt -o "$REPORTS_DIR/bandit-report.txt"; then
        log_success "Bandit security check passed"
    else
        log_warning "Bandit security check found issues (see report)"
    fi
    
    # Safety dependency check
    if safety check --json --output "$REPORTS_DIR/safety-report.json" \
              --short-report --output "$REPORTS_DIR/safety-report.txt"; then
        log_success "Safety dependency check passed"
    else
        log_warning "Safety dependency check found vulnerabilities (see report)"
    fi
}

# Run unit tests
run_unit_tests() {
    log_info "Running unit tests..."
    
    # Set test environment
    export $(cat .env.test | xargs)
    
    # Run pytest with coverage
    if pytest tests/ \
              --tb=short \
              --cov=src/connector \
              --cov-report=html:"$REPORTS_DIR/coverage-html" \
              --cov-report=xml:"$REPORTS_DIR/coverage.xml" \
              --cov-report=term-missing \
              --html="$REPORTS_DIR/test-report.html" \
              --json-report --json-report-file="$REPORTS_DIR/test-results.json" \
              --junitxml="$REPORTS_DIR/junit.xml" \
              -v; then
        log_success "Unit tests passed"
    else
        log_error "Unit tests failed"
        return 1
    fi
}

# Run integration tests
run_integration_tests() {
    log_info "Running integration tests..."
    
    # Check if Docker is available for integration tests
    if command -v docker &> /dev/null && docker info &> /dev/null; then
        log_info "Docker available, running full integration tests..."
        
        # Start test services
        docker-compose -f docker-compose.dev.yml up -d postgres-dev redis-dev
        
        # Wait for services to be ready
        sleep 10
        
        # Update test environment for integration tests
        export CONNECTOR_DATABASE_URL="postgresql://connector:connector123@localhost:5433/connector_dev"
        export CONNECTOR_REDIS_URL="redis://localhost:6380"
        
        # Run integration tests
        if pytest tests/test_integration.py \
                  --tb=short \
                  -m integration \
                  --html="$REPORTS_DIR/integration-test-report.html" \
                  -v; then
            log_success "Integration tests passed"
        else
            log_error "Integration tests failed"
            docker-compose -f docker-compose.dev.yml down
            return 1
        fi
        
        # Cleanup
        docker-compose -f docker-compose.dev.yml down
    else
        log_warning "Docker not available, skipping integration tests"
        
        # Run integration tests with mocks only
        if pytest tests/test_integration.py \
                  --tb=short \
                  --html="$REPORTS_DIR/integration-test-report.html" \
                  -v; then
            log_success "Integration tests (mocked) passed"
        else
            log_error "Integration tests (mocked) failed"
            return 1
        fi
    fi
}

# Run quality tests
run_quality_tests() {
    log_info "Running quality tests..."
    
    if pytest tests/test_quality.py \
              --tb=short \
              --html="$REPORTS_DIR/quality-test-report.html" \
              -v; then
        log_success "Quality tests passed"
    else
        log_warning "Quality tests found issues (see report)"
    fi
}

# Run performance tests
run_performance_tests() {
    log_info "Running performance tests..."
    
    if pytest tests/test_integration.py::TestPerformanceBenchmarks \
              --tb=short \
              --benchmark-json="$REPORTS_DIR/benchmark-results.json" \
              --benchmark-sort=mean \
              -v; then
        log_success "Performance tests completed"
    else
        log_warning "Performance tests had issues (see report)"
    fi
}

# Run complexity analysis
run_complexity_analysis() {
    log_info "Running complexity analysis..."
    
    # Radon complexity analysis
    radon cc src/ --min=B --show-complexity --total-average > "$REPORTS_DIR/complexity-report.txt"
    radon cc src/ --json > "$REPORTS_DIR/complexity-report.json"
    
    # Radon maintainability index
    radon mi src/ --min=B --show > "$REPORTS_DIR/maintainability-report.txt"
    radon mi src/ --json > "$REPORTS_DIR/maintainability-report.json"
    
    # Xenon complexity check
    if xenon --max-absolute B --max-modules A --max-average A src/; then
        log_success "Complexity analysis passed"
    else
        log_warning "Complexity analysis found issues (see report)"
    fi
}

# Generate test summary
generate_test_summary() {
    log_info "Generating test summary..."
    
    cat > "$REPORTS_DIR/test-summary.md" << EOF
# Test Summary Report

Generated on: $(date)

## Test Results

### Unit Tests
- Report: [test-report.html](test-report.html)
- Coverage: [coverage-html/index.html](coverage-html/index.html)
- Results: [test-results.json](test-results.json)

### Code Quality
- Flake8: [flake8-report.txt](flake8-report.txt)
- MyPy: [mypy-report/index.html](mypy-report/index.html)
- Bandit: [bandit-report.json](bandit-report.json)
- Safety: [safety-report.json](safety-report.json)

### Integration Tests
- Report: [integration-test-report.html](integration-test-report.html)

### Quality Tests
- Report: [quality-test-report.html](quality-test-report.html)

### Performance Tests
- Benchmarks: [benchmark-results.json](benchmark-results.json)

### Complexity Analysis
- Complexity: [complexity-report.txt](complexity-report.txt)
- Maintainability: [maintainability-report.txt](maintainability-report.txt)

## Coverage Summary

EOF
    
    # Add coverage summary if available
    if [[ -f "$REPORTS_DIR/coverage.xml" ]]; then
        python3 -c "
import xml.etree.ElementTree as ET
try:
    tree = ET.parse('$REPORTS_DIR/coverage.xml')
    root = tree.getroot()
    coverage = root.attrib.get('line-rate', '0')
    coverage_pct = float(coverage) * 100
    print(f'Overall Coverage: {coverage_pct:.2f}%')
except Exception as e:
    print('Coverage data not available')
" >> "$REPORTS_DIR/test-summary.md"
    fi
    
    log_success "Test summary generated at $REPORTS_DIR/test-summary.md"
}

# Open test reports
open_reports() {
    if command -v open &> /dev/null; then
        log_info "Opening test reports..."
        open "$REPORTS_DIR/test-summary.md"
        open "$REPORTS_DIR/test-report.html"
        open "$REPORTS_DIR/coverage-html/index.html"
    elif command -v xdg-open &> /dev/null; then
        log_info "Opening test reports..."
        xdg-open "$REPORTS_DIR/test-summary.md"
        xdg-open "$REPORTS_DIR/test-report.html"
        xdg-open "$REPORTS_DIR/coverage-html/index.html"
    else
        log_info "Test reports are available at: $REPORTS_DIR"
    fi
}

# Clean up
cleanup() {
    log_info "Cleaning up test environment..."
    
    # Remove test environment file
    rm -f .env.test
    
    # Deactivate virtual environment
    if [[ "$VIRTUAL_ENV" != "" ]]; then
        deactivate
    fi
    
    log_success "Cleanup completed"
}

# Main execution
main() {
    local test_type="${1:-all}"
    local failed_tests=0
    
    log_info "Starting File Connector test suite..."
    log_info "Test type: $test_type"
    
    # Setup
    setup_test_environment
    
    case "$test_type" in
        "format"|"formatting")
            run_formatting_checks || ((failed_tests++))
            ;;
        "lint"|"linting")
            run_linting || ((failed_tests++))
            ;;
        "type"|"typing")
            run_type_checking || ((failed_tests++))
            ;;
        "security")
            run_security_checks || ((failed_tests++))
            ;;
        "unit")
            run_unit_tests || ((failed_tests++))
            ;;
        "integration")
            run_integration_tests || ((failed_tests++))
            ;;
        "quality")
            run_quality_tests || ((failed_tests++))
            ;;
        "performance")
            run_performance_tests || ((failed_tests++))
            ;;
        "complexity")
            run_complexity_analysis || ((failed_tests++))
            ;;
        "quick")
            run_formatting_checks || ((failed_tests++))
            run_linting || ((failed_tests++))
            run_unit_tests || ((failed_tests++))
            ;;
        "ci")
            run_formatting_checks || ((failed_tests++))
            run_linting || ((failed_tests++))
            run_type_checking || ((failed_tests++))
            run_security_checks || ((failed_tests++))
            run_unit_tests || ((failed_tests++))
            run_integration_tests || ((failed_tests++))
            run_quality_tests || ((failed_tests++))
            ;;
        "all")
            run_formatting_checks || ((failed_tests++))
            run_linting || ((failed_tests++))
            run_type_checking || ((failed_tests++))
            run_security_checks || ((failed_tests++))
            run_unit_tests || ((failed_tests++))
            run_integration_tests || ((failed_tests++))
            run_quality_tests || ((failed_tests++))
            run_performance_tests || ((failed_tests++))
            run_complexity_analysis || ((failed_tests++))
            ;;
        "help"|"--help"|"-h")
            echo "File Connector Test Script"
            echo
            echo "Usage: $0 [TEST_TYPE]"
            echo
            echo "Test Types:"
            echo "  format, formatting    Run code formatting checks"
            echo "  lint, linting        Run linting checks"
            echo "  type, typing         Run type checking"
            echo "  security             Run security checks"
            echo "  unit                 Run unit tests"
            echo "  integration          Run integration tests"
            echo "  quality              Run quality tests"
            echo "  performance          Run performance tests"
            echo "  complexity           Run complexity analysis"
            echo "  quick                Run quick checks (format, lint, unit)"
            echo "  ci                   Run CI checks (all except performance)"
            echo "  all                  Run all tests and checks"
            echo "  help                 Show this help message"
            echo
            echo "Examples:"
            echo "  $0 unit              # Run only unit tests"
            echo "  $0 quick             # Run quick checks"
            echo "  $0 all               # Run comprehensive test suite"
            exit 0
            ;;
        *)
            log_error "Unknown test type: $test_type"
            log_info "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
    
    # Generate summary
    generate_test_summary
    
    # Results
    if [[ $failed_tests -eq 0 ]]; then
        log_success "All tests passed! ✅"
        
        # Open reports if requested
        if [[ "${OPEN_REPORTS:-}" == "true" ]]; then
            open_reports
        fi
        
        cleanup
        exit 0
    else
        log_error "$failed_tests test suite(s) failed ❌"
        
        # Open reports on failure too
        if [[ "${OPEN_REPORTS:-}" == "true" ]]; then
            open_reports
        fi
        
        cleanup
        exit 1
    fi
}

# Handle script interruption
trap cleanup EXIT

# Run main function
main "$@"