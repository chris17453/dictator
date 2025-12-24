"""
Tests for SSL security - ensure SSL verification is enabled
Following TDD - RED phase
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Mock problematic modules before import
sys.modules['sounddevice'] = MagicMock()
sys.modules['faster_whisper'] = MagicMock()
sys.modules['pynput'] = MagicMock()
sys.modules['pynput.keyboard'] = MagicMock()


class TestSSLSecurity:
    """Test that SSL verification is properly enabled"""

    def test_no_ssl_bypass_in_recorder(self):
        """
        CRITICAL: recorder.py must not disable SSL certificate verification.
        ssl._create_unverified_context is a security vulnerability.
        """
        from src import recorder
        import inspect

        # Get source code
        source = inspect.getsource(recorder.PureRecorder.load_whisper_model)

        # Should NOT contain SSL bypass
        assert 'ssl._create_unverified_context' not in source, (
            "recorder.py must not use ssl._create_unverified_context - "
            "this disables certificate verification and allows man-in-the-middle attacks"
        )

        assert 'ssl._create_default_https_context' not in source or (
            'ssl._create_default_https_context' in source and
            'ssl._create_unverified_context' not in source
        ), (
            "recorder.py must not override ssl._create_default_https_context with unverified context"
        )

    def test_ssl_module_not_modified(self):
        """
        Test that the ssl module's defaults are not modified globally.
        Modifying ssl defaults affects all HTTPS connections in the application.
        """
        import ssl

        # Get the default context creation function
        default_context_func = ssl._create_default_https_context

        # Should be the secure version
        # The function name should contain 'default' and not 'unverified'
        func_name = default_context_func.__name__
        assert 'unverified' not in func_name.lower(), (
            "SSL default context has been modified to unverified! "
            "This is a critical security vulnerability."
        )

    def test_recorder_uses_secure_ssl(self):
        """
        Test that recorder.py uses secure SSL by default.
        Any SSL configuration should maintain certificate verification.
        """
        from src import recorder
        import inspect

        # Check entire module source
        module_source = inspect.getsource(recorder)

        # Count occurrences of SSL bypass
        bypass_count = module_source.count('_create_unverified_context')

        assert bypass_count == 0, (
            f"Found {bypass_count} instance(s) of SSL bypass in recorder.py. "
            "All instances must be removed for security."
        )

    def test_whisper_model_loading_secure(self):
        """
        Test that Whisper model loading doesn't bypass SSL.
        If SSL issues occur, they should be handled with proper error messages,
        not by disabling security.
        """
        from src import recorder
        import inspect

        source = inspect.getsource(recorder.PureRecorder.load_whisper_model)

        # Should not have SSL bypass
        assert 'ssl' not in source.lower() or (
            'ssl' in source.lower() and '_create_unverified_context' not in source
        ), (
            "Whisper model loading must use secure SSL. "
            "If certificate issues occur, document them and use proper certificate bundles."
        )

    def test_network_operations_use_https(self):
        """
        Test that any network operations use HTTPS, not HTTP.
        This is complementary to SSL verification.
        """
        from src import recorder
        import inspect

        module_source = inspect.getsource(recorder)

        # Check for any HTTP URLs (should be HTTPS)
        import re
        http_urls = re.findall(r'http://[^\s\'"]+', module_source)

        # Filter out comments and URLs that are intentionally HTTP
        # (like localhost or documentation)
        insecure_urls = [url for url in http_urls if 'localhost' not in url and 'example' not in url]

        assert len(insecure_urls) == 0, (
            f"Found insecure HTTP URLs: {insecure_urls}. "
            "Use HTTPS for all external connections."
        )


class TestSecureDefaults:
    """Test that security defaults are maintained"""

    def test_ssl_default_verify_mode(self):
        """
        Test that SSL verification mode is CERT_REQUIRED by default.
        """
        import ssl

        # Create a default context
        context = ssl.create_default_context()

        # Verify mode should be CERT_REQUIRED
        assert context.verify_mode == ssl.CERT_REQUIRED, (
            "SSL context must require certificate verification"
        )

    def test_ssl_check_hostname_enabled(self):
        """
        Test that hostname checking is enabled.
        """
        import ssl

        # Create a default context
        context = ssl.create_default_context()

        # Hostname checking should be enabled
        assert context.check_hostname is True, (
            "SSL context must check hostnames"
        )


class TestSecurityBestPractices:
    """Test that security best practices are followed"""

    def test_no_hardcoded_credentials(self):
        """
        Test that there are no hardcoded credentials in recorder.py.
        """
        from src import recorder
        import inspect
        import re

        source = inspect.getsource(recorder)

        # Look for common credential patterns
        patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
        ]

        found_credentials = []
        for pattern in patterns:
            matches = re.findall(pattern, source, re.IGNORECASE)
            if matches:
                # Filter out obvious placeholders
                real_matches = [m for m in matches if 'your_' not in m.lower() and 'example' not in m.lower()]
                found_credentials.extend(real_matches)

        assert len(found_credentials) == 0, (
            f"Possible hardcoded credentials found: {found_credentials}"
        )

    def test_sensitive_data_not_logged(self):
        """
        Test that sensitive data patterns are not logged.
        """
        from src import recorder
        import inspect

        source = inspect.getsource(recorder)

        # Look for logging of potentially sensitive data
        # This is a basic check - real sensitive data would need context
        import re

        # Look for log.info(password=...) or similar
        sensitive_log_patterns = [
            r'log\.(info|debug|warning)\([^)]*password',
            r'log\.(info|debug|warning)\([^)]*token',
            r'log\.(info|debug|warning)\([^)]*api_key',
        ]

        found_issues = []
        for pattern in sensitive_log_patterns:
            if re.search(pattern, source, re.IGNORECASE):
                found_issues.append(pattern)

        assert len(found_issues) == 0, (
            f"Possible sensitive data logging found: {found_issues}"
        )
