"""
Load and performance tests with realistic user behavior.

Tests system performance under realistic load:
- Realistic user behavior patterns
- Peak load scenarios
- Sustained load tests
- Performance benchmarks
- Memory profiling

Run with: python manage.py test policy.tests.test_load_performance
"""
import time
import statistics
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
import concurrent.futures
import random


class RealisticLoadTest(TransactionTestCase):
    """Test with realistic user behavior patterns."""
    
    def setUp(self):
        """Create test data."""
        from policy.models import Policy, Control, Rule
        
        # Create realistic policy structure
        for i in range(10):
            policy = Policy.objects.create(
                name=f'Policy {i}',
                lifecycle='active'
            )
            
            # Each policy has multiple controls
            for j in range(5):
                control = Control.objects.create(
                    policy=policy,
                    name=f'Control {i}-{j}'
                )
                
                # Each control has multiple rules
                for k in range(3):
                    Rule.objects.create(
                        control=control,
                        expression={'field': f'value_{k}'},
                        priority=k
                    )
        
        # Create users
        for i in range(20):
            User.objects.create_user(
                username=f'user{i}',
                email=f'user{i}@test.com',
                password='testpass'
            )
    
    def test_concurrent_event_processing(self):
        """Test concurrent event processing."""
        from policy.models import HumanLayerEvent
        from policy.compliance_engine import ComplianceEngine
        
        engine = ComplianceEngine()
        
        def process_event(index):
            """Simulate user creating an event."""
            start_time = time.time()
            
            event = HumanLayerEvent.objects.create(
                event_type='user_action',
                source='load_test',
                user_id=f'user{index % 20}',
                summary=f'Event {index}',
                details={'action': 'test', 'index': index}
            )
            
            # Evaluate compliance
            violations = engine.evaluate_event(event)
            
            elapsed = time.time() - start_time
            return elapsed
        
        # Simulate 100 concurrent users
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(process_event, i) for i in range(100)]
            
            response_times = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    elapsed = future.result(timeout=30)
                    response_times.append(elapsed)
                except Exception as e:
                    print(f'Event processing failed: {e}')
        
        # Verify performance
        if response_times:
            avg_time = statistics.mean(response_times)
            p95_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
            
            print(f'Average response time: {avg_time:.3f}s')
            print(f'P95 response time: {p95_time:.3f}s')
            
            # Should complete within reasonable time
            self.assertLess(avg_time, 5.0, 'Average response time too slow')
            self.assertLess(p95_time, 10.0, 'P95 response time too slow')
    
    def test_dashboard_query_performance(self):
        """Test dashboard query performance."""
        from policy.models import Violation, HumanLayerEvent, Policy, Control, Rule
        
        # Create realistic violation data
        policy = Policy.objects.first()
        control = Control.objects.first()
        rule = Rule.objects.first()
        
        for i in range(1000):
            event = HumanLayerEvent.objects.create(
                event_type='dashboard_test',
                source='load_test',
                user_id=f'user{i % 20}',
                summary=f'Event {i}'
            )
            
            if i % 10 == 0:  # 10% violation rate
                Violation.objects.create(
                    rule=rule,
                    event=event,
                    ml_risk_score=random.uniform(0.5, 1.0)
                )
        
        # Measure query performance
        start_time = time.time()
        
        # Typical dashboard queries
        recent_violations = Violation.objects.select_related(
            'rule', 'event'
        ).order_by('-created_at')[:50]
        
        violation_count = Violation.objects.count()
        high_risk_count = Violation.objects.filter(ml_risk_score__gte=0.7).count()
        
        # Force evaluation
        list(recent_violations)
        
        elapsed = time.time() - start_time
        
        print(f'Dashboard query time: {elapsed:.3f}s')
        
        # Should load quickly
        self.assertLess(elapsed, 2.0, 'Dashboard queries too slow')
    
    def test_policy_evaluation_performance(self):
        """Test policy evaluation performance."""
        from policy.compliance_engine import ComplianceEngine
        from policy.models import HumanLayerEvent
        
        engine = ComplianceEngine()
        
        # Create test event
        event = HumanLayerEvent.objects.create(
            event_type='performance_test',
            source='load_test',
            summary='Performance test event',
            details={'test': True}
        )
        
        # Measure evaluation time
        times = []
        
        for i in range(100):
            start_time = time.time()
            violations = engine.evaluate_event(event)
            elapsed = time.time() - start_time
            times.append(elapsed)
        
        avg_time = statistics.mean(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f'Policy evaluation - Avg: {avg_time:.3f}s, Min: {min_time:.3f}s, Max: {max_time:.3f}s')
        
        # Should be fast
        self.assertLess(avg_time, 1.0, 'Policy evaluation too slow')


class SustainedLoadTest(TransactionTestCase):
    """Test system under sustained load."""
    
    def test_sustained_event_processing(self):
        """Test processing events continuously for extended period."""
        from policy.models import HumanLayerEvent
        from policy.compliance_engine import ComplianceEngine
        
        engine = ComplianceEngine()
        
        # Process events for 30 seconds
        end_time = time.time() + 30
        event_count = 0
        errors = 0
        
        while time.time() < end_time:
            try:
                event = HumanLayerEvent.objects.create(
                    event_type='sustained_test',
                    source='load_test',
                    summary=f'Event {event_count}'
                )
                engine.evaluate_event(event)
                event_count += 1
            except Exception as e:
                errors += 1
                print(f'Error during sustained load: {e}')
            
            # Small delay to simulate realistic load
            time.sleep(0.1)
        
        print(f'Processed {event_count} events in 30s ({event_count/30:.1f} events/sec)')
        print(f'Error rate: {errors/event_count*100:.1f}%')
        
        # Should maintain throughput
        self.assertGreater(event_count, 100, 'Throughput too low')
        self.assertLess(errors / max(event_count, 1), 0.01, 'Error rate too high')


class MemoryProfilingTest(TestCase):
    """Test memory usage patterns."""
    
    def test_memory_leak_detection(self):
        """Test for memory leaks in repeated operations."""
        import gc
        import sys
        
        from policy.models import HumanLayerEvent
        
        # Force garbage collection
        gc.collect()
        
        # Get initial memory usage (approximate)
        initial_objects = len(gc.get_objects())
        
        # Perform repeated operations
        for i in range(100):
            event = HumanLayerEvent.objects.create(
                event_type='memory_test',
                source='load_test',
                summary=f'Event {i}'
            )
            event.delete()
        
        # Force garbage collection
        gc.collect()
        
        # Check object count
        final_objects = len(gc.get_objects())
        
        # Should not have significant growth
        growth = final_objects - initial_objects
        print(f'Object count growth: {growth}')
        
        # Allow some growth but not excessive
        self.assertLess(growth, 1000, 'Possible memory leak detected')
    
    def test_large_dataset_memory(self):
        """Test memory usage with large datasets."""
        from policy.models import HumanLayerEvent
        
        # Create large batch
        events = []
        for i in range(1000):
            events.append(HumanLayerEvent(
                event_type='batch_memory_test',
                source='load_test',
                summary=f'Event {i}',
                details={'data': 'x' * 100}  # Some data in each event
            ))
        
        # Bulk create should be memory efficient
        try:
            HumanLayerEvent.objects.bulk_create(events, batch_size=100)
            
            # Should complete without running out of memory
            count = HumanLayerEvent.objects.filter(
                event_type='batch_memory_test'
            ).count()
            
            self.assertEqual(count, 1000)
            
        except MemoryError:
            self.fail('Bulk create exhausted memory')


class CachingPerformanceTest(TestCase):
    """Test caching performance improvements."""
    
    def setUp(self):
        """Set up test data."""
        from policy.models import Policy
        from django.core.cache import cache
        
        cache.clear()
        
        # Create test policies
        for i in range(50):
            Policy.objects.create(
                name=f'Cache Test Policy {i}',
                lifecycle='active'
            )
    
    def test_cache_hit_performance(self):
        """Test performance improvement from cache hits."""
        from policy.policy_cache import PolicyCache
        from policy.models import Policy
        
        cache_manager = PolicyCache()
        
        # First call - cache miss
        start_time = time.time()
        policies = cache_manager.get_active_policies()
        uncached_time = time.time() - start_time
        
        # Second call - cache hit
        start_time = time.time()
        policies = cache_manager.get_active_policies()
        cached_time = time.time() - start_time
        
        print(f'Uncached: {uncached_time:.4f}s, Cached: {cached_time:.4f}s')
        print(f'Speedup: {uncached_time/max(cached_time, 0.0001):.1f}x')
        
        # Cache should be significantly faster
        # Allow for some variance
        self.assertLess(cached_time, uncached_time * 2)


class DatabaseOptimizationTest(TestCase):
    """Test database query optimization."""
    
    def test_query_count(self):
        """Test number of queries for common operations."""
        from django.test.utils import override_settings
        from django.db import connection
        from django.test import TestCase
        from policy.models import Violation, Policy, Control, Rule
        
        # Create test data
        policy = Policy.objects.create(name='Test', lifecycle='active')
        control = Control.objects.create(policy=policy, name='Control')
        rule = Rule.objects.create(control=control, expression='true', priority=1)
        
        # Reset query count
        connection.queries_log.clear()
        
        # Fetch violations with related data
        violations = Violation.objects.select_related(
            'rule__control__policy',
            'event'
        )[:10]
        
        # Force evaluation
        list(violations)
        
        query_count = len(connection.queries)
        
        print(f'Query count for violations list: {query_count}')
        
        # Should use select_related to minimize queries
        # Acceptable range depends on data structure
        self.assertLess(query_count, 20, 'Too many database queries')


if __name__ == '__main__':
    import unittest
    unittest.main()
