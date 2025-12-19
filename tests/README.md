# Comprehensive Testing Suite

This directory contains the complete testing suite for the Django project management application.

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_integration.py        # Cross-app workflow tests
├── test_performance.py        # Performance and load tests
├── test_security.py          # Security vulnerability tests
└── app-specific tests/       # Individual app test directories
    ├── accounts/
    ├── projects/
    ├── tasks/
    ├── comments/
    ├── notifications/
    ├── teams/
    ├── files/
    └── activity/
```

## Test Categories

### 1. Unit Tests
- **Model Tests**: Test model methods, validators, and constraints
- **API Tests**: Test endpoints, permissions, and serialization
- **Business Logic Tests**: Test domain-specific logic

### 2. Integration Tests
- **User Journeys**: Complete workflows from registration to project management
- **Cross-App Workflows**: Tests spanning multiple applications
- **Data Flow Tests**: End-to-end data flow validation

### 3. Performance Tests
- **API Response Times**: Ensure endpoints respond within acceptable time limits
- **Database Query Optimization**: Test query efficiency with large datasets
- **Concurrent Load Testing**: Test system behavior under concurrent load
- **Memory Usage**: Monitor memory consumption during operations

### 4. Security Tests
- **Authentication Security**: SQL injection, XSS, CSRF protection
- **Authorization Security**: Role-based access control, horizontal privilege escalation
- **Input Validation**: Malicious input handling, file upload security
- **Data Exposure**: Sensitive data leakage prevention

## Running Tests

### Basic Test Execution

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test categories
pytest -m unit              # Unit tests only
pytest -m integration         # Integration tests only
pytest -m performance        # Performance tests only
pytest -m security           # Security tests only
```

### Advanced Test Execution

```bash
# Run with verbose output
pytest -v

# Run with specific markers
pytest -m "not slow"        # Skip slow tests
pytest -m "unit or integration"  # Run multiple categories

# Run performance tests with benchmarking
python tests/test_performance.py

# Run security tests
python tests/test_security.py
```

### Coverage Analysis

```bash
# Generate coverage report
pytest --cov=. --cov-report=html

# Check coverage thresholds
pytest --cov=. --cov-fail-under=80

# Generate XML report for CI
pytest --cov=. --cov-report=xml
```

## Test Configuration

### Pytest Configuration (pytest.ini)
- **Test Discovery**: Automatically finds test files and modules
- **Markers**: Predefined markers for test categorization
- **Coverage**: Integrated coverage reporting
- **Parallel Execution**: Multi-process test execution

### Test Settings (settings_test.py)
- **Database**: In-memory SQLite for fast tests
- **Email**: Local memory backend
- **Caching**: Disabled cache backend
- **Celery**: Eager task execution
- **Security**: Test-specific security settings

## Fixtures and Factories

### Shared Fixtures (conftest.py)
- **Authentication Clients**: Pre-configured clients for different user roles
- **Test Data**: Common test objects (users, projects, tasks)
- **URL Helpers**: Common URL patterns for testing

### Factory Classes
- **UserFactory**: Creates users with different roles and attributes
- **ProjectFactory**: Creates projects with various configurations
- **TaskFactory**: Creates tasks with different statuses and priorities
- **CommentFactory**: Creates threaded comments with reactions
- **NotificationFactory**: Creates notifications with different types

## Performance Benchmarks

### Response Time Expectations
- **Simple GET**: < 200ms
- **Complex GET**: < 500ms
- **POST/PUT**: < 300ms
- **DELETE**: < 100ms

### Database Query Expectations
- **List Views**: < 10 queries per page
- **Detail Views**: < 20 queries total
- **Filtered Views**: < 30 queries with filters
- **Statistics Views**: < 50 queries with aggregations

### Memory Usage Expectations
- **Base Memory**: < 50MB per test process
- **Memory Growth**: < 100MB during large operations
- **Pagination**: < 50% of full dataset memory usage

## Security Test Coverage

### Authentication Security
- **SQL Injection**: All input fields tested
- **XSS Prevention**: HTML/script injection attempts
- **Password Security**: Strength requirements and hashing
- **Rate Limiting**: Brute force prevention
- **Session Security**: Fixation and hijacking prevention

### Authorization Security
- **Role-Based Access**: Proper permission enforcement
- **Horizontal Access**: Users can't access others' resources
- **Vertical Access**: Privilege escalation prevention
- **Parameter Pollution**: Extra parameter handling

### Input Validation
- **File Uploads**: Type, size, and content validation
- **Data Sanitization**: HTML/XML/JSON sanitization
- **Length Limits**: Input length restrictions
- **Format Validation**: Proper format enforcement

## CI/CD Integration

### GitHub Actions Example
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.11
    - name: Install dependencies
      run: |
        pip install -r requirements-dev.txt
    - name: Run tests
      run: |
        pytest --cov=. --cov-report=xml
    - name: Upload coverage
      uses: codecov/codecov-action@v1
```

### Coverage Requirements
- **Minimum Coverage**: 80% line coverage
- **Critical Paths**: 95% coverage on core business logic
- **New Code**: 90% coverage on new features
- **Security Tests**: 100% coverage on security-critical paths

## Test Data Management

### Test Database
- **Isolation**: Each test runs in a clean database state
- **Transactions**: Tests run within database transactions
- **Rollback**: Automatic rollback after each test
- **Fixtures**: Consistent test data creation

### External Services
- **Email**: Mocked or using memory backend
- **File Storage**: Using local storage for tests
- **Cache**: Disabled or using dummy cache
- **External APIs**: Mocked using unittest.mock

## Best Practices

### Test Writing
1. **Descriptive Names**: Clear, descriptive test method names
2. **Single Assertion**: One assertion per test when possible
3. **Test Documentation**: Docstrings explaining test purpose
4. **Setup/Teardown**: Proper fixture usage
5. **Edge Cases**: Test boundary conditions

### Test Organization
1. **Group by Feature**: Related tests grouped together
2. **Use Markers**: Proper test categorization
3. **Parameterized Tests**: Use pytest.mark.parametrize for variations
4. **Custom Assertions**: Create helper methods for common assertions
5. **Test Data**: Use factories for consistent test data

### Performance Considerations
1. **Database Efficiency**: Minimize queries, use select_related/prefetch_related
2. **Pagination**: Test with various page sizes
3. **Caching**: Test cache hit/miss scenarios
4. **Bulk Operations**: Test bulk create/update/delete operations
5. **Memory Management**: Clean up resources in tests

## Troubleshooting

### Common Issues

#### Factory Import Errors
```bash
# If factories can't be imported, ensure:
# 1. Factory-boy is installed
pip install factory-boy

# 2. APPS includes test directory
# Check settings.py for apps configuration
```

#### Database Connection Issues
```bash
# If tests can't connect to database:
# 1. Check test database settings
# 2. Ensure migrations are applied
python manage.py migrate --settings=config.settings_test

# 3. Check database permissions
```

#### Coverage Issues
```bash
# If coverage is incomplete:
# 1. Check coverage configuration
cat .coveragerc

# 2. Generate detailed report
pytest --cov=. --cov-report=term-missing

# 3. Check for missing tests
coverage report --missing-lines
```

### Debugging Tests

#### Individual Test Debugging
```bash
# Run single test with debugging
pytest -v -s tests/test_integration.py::TestUserJourney::test_new_user_onboarding

# Run with pdb debugging
pytest --pdb tests/test_integration.py::TestUserJourney::test_new_user_onboarding
```

#### Database Debugging
```bash
# Show SQL queries in tests
pytest --ds=settings.settings_test --debug-mode

# Print executed queries
pytest --ds=settings.settings_test --print-sql
```

## Continuous Improvement

### Test Metrics
- **Test Count**: Track total number of tests
- **Coverage Trend**: Monitor coverage over time
- **Performance Trend**: Track test execution time
- **Flaky Tests**: Identify and fix unreliable tests

### Regular Tasks
1. **Weekly**: Review test coverage and add missing tests
2. **Bi-weekly**: Update performance benchmarks
3. **Monthly**: Review and update security test cases
4. **Quarterly**: Review and update test infrastructure

### Test Maintenance
1. **Factory Updates**: Keep factories in sync with models
2. **Fixture Updates**: Update fixtures for new features
3. **Configuration Updates**: Review and update test settings
4. **Documentation Updates**: Keep test documentation current

## Contributing

### Adding New Tests
1. **Follow Patterns**: Use existing test patterns as examples
2. **Add Factories**: Create factory classes for new models
3. **Update Fixtures**: Add new fixtures to conftest.py
4. **Add Coverage**: Ensure new code is covered
5. **Update Docs**: Document new test cases

### Code Review Checklist
- [ ] Tests added for new features
- [ ] Factories created for new models
- [ ] Security considerations addressed
- [ ] Performance impact considered
- [ ] Documentation updated
- [ ] Coverage thresholds met

## Resources

### Documentation
- [Pytest Documentation](https://docs.pytest.org/)
- [Factory Boy Documentation](https://factoryboy.readthedocs.io/)
- [Django Testing Documentation](https://docs.djangoproject.com/en/stable/topics/testing/)

### Tools
- **pytest**: Test runner and framework
- **coverage.py**: Coverage measurement
- **factory-boy**: Test data generation
- **mock**: Test mocking and patching

### Extensions
- **pytest-django**: Django integration for pytest
- **pytest-cov**: Coverage reporting
- **pytest-xdist**: Parallel test execution
- **pytest-mock**: Enhanced mocking capabilities

This comprehensive testing suite ensures the application is reliable, secure, performant, and maintainable. Regular execution of these tests helps catch issues early and maintain code quality throughout the development lifecycle.
