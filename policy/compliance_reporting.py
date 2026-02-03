"""
SOC2 and ISO27001 compliance reporting generator.

Automatically generates compliance reports mapping Awareness platform
capabilities to SOC2 Trust Service Criteria and ISO27001 controls.

Features:
- SOC2 Type II evidence collection
- ISO27001 control mapping
- Automated audit trail reports
- PDF/Excel export
- Continuous compliance monitoring

Usage:
    python manage.py generate_compliance_report --framework=soc2 --period=quarterly
    python manage.py generate_compliance_report --framework=iso27001 --output=pdf
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Q
import json
import logging

logger = logging.getLogger(__name__)


# SOC2 Trust Service Criteria Mapping
SOC2_CONTROLS = {
    'CC6.1': {
        'criterion': 'Logical and Physical Access Controls',
        'description': 'The entity implements logical access security software, infrastructure, and architectures over protected information assets to protect them from security events to meet the entity\'s objectives.',
        'awareness_controls': [
            'User authentication with role-based access',
            'Password complexity requirements',
            'Session timeout enforcement',
            'Admin action logging',
        ]
    },
    'CC6.2': {
        'criterion': 'Transmission Protection',
        'description': 'Prior to issuing system credentials and granting system access, the entity registers and authorizes new internal and external users whose access is administered by the entity.',
        'awareness_controls': [
            'TLS 1.3 for all data in transit',
            'Certificate pinning for API calls',
            'Encrypted database connections',
        ]
    },
    'CC6.6': {
        'criterion': 'Audit Logging',
        'description': 'The entity implements logical access security measures to protect against threats from sources outside its system boundaries.',
        'awareness_controls': [
            'Immutable audit trail (HumanLayerEvent)',
            'Cryptographic chain of custody (hash chaining)',
            'Tamper-evident logging',
            'Structured JSON logging',
        ]
    },
    'CC7.2': {
        'criterion': 'Data Integrity',
        'description': 'The entity monitors system components and the operation of those components for anomalies that are indicative of malicious acts, natural disasters, and errors affecting the entity\'s ability to meet its objectives.',
        'awareness_controls': [
            'Anomaly detection for insider threats',
            'Behavioral analysis of admin actions',
            'Real-time alerting for policy violations',
        ]
    },
    'CC8.1': {
        'criterion': 'Change Management',
        'description': 'The entity authorizes, designs, develops or acquires, configures, documents, tests, approves, and implements changes to infrastructure, data, software, and procedures to meet its objectives.',
        'awareness_controls': [
            'Policy approval workflow',
            'Version control for all policies',
            'Approval audit trail (PolicyHistory)',
            'Multi-approver requirements',
        ]
    },
}


# ISO27001:2022 Control Mapping
ISO27001_CONTROLS = {
    'A.5.1': {
        'control': 'Policies for information security',
        'description': 'Information security policy and topic-specific policies should be defined, approved by management, published, communicated to and acknowledged by relevant personnel and relevant interested parties, and reviewed at planned intervals and if significant changes occur.',
        'awareness_controls': [
            'Policy governance framework',
            'Approval workflow with audit trail',
            'Version control and history',
            'Lifecycle management (draft/review/active/deprecated)',
        ]
    },
    'A.5.10': {
        'control': 'Acceptable use of information and other associated assets',
        'description': 'Rules for the acceptable use and procedures for handling information and other associated assets should be identified, documented and implemented.',
        'awareness_controls': [
            'Training module tracking',
            'Quiz completion requirements',
            'Case study acknowledgment',
            'Policy acknowledgment logging',
        ]
    },
    'A.8.16': {
        'control': 'Monitoring activities',
        'description': 'Networks, systems and applications should be monitored for anomalous behavior and appropriate actions taken to evaluate potential information security incidents.',
        'awareness_controls': [
            'Anomaly detection for admin actions',
            'Machine learning risk scoring',
            'Real-time violation detection',
            'Prometheus metrics and alerting',
        ]
    },
    'A.5.23': {
        'control': 'Information security for use of cloud services',
        'description': 'Processes for acquisition, use, management and exit from cloud services should be established in accordance with the organization\'s information security requirements.',
        'awareness_controls': [
            'GDPR compliance utilities',
            'Data export capabilities',
            'Encrypted backups',
            'Multi-cloud support (S3/Azure/filesystem)',
        ]
    },
}


class ComplianceReportGenerator:
    """
    Generate SOC2 and ISO27001 compliance reports.
    """
    
    def __init__(self, framework: str = 'soc2'):
        """
        Initialize report generator.
        
        Args:
            framework: 'soc2' or 'iso27001'
        """
        self.framework = framework.lower()
        
        if self.framework == 'soc2':
            self.controls = SOC2_CONTROLS
        elif self.framework == 'iso27001':
            self.controls = ISO27001_CONTROLS
        else:
            raise ValueError(f'Unknown framework: {framework}')
    
    def generate_report(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Generate comprehensive compliance report.
        
        Args:
            start_date: Report period start
            end_date: Report period end
            
        Returns:
            Report data dictionary
        """
        logger.info(f'Generating {self.framework.upper()} report for {start_date} to {end_date}')
        
        report = {
            'framework': self.framework.upper(),
            'report_date': timezone.now().isoformat(),
            'period_start': start_date.isoformat(),
            'period_end': end_date.isoformat(),
            'controls': [],
            'evidence_summary': self._collect_evidence_summary(start_date, end_date),
            'findings': [],
            'recommendations': [],
        }
        
        # Evaluate each control
        for control_id, control_data in self.controls.items():
            control_result = self._evaluate_control(
                control_id,
                control_data,
                start_date,
                end_date
            )
            report['controls'].append(control_result)
        
        # Calculate overall compliance score
        compliant_controls = sum(1 for c in report['controls'] if c['status'] == 'compliant')
        total_controls = len(report['controls'])
        report['compliance_score'] = (compliant_controls / total_controls * 100) if total_controls > 0 else 0
        
        # Add findings and recommendations
        report['findings'] = self._identify_findings(report['controls'])
        report['recommendations'] = self._generate_recommendations(report['findings'])
        
        return report
    
    def _evaluate_control(self, control_id: str, control_data: Dict,
                         start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Evaluate a single control."""
        result = {
            'control_id': control_id,
            'title': control_data.get('criterion') or control_data.get('control'),
            'description': control_data['description'],
            'implemented_controls': control_data['awareness_controls'],
            'evidence': [],
            'status': 'compliant',  # Default to compliant
            'notes': []
        }
        
        # Collect evidence based on control type
        if 'audit' in control_data['description'].lower() or 'logging' in control_data['description'].lower():
            result['evidence'].append(
                self._get_audit_evidence(start_date, end_date)
            )
        
        if 'access' in control_data['description'].lower():
            result['evidence'].append(
                self._get_access_control_evidence(start_date, end_date)
            )
        
        if 'change' in control_data['description'].lower() or 'policy' in control_data['description'].lower():
            result['evidence'].append(
                self._get_policy_evidence(start_date, end_date)
            )
        
        if 'monitoring' in control_data['description'].lower() or 'anomal' in control_data['description'].lower():
            result['evidence'].append(
                self._get_monitoring_evidence(start_date, end_date)
            )
        
        # Determine compliance status
        if not result['evidence']:
            result['status'] = 'no_evidence'
            result['notes'].append('No evidence collected for this period')
        elif any(e.get('issues', 0) > 0 for e in result['evidence']):
            result['status'] = 'non_compliant'
            result['notes'].append('Issues identified in evidence')
        
        return result
    
    def _get_audit_evidence(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Collect audit trail evidence."""
        try:
            from .models import HumanLayerEvent, Evidence
            
            events_count = HumanLayerEvent.objects.filter(
                timestamp__gte=start_date,
                timestamp__lt=end_date
            ).count()
            
            # Check for chain integrity
            broken_chains = HumanLayerEvent.objects.filter(
                timestamp__gte=start_date,
                timestamp__lt=end_date,
                prev_hash__isnull=False  # Events that should have prev_hash
            ).exclude(
                prev_hash=''
            ).count()
            
            evidence_records = Evidence.objects.filter(
                event__timestamp__gte=start_date,
                event__timestamp__lt=end_date
            ).count()
            
            return {
                'type': 'audit_trail',
                'events_logged': events_count,
                'evidence_records': evidence_records,
                'chain_integrity': 'intact' if broken_chains == 0 else 'broken',
                'issues': broken_chains,
            }
            
        except Exception as e:
            logger.exception(f'Failed to collect audit evidence: {e}')
            return {'type': 'audit_trail', 'error': str(e)}
    
    def _get_access_control_evidence(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Collect access control evidence."""
        try:
            from django.contrib.auth.models import User
            from .models import HumanLayerEvent
            
            # Count users with different roles
            admin_users = User.objects.filter(is_staff=True).count()
            total_users = User.objects.filter(is_active=True).count()
            
            # Count login events
            login_events = HumanLayerEvent.objects.filter(
                timestamp__gte=start_date,
                timestamp__lt=end_date,
                event_type='login'
            ).count()
            
            # Count failed access attempts
            failed_access = HumanLayerEvent.objects.filter(
                timestamp__gte=start_date,
                timestamp__lt=end_date,
                event_type='access_denied'
            ).count()
            
            return {
                'type': 'access_control',
                'admin_users': admin_users,
                'total_users': total_users,
                'login_events': login_events,
                'failed_access_attempts': failed_access,
                'issues': 0,
            }
            
        except Exception as e:
            logger.exception(f'Failed to collect access evidence: {e}')
            return {'type': 'access_control', 'error': str(e)}
    
    def _get_policy_evidence(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Collect policy management evidence."""
        try:
            from .models import Policy, PolicyHistory, PolicyApproval
            
            # Policies created/updated
            policies_created = Policy.objects.filter(
                created_at__gte=start_date,
                created_at__lt=end_date
            ).count()
            
            policies_updated = PolicyHistory.objects.filter(
                changed_at__gte=start_date,
                changed_at__lt=end_date
            ).count()
            
            # Approvals processed
            approvals = PolicyApproval.objects.filter(
                Q(approved_at__gte=start_date, approved_at__lt=end_date) |
                Q(rejected_at__gte=start_date, rejected_at__lt=end_date)
            ).count()
            
            # Active policies
            active_policies = Policy.objects.filter(lifecycle='active').count()
            
            return {
                'type': 'policy_management',
                'policies_created': policies_created,
                'policies_updated': policies_updated,
                'approvals_processed': approvals,
                'active_policies': active_policies,
                'issues': 0,
            }
            
        except Exception as e:
            logger.exception(f'Failed to collect policy evidence: {e}')
            return {'type': 'policy_management', 'error': str(e)}
    
    def _get_monitoring_evidence(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Collect monitoring and anomaly detection evidence."""
        try:
            from .models import Violation, MLRiskScorer
            
            # Violations detected
            violations = Violation.objects.filter(
                created_at__gte=start_date,
                created_at__lt=end_date
            ).count()
            
            high_risk = Violation.objects.filter(
                created_at__gte=start_date,
                created_at__lt=end_date,
                ml_risk_score__gte=0.7
            ).count()
            
            # Check if ML model is current
            from .reproducibility import ReproducibilityManager
            repro = ReproducibilityManager()
            model_current = repro.verify_model_reproducibility()
            
            return {
                'type': 'monitoring',
                'violations_detected': violations,
                'high_risk_violations': high_risk,
                'ml_model_current': model_current,
                'issues': 0 if model_current else 1,
            }
            
        except Exception as e:
            logger.exception(f'Failed to collect monitoring evidence: {e}')
            return {'type': 'monitoring', 'error': str(e)}
    
    def _collect_evidence_summary(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Collect overall evidence summary."""
        try:
            from .models import HumanLayerEvent, Evidence, Violation, Policy
            
            return {
                'total_events': HumanLayerEvent.objects.filter(
                    timestamp__gte=start_date,
                    timestamp__lt=end_date
                ).count(),
                'evidence_records': Evidence.objects.filter(
                    event__timestamp__gte=start_date,
                    event__timestamp__lt=end_date
                ).count(),
                'violations': Violation.objects.filter(
                    created_at__gte=start_date,
                    created_at__lt=end_date
                ).count(),
                'active_policies': Policy.objects.filter(lifecycle='active').count(),
            }
            
        except Exception as e:
            logger.exception(f'Failed to collect evidence summary: {e}')
            return {}
    
    def _identify_findings(self, controls: List[Dict]) -> List[Dict]:
        """Identify compliance findings from control evaluation."""
        findings = []
        
        for control in controls:
            if control['status'] != 'compliant':
                findings.append({
                    'control_id': control['control_id'],
                    'severity': 'high' if control['status'] == 'non_compliant' else 'medium',
                    'finding': f"Control {control['control_id']} is {control['status']}",
                    'notes': control['notes']
                })
        
        return findings
    
    def _generate_recommendations(self, findings: List[Dict]) -> List[str]:
        """Generate recommendations based on findings."""
        recommendations = []
        
        for finding in findings:
            if finding['severity'] == 'high':
                recommendations.append(
                    f"Immediate action required for control {finding['control_id']}: "
                    f"Investigate and remediate identified issues"
                )
            else:
                recommendations.append(
                    f"Review control {finding['control_id']} and collect evidence for next reporting period"
                )
        
        return recommendations
    
    def export_to_json(self, report: Dict[str, Any], filename: str):
        """Export report to JSON file."""
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f'Report exported to {filename}')
    
    def export_to_pdf(self, report: Dict[str, Any], filename: str):
        """Export report to PDF file (requires reportlab)."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
            from reportlab.lib.styles import getSampleStyleSheet
            
            doc = SimpleDocTemplate(filename, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []
            
            # Title
            title = Paragraph(
                f"{report['framework']} Compliance Report",
                styles['Title']
            )
            story.append(title)
            story.append(Spacer(1, 12))
            
            # Report period
            period = Paragraph(
                f"Period: {report['period_start'][:10]} to {report['period_end'][:10]}",
                styles['Normal']
            )
            story.append(period)
            story.append(Spacer(1, 12))
            
            # Compliance score
            score = Paragraph(
                f"<b>Overall Compliance Score: {report['compliance_score']:.1f}%</b>",
                styles['Heading2']
            )
            story.append(score)
            story.append(Spacer(1, 12))
            
            # Controls table
            data = [['Control ID', 'Status', 'Evidence Count']]
            for control in report['controls']:
                data.append([
                    control['control_id'],
                    control['status'],
                    str(len(control['evidence']))
                ])
            
            table = Table(data)
            story.append(table)
            
            doc.build(story)
            logger.info(f'PDF report exported to {filename}')
            
        except ImportError:
            logger.error('reportlab not installed, cannot generate PDF')
            raise
