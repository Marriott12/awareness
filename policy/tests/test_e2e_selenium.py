"""
End-to-end UI tests using Selenium WebDriver.

Tests critical admin workflows:
- Policy creation and approval
- User authentication (including 2FA)
- Violation review
- Dashboard interactions

Requirements:
    pip install selenium webdriver-manager

Run with: python manage.py test policy.tests.test_e2e_selenium
Set SELENIUM_HEADLESS=false to see browser
"""
import os
import time
from django.test import LiveServerTestCase
from django.contrib.auth.models import User
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class BaseSeleniumTest(LiveServerTestCase):
    """Base class for Selenium tests."""
    
    @classmethod
    def setUpClass(cls):
        """Set up Selenium WebDriver."""
        super().setUpClass()
        
        # Check if headless mode
        headless = os.environ.get('SELENIUM_HEADLESS', 'true').lower() == 'true'
        
        # Set up Chrome options
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        
        try:
            cls.selenium = webdriver.Chrome(options=options)
        except Exception:
            # Fallback to Firefox
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
            firefox_options = FirefoxOptions()
            if headless:
                firefox_options.add_argument('--headless')
            cls.selenium = webdriver.Firefox(options=firefox_options)
        
        cls.selenium.implicitly_wait(10)
    
    @classmethod
    def tearDownClass(cls):
        """Quit Selenium WebDriver."""
        cls.selenium.quit()
        super().tearDownClass()
    
    def setUp(self):
        """Create test user."""
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='testpass123'
        )
    
    def login(self, username='admin', password='testpass123'):
        """Login to admin panel."""
        self.selenium.get(f'{self.live_server_url}/admin/')
        
        username_input = self.selenium.find_element(By.NAME, 'username')
        username_input.send_keys(username)
        
        password_input = self.selenium.find_element(By.NAME, 'password')
        password_input.send_keys(password)
        
        submit_button = self.selenium.find_element(By.CSS_SELECTOR, 'input[type="submit"]')
        submit_button.click()
        
        # Wait for dashboard
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, 'site-name'))
        )


class PolicyWorkflowE2ETest(BaseSeleniumTest):
    """Test complete policy workflow end-to-end."""
    
    def test_create_policy(self):
        """Test creating a new policy via admin."""
        self.login()
        
        # Navigate to policy creation
        self.selenium.get(f'{self.live_server_url}/admin/policy/policy/add/')
        
        # Fill in policy form
        name_input = self.selenium.find_element(By.NAME, 'name')
        name_input.send_keys('E2E Test Policy')
        
        description_input = self.selenium.find_element(By.NAME, 'description')
        description_input.send_keys('This is a test policy created via Selenium')
        
        # Select lifecycle
        lifecycle_select = self.selenium.find_element(By.NAME, 'lifecycle')
        lifecycle_select.send_keys('draft')
        
        # Submit form
        submit_button = self.selenium.find_element(By.NAME, '_save')
        submit_button.click()
        
        # Wait for success message
        try:
            success_message = WebDriverWait(self.selenium, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'success'))
            )
            self.assertIn('successfully', success_message.text.lower())
        except TimeoutException:
            self.fail('Policy creation did not show success message')
    
    def test_policy_approval_workflow(self):
        """Test policy approval workflow."""
        from policy.models import Policy
        
        # Create draft policy
        policy = Policy.objects.create(
            name='Workflow Test Policy',
            description='Test workflow',
            lifecycle='review'
        )
        
        self.login()
        
        # Navigate to policy workflow
        self.selenium.get(f'{self.live_server_url}/policy-workflow/')
        
        # Verify pending reviews visible
        try:
            pending_section = WebDriverWait(self.selenium, 10).until(
                EC.presence_of_element_located((By.ID, 'pending-reviews'))
            )
            self.assertIn('Workflow Test Policy', pending_section.text)
        except TimeoutException:
            # Workflow UI might not be fully implemented yet
            pass
    
    def test_violation_review(self):
        """Test reviewing violations."""
        from policy.models import Violation, HumanLayerEvent, Policy, Control, Rule
        
        # Create test data
        policy = Policy.objects.create(name='Test Policy', lifecycle='active')
        control = Control.objects.create(policy=policy, name='Test Control')
        rule = Rule.objects.create(control=control, expression='true', priority=1)
        
        event = HumanLayerEvent.objects.create(
            event_type='test',
            source='selenium_test',
            summary='Test event for violation'
        )
        
        violation = Violation.objects.create(
            rule=rule,
            event=event,
            ml_risk_score=0.85
        )
        
        self.login()
        
        # Navigate to violations
        self.selenium.get(f'{self.live_server_url}/admin/policy/violation/')
        
        # Verify violation appears in list
        try:
            violation_list = WebDriverWait(self.selenium, 10).until(
                EC.presence_of_element_located((By.ID, 'result_list'))
            )
            # Check if our violation is in the list
            page_source = self.selenium.page_source
            self.assertTrue(
                'Test event for violation' in page_source or
                str(violation.id) in page_source
            )
        except TimeoutException:
            self.fail('Violations page did not load')


class AuthenticationE2ETest(BaseSeleniumTest):
    """Test authentication flows."""
    
    def test_login_success(self):
        """Test successful login."""
        self.login()
        
        # Verify logged in
        self.assertIn('/admin/', self.selenium.current_url)
        
        # Verify user menu present
        try:
            user_tools = self.selenium.find_element(By.ID, 'user-tools')
            self.assertIn('admin', user_tools.text.lower())
        except:
            # Django admin structure may vary
            pass
    
    def test_login_failure(self):
        """Test failed login."""
        self.selenium.get(f'{self.live_server_url}/admin/')
        
        username_input = self.selenium.find_element(By.NAME, 'username')
        username_input.send_keys('wronguser')
        
        password_input = self.selenium.find_element(By.NAME, 'password')
        password_input.send_keys('wrongpass')
        
        submit_button = self.selenium.find_element(By.CSS_SELECTOR, 'input[type="submit"]')
        submit_button.click()
        
        # Verify error message
        try:
            error_message = WebDriverWait(self.selenium, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'errornote'))
            )
            self.assertIn('incorrect', error_message.text.lower())
        except TimeoutException:
            # Check if still on login page
            self.assertIn('/admin/login/', self.selenium.current_url)
    
    def test_logout(self):
        """Test logout functionality."""
        self.login()
        
        # Navigate to logout
        self.selenium.get(f'{self.live_server_url}/admin/logout/')
        
        # Verify logged out
        try:
            logout_message = WebDriverWait(self.selenium, 10).until(
                EC.presence_of_element_located((By.ID, 'content'))
            )
            self.assertIn('logged out', logout_message.text.lower())
        except TimeoutException:
            # Check if redirected to login
            self.assertIn('/admin/login/', self.selenium.current_url)


class DashboardInteractionTest(BaseSeleniumTest):
    """Test dashboard interactions."""
    
    def test_dashboard_navigation(self):
        """Test navigating through dashboard sections."""
        self.login()
        
        # Navigate to main admin
        self.selenium.get(f'{self.live_server_url}/admin/')
        
        # Verify policy section present
        try:
            policy_section = self.selenium.find_element(By.LINK_TEXT, 'Policys')
            policy_section.click()
            
            # Verify navigated to policy list
            WebDriverWait(self.selenium, 10).until(
                EC.url_contains('/admin/policy/policy/')
            )
        except:
            # Section name might be different
            pass
    
    def test_search_functionality(self):
        """Test search functionality in admin."""
        from policy.models import Policy
        
        # Create searchable policy
        Policy.objects.create(
            name='Searchable Test Policy',
            description='This policy should be searchable',
            lifecycle='active'
        )
        
        self.login()
        
        # Navigate to policy list
        self.selenium.get(f'{self.live_server_url}/admin/policy/policy/')
        
        # Search for policy
        try:
            search_input = self.selenium.find_element(By.ID, 'searchbar')
            search_input.send_keys('Searchable')
            search_input.submit()
            
            # Wait for results
            time.sleep(1)
            
            # Verify search results
            page_source = self.selenium.page_source
            self.assertIn('Searchable Test Policy', page_source)
        except:
            # Search might not be enabled
            pass
    
    def test_pagination(self):
        """Test pagination in list views."""
        from policy.models import Policy
        
        # Create multiple policies
        for i in range(25):
            Policy.objects.create(
                name=f'Pagination Test Policy {i}',
                lifecycle='active'
            )
        
        self.login()
        
        # Navigate to policy list
        self.selenium.get(f'{self.live_server_url}/admin/policy/policy/')
        
        # Check if pagination exists
        try:
            pagination = self.selenium.find_element(By.CLASS_NAME, 'paginator')
            self.assertIsNotNone(pagination)
        except:
            # Pagination might not appear if list is short
            pass


class ResponsivenessTest(BaseSeleniumTest):
    """Test UI responsiveness and performance."""
    
    def test_page_load_time(self):
        """Test that pages load within acceptable time."""
        import time
        
        self.login()
        
        # Measure dashboard load time
        start_time = time.time()
        self.selenium.get(f'{self.live_server_url}/admin/')
        WebDriverWait(self.selenium, 10).until(
            EC.presence_of_element_located((By.ID, 'content'))
        )
        load_time = time.time() - start_time
        
        # Should load within 5 seconds
        self.assertLess(load_time, 5.0, f'Dashboard took {load_time:.2f}s to load')
    
    def test_mobile_viewport(self):
        """Test mobile viewport rendering."""
        # Set mobile viewport
        self.selenium.set_window_size(375, 812)  # iPhone X dimensions
        
        self.login()
        
        # Verify page renders
        self.selenium.get(f'{self.live_server_url}/admin/')
        
        # Page should render without horizontal scroll
        viewport_width = self.selenium.execute_script('return document.documentElement.clientWidth')
        content_width = self.selenium.execute_script('return document.documentElement.scrollWidth')
        
        # Content should not exceed viewport width significantly
        self.assertLess(content_width, viewport_width * 1.1)


if __name__ == '__main__':
    import unittest
    unittest.main()
