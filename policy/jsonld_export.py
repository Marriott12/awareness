"""
JSON-LD export format for standardized data portability.

Implements JSON-LD (JSON for Linking Data) export format following Schema.org
standards for maximum interoperability and semantic web compatibility.

Features:
- Schema.org compliant exports
- RDF compatibility
- Linked data structure
- Standard vocabularies
- Cross-platform portability

Usage:
    from policy.jsonld_export import JSONLDExporter
    
    exporter = JSONLDExporter()
    policy_ld = exporter.export_policy(policy_id)
    event_ld = exporter.export_events(start_date, end_date)
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from django.utils import timezone
import json
import logging

logger = logging.getLogger(__name__)


class JSONLDExporter:
    """
    Export Awareness data in JSON-LD format.
    
    JSON-LD (JSON for Linking Data) is a method of encoding linked data using JSON.
    It allows data to be serialized in a way that is compatible with RDF and enables
    semantic web interoperability.
    """
    
    # Schema.org context
    CONTEXT = {
        "@context": {
            "@vocab": "http://schema.org/",
            "awareness": "http://awareness.example.com/schema/",
            "policy": "awareness:policy",
            "event": "awareness:event",
            "evidence": "awareness:evidence",
            "violation": "awareness:violation",
        }
    }
    
    def export_policy(self, policy_id: int) -> Dict[str, Any]:
        """
        Export a policy in JSON-LD format.
        
        Args:
            policy_id: ID of policy to export
            
        Returns:
            JSON-LD representation of policy
        """
        try:
            from .models import Policy
            
            policy = Policy.objects.get(pk=policy_id)
            
            ld_policy = {
                "@context": self.CONTEXT["@context"],
                "@type": "Policy",
                "@id": f"urn:awareness:policy:{policy.id}",
                "identifier": str(policy.id),
                "name": policy.name,
                "description": policy.description or "",
                "dateCreated": policy.created_at.isoformat(),
                "dateModified": policy.updated_at.isoformat(),
                "version": str(policy.version),
                "status": policy.lifecycle,
                "controls": self._export_controls(policy),
            }
            
            # Add approval information if available
            ld_policy["approvals"] = self._export_approvals(policy)
            
            # Add version history
            ld_policy["versionHistory"] = self._export_version_history(policy)
            
            return ld_policy
            
        except Exception as e:
            logger.exception(f'Failed to export policy {policy_id}: {e}')
            return {"error": str(e)}
    
    def _export_controls(self, policy) -> List[Dict[str, Any]]:
        """Export policy controls in JSON-LD format."""
        controls = []
        
        for control in policy.controls.all():
            ld_control = {
                "@type": "awareness:Control",
                "@id": f"urn:awareness:control:{control.id}",
                "identifier": str(control.id),
                "name": control.name,
                "description": control.description or "",
                "rules": self._export_rules(control),
            }
            controls.append(ld_control)
        
        return controls
    
    def _export_rules(self, control) -> List[Dict[str, Any]]:
        """Export control rules in JSON-LD format."""
        rules = []
        
        for rule in control.rules.all():
            ld_rule = {
                "@type": "awareness:Rule",
                "@id": f"urn:awareness:rule:{rule.id}",
                "identifier": str(rule.id),
                "expression": rule.expression,
                "priority": rule.priority,
                "isActive": rule.is_active,
            }
            rules.append(ld_rule)
        
        return rules
    
    def _export_approvals(self, policy) -> List[Dict[str, Any]]:
        """Export policy approvals in JSON-LD format."""
        try:
            from .models import PolicyApproval
            
            approvals = []
            
            for approval in PolicyApproval.objects.filter(policy=policy):
                ld_approval = {
                    "@type": "awareness:Approval",
                    "@id": f"urn:awareness:approval:{approval.id}",
                    "approver": {
                        "@type": "Person",
                        "identifier": str(approval.approver.id),
                        "name": approval.approver.get_full_name() or approval.approver.username,
                    },
                    "dateApproved": approval.approved_at.isoformat() if approval.approved_at else None,
                    "dateRejected": approval.rejected_at.isoformat() if approval.rejected_at else None,
                    "comments": approval.comments or "",
                }
                approvals.append(ld_approval)
            
            return approvals
            
        except Exception as e:
            logger.warning(f'Failed to export approvals: {e}')
            return []
    
    def _export_version_history(self, policy) -> List[Dict[str, Any]]:
        """Export policy version history in JSON-LD format."""
        try:
            from .models import PolicyHistory
            
            versions = []
            
            for history in PolicyHistory.objects.filter(policy=policy).order_by('-version'):
                ld_version = {
                    "@type": "awareness:PolicyVersion",
                    "@id": f"urn:awareness:policy:{policy.id}:version:{history.version}",
                    "version": str(history.version),
                    "dateChanged": history.changed_at.isoformat(),
                    "changedBy": {
                        "@type": "Person",
                        "identifier": str(history.changed_by.id),
                        "name": history.changed_by.get_full_name() or history.changed_by.username,
                    } if history.changed_by else None,
                    "changeReason": history.change_reason or "",
                }
                versions.append(ld_version)
            
            return versions
            
        except Exception as e:
            logger.warning(f'Failed to export version history: {e}')
            return []
    
    def export_events(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Export audit events in JSON-LD format.
        
        Args:
            start_date: Start of export period
            end_date: End of export period
            
        Returns:
            JSON-LD representation of events
        """
        try:
            from .models import HumanLayerEvent
            
            events = HumanLayerEvent.objects.filter(
                timestamp__gte=start_date,
                timestamp__lt=end_date
            ).order_by('timestamp')
            
            ld_events = {
                "@context": self.CONTEXT["@context"],
                "@type": "ItemList",
                "name": "Audit Events",
                "description": f"Events from {start_date.date()} to {end_date.date()}",
                "numberOfItems": events.count(),
                "itemListElement": []
            }
            
            for idx, event in enumerate(events):
                ld_event = {
                    "@type": "awareness:AuditEvent",
                    "@id": f"urn:awareness:event:{event.id}",
                    "position": idx + 1,
                    "identifier": str(event.id),
                    "eventType": event.event_type,
                    "dateCreated": event.timestamp.isoformat(),
                    "source": event.source or "",
                    "agent": {
                        "@type": "Person",
                        "identifier": event.user_id or "",
                    } if event.user_id else None,
                    "description": event.summary or "",
                    "additionalProperty": [
                        {
                            "@type": "PropertyValue",
                            "name": "details",
                            "value": json.dumps(event.details) if event.details else "{}"
                        },
                        {
                            "@type": "PropertyValue",
                            "name": "signature",
                            "value": event.signature or ""
                        },
                        {
                            "@type": "PropertyValue",
                            "name": "prev_hash",
                            "value": event.prev_hash or ""
                        }
                    ]
                }
                
                ld_events["itemListElement"].append(ld_event)
            
            return ld_events
            
        except Exception as e:
            logger.exception(f'Failed to export events: {e}')
            return {"error": str(e)}
    
    def export_violations(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Export violations in JSON-LD format.
        
        Args:
            start_date: Start of export period
            end_date: End of export period
            
        Returns:
            JSON-LD representation of violations
        """
        try:
            from .models import Violation
            
            violations = Violation.objects.filter(
                created_at__gte=start_date,
                created_at__lt=end_date
            ).select_related('rule', 'event')
            
            ld_violations = {
                "@context": self.CONTEXT["@context"],
                "@type": "ItemList",
                "name": "Policy Violations",
                "description": f"Violations from {start_date.date()} to {end_date.date()}",
                "numberOfItems": violations.count(),
                "itemListElement": []
            }
            
            for idx, violation in enumerate(violations):
                ld_violation = {
                    "@type": "awareness:Violation",
                    "@id": f"urn:awareness:violation:{violation.id}",
                    "position": idx + 1,
                    "identifier": str(violation.id),
                    "dateCreated": violation.created_at.isoformat(),
                    "rule": {
                        "@type": "awareness:Rule",
                        "@id": f"urn:awareness:rule:{violation.rule.id}",
                        "identifier": str(violation.rule.id),
                        "name": violation.rule.expression,
                    } if violation.rule else None,
                    "relatedEvent": {
                        "@type": "awareness:AuditEvent",
                        "@id": f"urn:awareness:event:{violation.event.id}",
                        "identifier": str(violation.event.id),
                    } if violation.event else None,
                    "riskScore": float(violation.ml_risk_score) if violation.ml_risk_score else None,
                    "humanReview": {
                        "@type": "Review",
                        "reviewRating": {
                            "@type": "Rating",
                            "ratingValue": "confirmed" if violation.human_confirmed else "rejected"
                        },
                        "author": {
                            "@type": "Person",
                            "identifier": str(violation.human_reviewer.id),
                            "name": violation.human_reviewer.get_full_name() or violation.human_reviewer.username,
                        } if violation.human_reviewer else None,
                        "datePublished": violation.human_reviewed_at.isoformat() if violation.human_reviewed_at else None,
                    } if violation.human_reviewed_at else None
                }
                
                ld_violations["itemListElement"].append(ld_violation)
            
            return ld_violations
            
        except Exception as e:
            logger.exception(f'Failed to export violations: {e}')
            return {"error": str(e)}
    
    def export_full_dataset(self, output_file: str):
        """
        Export complete dataset in JSON-LD format.
        
        Args:
            output_file: Path to output file
        """
        try:
            from .models import Policy
            
            dataset = {
                "@context": self.CONTEXT["@context"],
                "@type": "Dataset",
                "name": "Awareness Platform Data Export",
                "description": "Complete export of Awareness platform data",
                "dateCreated": timezone.now().isoformat(),
                "hasPart": []
            }
            
            # Export all policies
            for policy in Policy.objects.all():
                dataset["hasPart"].append(self.export_policy(policy.id))
            
            # Export recent events (last 90 days)
            end_date = timezone.now()
            start_date = end_date - timezone.timedelta(days=90)
            
            dataset["hasPart"].append(
                self.export_events(start_date, end_date)
            )
            
            dataset["hasPart"].append(
                self.export_violations(start_date, end_date)
            )
            
            # Write to file
            with open(output_file, 'w') as f:
                json.dump(dataset, f, indent=2, default=str)
            
            logger.info(f'Full dataset exported to {output_file}')
            
        except Exception as e:
            logger.exception(f'Failed to export full dataset: {e}')
            raise
    
    def validate_jsonld(self, ld_data: Dict[str, Any]) -> bool:
        """
        Validate JSON-LD structure.
        
        Args:
            ld_data: JSON-LD data to validate
            
        Returns:
            True if valid
        """
        # Basic validation
        if "@context" not in ld_data:
            logger.error('Missing @context')
            return False
        
        if "@type" not in ld_data:
            logger.error('Missing @type')
            return False
        
        # Could add more sophisticated validation using pyld library
        # For now, just basic checks
        
        return True
