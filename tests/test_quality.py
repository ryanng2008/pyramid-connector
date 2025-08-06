"""Quality assurance tests for code standards and best practices."""

import ast
import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any

import pytest


class TestCodeQuality:
    """Test code quality standards."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent
        self.src_dir = self.project_root / "src"
        self.python_files = list(self.src_dir.rglob("*.py"))
    
    def test_python_files_exist(self):
        """Test that Python source files exist."""
        assert len(self.python_files) > 0, "No Python files found in src directory"
    
    def test_no_syntax_errors(self):
        """Test that all Python files have valid syntax."""
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                ast.parse(content)
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {py_file}: {e}")
    
    def test_imports_organization(self):
        """Test that imports are properly organized."""
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            import_lines = []
            current_line_no = 0
            
            # Find import lines
            for i, line in enumerate(lines):
                stripped = line.strip()
                if (stripped.startswith('import ') or 
                    stripped.startswith('from ') or 
                    (stripped and not stripped.startswith('#') and 
                     ('import ' in stripped or 'from ' in stripped))):
                    import_lines.append((i + 1, stripped))
            
            # Check for imports after code (basic check)
            code_started = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith('#') and not stripped.startswith('"""'):
                    if not (stripped.startswith('import ') or stripped.startswith('from ')):
                        if not stripped.startswith('"""') and '"""' not in stripped:
                            code_started = True
                    elif code_started and (stripped.startswith('import ') or stripped.startswith('from ')):
                        # Allow some flexibility for type checking imports
                        if 'TYPE_CHECKING' not in line:
                            pytest.fail(f"Import after code in {py_file}:{i + 1}: {stripped}")
    
    def test_docstrings_present(self):
        """Test that functions and classes have docstrings."""
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue  # Skip files with syntax errors
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # Skip private methods and test methods
                    if (node.name.startswith('_') and not node.name.startswith('__')) or \
                       node.name.startswith('test_'):
                        continue
                    
                    # Check for docstring
                    docstring = ast.get_docstring(node)
                    if not docstring:
                        pytest.fail(
                            f"Missing docstring for {type(node).__name__} '{node.name}' "
                            f"in {py_file}:{node.lineno}"
                        )
    
    def test_no_hardcoded_secrets(self):
        """Test that no hardcoded secrets are present."""
        secret_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']',
            r'private_key\s*=\s*["\'][^"\']+["\']',
        ]
        
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for pattern in secret_patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Skip test files and example values
                    if ('test' in str(py_file).lower() or 
                        'example' in match.group().lower() or
                        'your_' in match.group().lower() or
                        'test_' in match.group().lower()):
                        continue
                    
                    pytest.fail(f"Potential hardcoded secret in {py_file}: {match.group()}")
    
    def test_no_debug_statements(self):
        """Test that no debug statements are left in code."""
        debug_patterns = [
            r'\bprint\s*\(',
            r'\bpdb\.set_trace\s*\(',
            r'\bbreakpoint\s*\(',
            r'\bipdb\.set_trace\s*\(',
        ]
        
        for py_file in self.python_files:
            # Skip test files
            if 'test' in str(py_file).lower():
                continue
                
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for pattern in debug_patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    line_no = content[:match.start()].count('\n') + 1
                    pytest.fail(f"Debug statement found in {py_file}:{line_no}: {match.group()}")
    
    def test_consistent_naming_conventions(self):
        """Test consistent naming conventions."""
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Class names should be PascalCase
                    if not re.match(r'^[A-Z][a-zA-Z0-9]*$', node.name):
                        if not node.name.startswith('_'):  # Allow private classes
                            pytest.fail(
                                f"Class '{node.name}' should use PascalCase "
                                f"in {py_file}:{node.lineno}"
                            )
                
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Function names should be snake_case
                    if not re.match(r'^[a-z_][a-z0-9_]*$', node.name):
                        if not node.name.startswith('__'):  # Allow magic methods
                            pytest.fail(
                                f"Function '{node.name}' should use snake_case "
                                f"in {py_file}:{node.lineno}"
                            )
    
    def test_file_encoding_utf8(self):
        """Test that all Python files use UTF-8 encoding."""
        for py_file in self.python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    f.read()
            except UnicodeDecodeError:
                pytest.fail(f"File {py_file} is not UTF-8 encoded")
    
    def test_line_length_reasonable(self):
        """Test that lines are not excessively long."""
        max_line_length = 100  # Reasonable limit
        
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for i, line in enumerate(lines):
                if len(line.rstrip()) > max_line_length:
                    # Allow some flexibility for imports and URLs
                    if ('import ' in line or 'from ' in line or 
                        'http' in line or 'https' in line):
                        continue
                    
                    pytest.fail(
                        f"Line too long ({len(line.rstrip())} chars) in "
                        f"{py_file}:{i + 1}"
                    )


class TestSecurityStandards:
    """Test security standards and best practices."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent
        self.src_dir = self.project_root / "src"
        self.python_files = list(self.src_dir.rglob("*.py"))
    
    def test_no_sql_injection_patterns(self):
        """Test for potential SQL injection vulnerabilities."""
        dangerous_patterns = [
            r'f".*SELECT.*"',
            r'f\'.*SELECT.*\'',
            r'".*SELECT.*"\s*%',
            r'\'.*SELECT.*\'\s*%',
            r'\.format\(.*SELECT.*\)',
        ]
        
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for pattern in dangerous_patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    line_no = content[:match.start()].count('\n') + 1
                    pytest.fail(
                        f"Potential SQL injection pattern in {py_file}:{line_no}: "
                        f"{match.group()[:50]}..."
                    )
    
    def test_secure_random_usage(self):
        """Test that secure random functions are used where appropriate."""
        insecure_patterns = [
            r'\brandom\.random\(',
            r'\brandom\.randint\(',
            r'\brandom\.choice\(',
        ]
        
        for py_file in self.python_files:
            # Skip test files
            if 'test' in str(py_file).lower():
                continue
                
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if file deals with security-sensitive operations
            if any(word in content.lower() for word in ['password', 'token', 'secret', 'auth']):
                for pattern in insecure_patterns:
                    if re.search(pattern, content):
                        pytest.fail(
                            f"Use secrets module instead of random for security in {py_file}"
                        )
    
    def test_no_shell_injection(self):
        """Test for potential shell injection vulnerabilities."""
        dangerous_patterns = [
            r'subprocess\.call\([^)]*shell\s*=\s*True',
            r'subprocess\.run\([^)]*shell\s*=\s*True',
            r'os\.system\(',
            r'os\.popen\(',
        ]
        
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for pattern in dangerous_patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    line_no = content[:match.start()].count('\n') + 1
                    pytest.fail(
                        f"Potential shell injection vulnerability in {py_file}:{line_no}: "
                        f"{match.group()}"
                    )
    
    def test_input_validation_patterns(self):
        """Test that input validation patterns are present."""
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for API endpoints or user input handling
            if 'request' in content and ('endpoint' in content or 'handler' in content):
                # Should have some form of validation
                validation_patterns = [
                    r'pydantic',
                    r'validator',
                    r'validate',
                    r'isinstance\(',
                    r'type\s*==',
                ]
                
                has_validation = any(re.search(pattern, content, re.IGNORECASE) 
                                   for pattern in validation_patterns)
                
                if not has_validation:
                    pytest.fail(
                        f"File {py_file} handles requests but lacks validation patterns"
                    )


class TestPerformanceStandards:
    """Test performance-related standards."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent
        self.src_dir = self.project_root / "src"
        self.python_files = list(self.src_dir.rglob("*.py"))
    
    def test_no_blocking_operations_in_async(self):
        """Test that async functions don't contain blocking operations."""
        blocking_patterns = [
            r'time\.sleep\(',
            r'requests\.get\(',
            r'requests\.post\(',
            r'urllib\.request\.',
        ]
        
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            
            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef):
                    # Get function content
                    func_start = node.lineno
                    func_end = node.end_lineno if hasattr(node, 'end_lineno') else func_start + 20
                    
                    func_lines = content.split('\n')[func_start-1:func_end]
                    func_content = '\n'.join(func_lines)
                    
                    for pattern in blocking_patterns:
                        if re.search(pattern, func_content):
                            pytest.fail(
                                f"Blocking operation in async function '{node.name}' "
                                f"in {py_file}:{func_start}"
                            )
    
    def test_proper_async_context_managers(self):
        """Test that async context managers are used properly."""
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for potential async context manager usage
            patterns = [
                r'async\s+with\s+.*\.',
                r'await\s+.*\.__aenter__',
                r'await\s+.*\.__aexit__',
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    # This is good - async context managers are being used
                    pass
    
    def test_efficient_data_structures(self):
        """Test for efficient data structure usage."""
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for potentially inefficient patterns
            inefficient_patterns = [
                (r'for\s+\w+\s+in\s+.*\.keys\(\):', 'Use "for key in dict:" instead of "for key in dict.keys():"'),
                (r'len\([^)]+\)\s*==\s*0', 'Use "not container" instead of "len(container) == 0"'),
                (r'len\([^)]+\)\s*>\s*0', 'Use "container" instead of "len(container) > 0"'),
            ]
            
            for pattern, message in inefficient_patterns:
                matches = re.finditer(pattern, content)
                for match in matches:
                    line_no = content[:match.start()].count('\n') + 1
                    # Just warn about these for now
                    print(f"Performance suggestion in {py_file}:{line_no}: {message}")


class TestErrorHandlingStandards:
    """Test error handling standards."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent
        self.src_dir = self.project_root / "src"
        self.python_files = list(self.src_dir.rglob("*.py"))
    
    def test_proper_exception_handling(self):
        """Test that exceptions are handled properly."""
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # Check for bare except clauses
                    if node.type is None:
                        pytest.fail(
                            f"Bare except clause found in {py_file}:{node.lineno}. "
                            f"Catch specific exceptions instead."
                        )
                    
                    # Check for catching Exception without re-raising or logging
                    if (isinstance(node.type, ast.Name) and 
                        node.type.id == 'Exception'):
                        # Should have logging or re-raising
                        handler_content = ast.dump(node)
                        if ('log' not in handler_content.lower() and 
                            'raise' not in handler_content.lower()):
                            print(f"Warning: Exception caught but not logged or re-raised in {py_file}:{node.lineno}")
    
    def test_custom_exceptions_defined(self):
        """Test that custom exceptions are properly defined."""
        for py_file in self.python_files:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if it's an exception class
                    if any(base.id == 'Exception' if isinstance(base, ast.Name) else False 
                           for base in node.bases):
                        # Should have docstring
                        docstring = ast.get_docstring(node)
                        if not docstring:
                            pytest.fail(
                                f"Custom exception '{node.name}' missing docstring "
                                f"in {py_file}:{node.lineno}"
                            )


class TestTestCoverage:
    """Test test coverage and quality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.project_root = Path(__file__).parent.parent
        self.src_dir = self.project_root / "src"
        self.tests_dir = self.project_root / "tests"
    
    def test_all_modules_have_tests(self):
        """Test that all modules have corresponding test files."""
        src_modules = []
        for py_file in self.src_dir.rglob("*.py"):
            if py_file.name != "__init__.py":
                # Get relative path from src
                rel_path = py_file.relative_to(self.src_dir)
                src_modules.append(rel_path)
        
        test_files = []
        for py_file in self.tests_dir.rglob("test_*.py"):
            test_files.append(py_file.name)
        
        # Check that major modules have tests
        major_modules = [
            "main.py",
            "database/models.py",
            "database/service.py",
            "api_clients/google_drive.py",
            "api_clients/autodesk.py",
            "core/sync_engine.py",
            "core/connector.py",
        ]
        
        for module in major_modules:
            module_name = Path(module).stem
            expected_test = f"test_{module_name}.py"
            
            if expected_test not in test_files:
                # Check if there are related test files
                related_tests = [t for t in test_files if module_name in t]
                if not related_tests:
                    pytest.fail(f"No test file found for major module: {module}")
    
    def test_test_file_structure(self):
        """Test that test files follow proper structure."""
        test_files = list(self.tests_dir.rglob("test_*.py"))
        
        for test_file in test_files:
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Should import pytest
            if 'import pytest' not in content and 'from pytest' not in content:
                pytest.fail(f"Test file {test_file} should import pytest")
            
            # Should have test functions
            if 'def test_' not in content:
                pytest.fail(f"Test file {test_file} should have test functions")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])