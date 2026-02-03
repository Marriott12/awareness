"""
Enhanced experiment reproducibility with container tracking.

Captures Docker image digests, hashed dependencies, and complete environment
information to ensure experiments can be reproduced exactly.
"""
import subprocess
import platform
import sys
import os
import hashlib
import json
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ReproducibilityCapture:
    """
    Capture comprehensive metadata for experiment reproducibility.
    
    Features:
    - Docker image SHA256 digest
    - Hashed dependency manifest (pip freeze + SHA256)
    - Git commit SHA with dirty status
    - Platform and environment information
    - Cryptographic binding of seed to experiment
    """
    
    @staticmethod
    def get_git_commit() -> Optional[str]:
        """Get current Git commit SHA, or None if not in a repo."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=5,
                check=True
            )
            commit = result.stdout.strip()
            
            # Check for uncommitted changes
            dirty_result = subprocess.run(
                ['git', 'diff-index', '--quiet', 'HEAD', '--'],
                capture_output=True,
                timeout=5
            )
            
            if dirty_result.returncode != 0:
                commit += '-dirty'
            
            return commit
        except Exception as e:
            logger.warning(f'Failed to capture git commit: {e}')
            return None
    
    @staticmethod
    def get_docker_image_digest() -> Optional[str]:
        """
        Get SHA256 digest of current Docker image if running in container.
        
        Returns None if not in a container or unable to determine.
        """
        # Check if running in Docker
        if not os.path.exists('/.dockerenv') and not os.path.exists('/run/.containerenv'):
            return None
        
        try:
            # Try to get image ID from cgroup
            with open('/proc/self/cgroup', 'r') as f:
                cgroup_content = f.read()
            
            # Extract container ID from cgroup path
            for line in cgroup_content.split('\n'):
                if 'docker' in line or 'kubepods' in line:
                    parts = line.split('/')
                    if len(parts) > 0:
                        container_id = parts[-1][:12]  # First 12 chars of container ID
                        
                        # Try to inspect container to get image digest
                        result = subprocess.run(
                            ['docker', 'inspect', '--format={{.Image}}', container_id],
                            capture_output=True,
                            text=True,
                            timeout=5,
                            check=True
                        )
                        
                        image_id = result.stdout.strip()
                        
                        # Get full digest
                        digest_result = subprocess.run(
                            ['docker', 'inspect', '--format={{index .RepoDigests 0}}', image_id],
                            capture_output=True,
                            text=True,
                            timeout=5,
                            check=True
                        )
                        
                        return digest_result.stdout.strip()
            
            return None
        except Exception as e:
            logger.warning(f'Failed to capture Docker image digest: {e}')
            return None
    
    @staticmethod
    def get_dependency_hash() -> str:
        """
        Generate SHA256 hash of all installed dependencies.
        
        Returns hash of pip freeze output for reproducibility verification.
        """
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'freeze'],
                capture_output=True,
                text=True,
                timeout=10,
                check=True
            )
            
            dependencies = result.stdout.strip()
            
            # Sort dependencies for consistent hashing
            sorted_deps = '\n'.join(sorted(dependencies.split('\n')))
            
            # Generate SHA256 hash
            hash_obj = hashlib.sha256(sorted_deps.encode('utf-8'))
            return hash_obj.hexdigest()
        except Exception as e:
            logger.warning(f'Failed to capture dependency hash: {e}')
            return 'unknown'
    
    @staticmethod
    def get_platform_info() -> Dict[str, str]:
        """Get detailed platform and environment information."""
        return {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'python_version': sys.version,
            'python_implementation': platform.python_implementation(),
        }
    
    @staticmethod
    def bind_seed_to_experiment(experiment_id: str, seed: int) -> str:
        """
        Cryptographically bind random seed to experiment ID.
        
        Args:
            experiment_id: Unique experiment identifier
            seed: Random seed value
            
        Returns:
            SHA256 hash binding seed to experiment
        """
        binding_string = f"{experiment_id}:{seed}"
        hash_obj = hashlib.sha256(binding_string.encode('utf-8'))
        return hash_obj.hexdigest()
    
    @classmethod
    def capture_full_metadata(cls, experiment_id: Optional[str] = None, 
                             seed: Optional[int] = None) -> Dict[str, Any]:
        """
        Capture complete reproducibility metadata.
        
        Args:
            experiment_id: Optional experiment identifier for seed binding
            seed: Optional random seed value
            
        Returns:
            Dictionary with all reproducibility metadata
        """
        metadata = {
            'git_commit': cls.get_git_commit(),
            'docker_image_digest': cls.get_docker_image_digest(),
            'dependency_hash': cls.get_dependency_hash(),
            'platform': cls.get_platform_info(),
            'timestamp': None,  # Will be set by caller
        }
        
        # Add seed binding if provided
        if experiment_id and seed is not None:
            metadata['seed'] = seed
            metadata['seed_binding'] = cls.bind_seed_to_experiment(experiment_id, seed)
        
        # Add Django version
        try:
            import django
            metadata['django_version'] = django.get_version()
        except Exception:
            metadata['django_version'] = 'unknown'
        
        # Add container runtime info if available
        if os.path.exists('/.dockerenv'):
            metadata['container_runtime'] = 'docker'
        elif os.path.exists('/run/.containerenv'):
            metadata['container_runtime'] = 'podman'
        else:
            metadata['container_runtime'] = 'none'
        
        return metadata
    
    @classmethod
    def verify_reproducibility(cls, original_metadata: Dict[str, Any], 
                               current_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
        """
        Verify if current environment matches original experiment metadata.
        
        Args:
            original_metadata: Metadata from original experiment
            current_metadata: Optional current metadata (will be captured if not provided)
            
        Returns:
            Dictionary with verification results for each component
        """
        if current_metadata is None:
            current_metadata = cls.capture_full_metadata()
        
        verification = {}
        
        # Check git commit
        if 'git_commit' in original_metadata:
            verification['git_match'] = (
                original_metadata['git_commit'] == current_metadata.get('git_commit')
            )
        
        # Check Docker image
        if 'docker_image_digest' in original_metadata:
            verification['docker_match'] = (
                original_metadata['docker_image_digest'] == current_metadata.get('docker_image_digest')
            )
        
        # Check dependencies
        if 'dependency_hash' in original_metadata:
            verification['dependencies_match'] = (
                original_metadata['dependency_hash'] == current_metadata.get('dependency_hash')
            )
        
        # Check platform (warning only, not strict requirement)
        if 'platform' in original_metadata:
            verification['platform_match'] = (
                original_metadata['platform'] == current_metadata.get('platform')
            )
        
        # Check seed binding
        if 'seed_binding' in original_metadata:
            verification['seed_binding_valid'] = (
                original_metadata['seed_binding'] == current_metadata.get('seed_binding')
            )
        
        # Overall verification (all critical checks must pass)
        critical_checks = ['git_match', 'dependencies_match']
        verification['reproducible'] = all(
            verification.get(check, False) for check in critical_checks
        )
        
        return verification
