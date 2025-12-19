#!/usr/bin/env python
"""
Comprehensive test runner for the Django project.
Runs all test categories and generates detailed reports.
"""
import os
import sys
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description, cwd=None):
    """Run a command and return result."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or Path(__file__).parent,
            capture_output=True,
            text=True,
            check=False
        )
        
        print(f"Exit code: {result.returncode}")
        if result.stdout:
            print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
        
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        print(f"Error running command: {e}")
        return False, "", str(e)


def main():
    parser = argparse.ArgumentParser(description="Run comprehensive test suite")
    parser.add_argument(
        '--coverage',
        action='store_true',
        help='Generate coverage report'
    )
    parser.add_argument(
        '--performance',
        action='store_true',
        help='Run performance tests'
    )
    parser.add_argument(
        '--security',
        action='store_true',
        help='Run security tests'
    )
    parser.add_argument(
        '--integration',
        action='store_true',
        help='Run integration tests'
    )
    parser.add_argument(
        '--unit',
        action='store_true',
        help='Run unit tests'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Run all tests (default)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--failfast',
        action='store_true',
        help='Stop on first failure'
    )
    
    args = parser.parse_args()
    
    # Default to all tests if no specific type selected
    if not any([args.coverage, args.performance, args.security, 
                  args.integration, args.unit, args.all]):
        args.all = True
    
    project_root = Path(__file__).parent
    
    # Build base pytest command
    pytest_cmd = ['python', '-m', 'pytest']
    
    if args.verbose:
        pytest_cmd.append('-v')
    
    if args.failfast:
        pytest_cmd.append('-x')
    
    # Coverage options
    if args.coverage or args.all:
        pytest_cmd.extend([
            '--cov=.',
            '--cov-report=html',
            '--cov-report=term-missing',
            '--cov-report=xml',
            '--cov-fail-under=80'
        ])
    
    success = True
    results = {}
    
    # Run unit tests
    if args.unit or args.all:
        success, stdout, stderr = run_command(
            pytest_cmd + ['-m', 'unit'],
            "Unit Tests"
        )
        results['unit'] = success
        if not success:
            success = False
    
    # Run integration tests
    if args.integration or args.all:
        success, stdout, stderr = run_command(
            pytest_cmd + ['-m', 'integration'],
            "Integration Tests"
        )
        results['integration'] = success
        if not success:
            success = False
    
    # Run performance tests
    if args.performance or args.all:
        success, stdout, stderr = run_command(
            pytest_cmd + ['-m', 'performance'],
            "Performance Tests"
        )
        results['performance'] = success
        if not success:
            success = False
    
    # Run security tests
    if args.security or args.all:
        success, stdout, stderr = run_command(
            pytest_cmd + ['-m', 'security'],
            "Security Tests"
        )
        results['security'] = success
        if not success:
            success = False
    
    # Generate summary report
    print(f"\n{'='*60}")
    print("TEST EXECUTION SUMMARY")
    print(f"{'='*60}")
    
    for test_type, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_type.title():15} {status}")
    
    print(f"\nOverall: {'✓ SUCCESS' if success else '✗ FAILURE'}")
    
    # Coverage report location
    if args.coverage or args.all:
        print(f"\nCoverage reports generated:")
        print(f"  HTML: {project_root}/htmlcov/index.html")
        print(f"  XML:  {project_root}/coverage.xml")
        print(f"  Terminal: See above output")
    
    # Performance report location
    if args.performance or args.all:
        print(f"\nPerformance benchmarks:")
        print(f"  Check individual test outputs above")
    
    # Security report location
    if args.security or args.all:
        print(f"\nSecurity analysis:")
        print(f"  Check individual test outputs above")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
