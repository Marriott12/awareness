"""
Management command to populate the database with comprehensive, realistic sample data.

This creates production-quality data that looks authentic, not like test data.
Includes: Policies, Controls, Rules, Training, Quizzes, Case Studies
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate database with comprehensive, realistic security awareness data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=5,
            help='Number of regular users to create'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting data population...'))
        
        # Create users
        users = self.create_users(options['users'])
        
        # Create policies with controls and rules
        policies = self.create_policies()
        
        # Create training modules
        training_modules = self.create_training_modules()
        
        # Create case studies
        case_studies = self.create_case_studies()
        
        # Create quizzes with questions
        quizzes = self.create_quizzes()
        
        # Create some sample progress and attempts for users
        self.create_user_activity(users, training_modules, quizzes)
        
        # Create some sample violations for demonstration
        self.create_sample_violations(users, policies)
        
        self.stdout.write(self.style.SUCCESS('✅ Data population complete!'))
        self.stdout.write(self.style.SUCCESS(f'Created: {len(users)} users, {len(policies)} policies, {len(training_modules)} modules, {len(case_studies)} case studies, {len(quizzes)} quizzes'))

    def create_users(self, count):
        """Create realistic user accounts."""
        self.stdout.write('Creating users...')
        
        # Create admin if doesn't exist
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@company.com',
                'is_staff': True,
                'is_superuser': True,
                'first_name': 'System',
                'last_name': 'Administrator'
            }
        )
        if created:
            admin.set_password('admin123')
            admin.save()
            self.stdout.write(f'  Created admin user (password: admin123)')
        
        # Create regular users with realistic names
        user_data = [
            ('john.smith', 'John', 'Smith', 'john.smith@company.com'),
            ('sarah.johnson', 'Sarah', 'Johnson', 'sarah.johnson@company.com'),
            ('michael.chen', 'Michael', 'Chen', 'michael.chen@company.com'),
            ('emily.rodriguez', 'Emily', 'Rodriguez', 'emily.rodriguez@company.com'),
            ('david.williams', 'David', 'Williams', 'david.williams@company.com'),
            ('lisa.anderson', 'Lisa', 'Anderson', 'lisa.anderson@company.com'),
            ('james.taylor', 'James', 'Taylor', 'james.taylor@company.com'),
            ('maria.garcia', 'Maria', 'Garcia', 'maria.garcia@company.com'),
        ]
        
        users = [admin]
        for username, first, last, email in user_data[:count]:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'first_name': first,
                    'last_name': last,
                    'is_staff': False,
                }
            )
            if created:
                user.set_password('password123')
                user.save()
                self.stdout.write(f'  Created user: {username}')
            users.append(user)
        
        return users

    def create_policies(self):
        """Create realistic security policies with controls and rules."""
        from policy.models import Policy, Control, Rule, Threshold
        
        self.stdout.write('Creating policies...')
        
        policies_data = [
            {
                'name': 'Social Media Operations Security',
                'description': 'Comprehensive guidelines for secure social media usage to prevent operational security breaches, information leakage, and adversarial reconnaissance.',
                'version': '2.1',
                'lifecycle': 'active',
                'notification_channel': 'security-ops@company.com',
                'sla_hours': 24,
                'controls': [
                    {
                        'name': 'Location Privacy Protection',
                        'description': 'Prevent disclosure of physical locations through posts, photos, check-ins, or metadata that could enable threat actor targeting.',
                        'severity': 'critical',
                        'rules': [
                            {'name': 'No Geotagging', 'operator': '==', 'left_operand': 'post.geotag_enabled', 'right_value': False},
                            {'name': 'No Location Keywords', 'operator': 'not_in', 'left_operand': 'post.content', 'right_value': ['base', 'deployment', 'station', 'facility']},
                        ]
                    },
                    {
                        'name': 'Personal Information Control',
                        'description': 'Restrict sharing of personally identifiable information that could be used for social engineering, doxxing, or targeted attacks.',
                        'severity': 'high',
                        'rules': [
                            {'name': 'No PII in Bio', 'operator': 'not_in', 'left_operand': 'profile.bio', 'right_value': ['phone', 'address', 'DOB']},
                            {'name': 'Limited Contact Info', 'operator': '<=', 'left_operand': 'profile.contact_fields', 'right_value': 1},
                        ]
                    },
                    {
                        'name': 'Operational Information Security',
                        'description': 'Prevent inadvertent disclosure of mission details, unit information, or operational capabilities through social media activity.',
                        'severity': 'critical',
                        'rules': [
                            {'name': 'No Mission Details', 'operator': 'not_in', 'left_operand': 'post.content', 'right_value': ['mission', 'operation', 'deployment']},
                            {'name': 'No Unit Identification', 'operator': '!=', 'left_operand': 'post.unit_mention', 'right_value': True},
                        ]
                    },
                ]
            },
            {
                'name': 'Data Classification and Handling',
                'description': 'Enforce proper handling, storage, and transmission of classified and sensitive information across all communication channels.',
                'version': '3.0',
                'lifecycle': 'active',
                'notification_channel': 'data-security@company.com',
                'sla_hours': 12,
                'controls': [
                    {
                        'name': 'Classified Material Protection',
                        'description': 'Ensure classified information is only processed on approved systems with appropriate clearances and need-to-know.',
                        'severity': 'critical',
                        'rules': [
                            {'name': 'Approved System Only', 'operator': '==', 'left_operand': 'system.classification_approved', 'right_value': True},
                            {'name': 'Valid Clearance', 'operator': 'in', 'left_operand': 'user.clearance', 'right_value': ['SECRET', 'TOP_SECRET', 'TS/SCI']},
                        ]
                    },
                    {
                        'name': 'Encryption Requirements',
                        'description': 'Mandate encryption for data at rest and in transit based on sensitivity classification level.',
                        'severity': 'high',
                        'rules': [
                            {'name': 'Encryption Enabled', 'operator': '==', 'left_operand': 'transmission.encrypted', 'right_value': True},
                            {'name': 'Strong Cipher', 'operator': 'in', 'left_operand': 'encryption.algorithm', 'right_value': ['AES-256', 'RSA-2048']},
                        ]
                    },
                ]
            },
            {
                'name': 'Access Control and Authentication',
                'description': 'Establish strong authentication requirements and access control mechanisms to prevent unauthorized system access.',
                'version': '1.5',
                'lifecycle': 'active',
                'notification_channel': 'iam-team@company.com',
                'sla_hours': 8,
                'controls': [
                    {
                        'name': 'Multi-Factor Authentication',
                        'description': 'Require multi-factor authentication for all system access, especially privileged accounts and remote connections.',
                        'severity': 'critical',
                        'rules': [
                            {'name': 'MFA Enabled', 'operator': '==', 'left_operand': 'auth.mfa_enabled', 'right_value': True},
                            {'name': 'Strong Second Factor', 'operator': 'in', 'left_operand': 'auth.second_factor', 'right_value': ['TOTP', 'Hardware_Token', 'Biometric']},
                        ]
                    },
                    {
                        'name': 'Password Strength Requirements',
                        'description': 'Enforce minimum password complexity and rotation policies to prevent credential compromise.',
                        'severity': 'medium',
                        'rules': [
                            {'name': 'Minimum Length', 'operator': '>=', 'left_operand': 'password.length', 'right_value': 12},
                            {'name': 'Complexity Check', 'operator': '==', 'left_operand': 'password.complex', 'right_value': True},
                        ]
                    },
                ]
            },
        ]
        
        policies = []
        for policy_data in policies_data:
            controls_data = policy_data.pop('controls')
            policy, created = Policy.objects.get_or_create(
                name=policy_data['name'],
                defaults=policy_data
            )
            if created:
                self.stdout.write(f'  Created policy: {policy.name}')
            policies.append(policy)
            
            # Create controls and rules
            for control_data in controls_data:
                rules_data = control_data.pop('rules', [])
                control, created = Control.objects.get_or_create(
                    policy=policy,
                    name=control_data['name'],
                    defaults=control_data
                )
                if created:
                    self.stdout.write(f'    Created control: {control.name}')
                
                # Create rules
                for rule_data in rules_data:
                    rule_data['right_value'] = str(rule_data['right_value'])  # Convert to JSON-compatible string
                    Rule.objects.get_or_create(
                        control=control,
                        name=rule_data['name'],
                        defaults=rule_data
                    )
        
        return policies

    def create_training_modules(self):
        """Create comprehensive training modules."""
        from training.models import TrainingModule
        
        self.stdout.write('Creating training modules...')
        
        modules_data = [
            {
                'title': 'Operations Security (OPSEC) Fundamentals',
                'slug': 'opsec-fundamentals',
                'content': '''# Operations Security Fundamentals

## Overview
Operations Security (OPSEC) is a critical process that identifies critical information, determines if friendly actions can be observed, and prevents adversaries from detecting sensitive activities.

## The Five-Step OPSEC Process

### 1. Identify Critical Information
- Mission details and timelines
- Personnel locations and movements
- Communication methods and frequencies
- Capabilities and limitations
- Vulnerabilities in operations

### 2. Analyze Threats
- Who wants to exploit your information?
- What are their capabilities?
- What collection methods might they use?

### 3. Analyze Vulnerabilities
- How could adversaries obtain critical information?
- What indicators might you be exposing?
- Are there patterns in your behavior?

### 4. Assess Risk
- What's the likelihood of exploitation?
- What's the potential impact?
- Prioritize vulnerabilities by risk level

### 5. Apply Countermeasures
- Implement protective measures
- Change procedures to reduce indicators
- Use deception when appropriate
- Monitor effectiveness

## Key Principles
- **Need to Know**: Share information only with those who require it
- **Least Privilege**: Grant minimum access necessary
- **Defense in Depth**: Layer multiple security measures
- **Continuous Assessment**: Regularly review and update OPSEC practices

Remember: OPSEC is everyone's responsibility!''',
                'order': 1
            },
            {
                'title': 'Social Media Security Best Practices',
                'slug': 'social-media-security',
                'content': '''# Social Media Security

## Introduction
Social media platforms are powerful tools for connection, but they also present significant security risks when used improperly. This module covers essential practices for maintaining operational security online.

## Privacy Settings

### Profile Configuration
- Review all privacy settings quarterly
- Limit profile visibility to friends/connections only
- Disable location services and geotagging
- Remove work information from public profiles
- Use privacy-focused profile pictures

### Content Controls
- Review all posts before publishing
- Disable automatic photo tagging
- Limit who can see your friends list
- Restrict post visibility to trusted contacts
- Enable post approval for tagged content

## Information Control

### What NOT to Post
- **Location Information**: Current or future locations, travel plans
- **Operational Details**: Mission information, deployment schedules
- **Personal Identifiers**: Full names of family, phone numbers, addresses
- **Security Information**: Badges, access cards, security procedures
- **Sensitive Photos**: Military installations, equipment, unit insignia

### Safe Posting Guidelines
- Delay posting about events (post after, not during)
- Avoid routine patterns in posting times
- Be vague about locations and activities
- Think before you share or comment
- Consider who might see your content

## Threat Awareness

### Common Attacks
- **Social Engineering**: Manipulating you to reveal information
- **Reconnaissance**: Gathering intelligence through your posts
- **Doxxing**: Publishing private information about you
- **Impersonation**: Fake profiles pretending to be you or friends

### Red Flags
- Friend requests from unknown people
- Messages asking for personal information
- Suspicious links or attachments
- Profiles with limited information or activity
- Questions about work, locations, or schedules

## Best Practices
1. Separate professional and personal accounts
2. Use strong, unique passwords for each platform
3. Enable multi-factor authentication
4. Regularly audit your connections
5. Report suspicious activity immediately
6. Educate family members about OPSEC

Your social media activity can reveal more than you think. Stay vigilant!''',
                'order': 2
            },
            {
                'title': 'Recognizing and Reporting Security Incidents',
                'slug': 'security-incident-reporting',
                'content': '''# Security Incident Recognition and Reporting

## What is a Security Incident?

A security incident is any event that could compromise the confidentiality, integrity, or availability of information or systems.

## Types of Security Incidents

### Information Compromise
- Unauthorized disclosure of classified information
- Data breach or leak
- Inadvertent information sharing
- Loss of controlled documents or devices

### Cyber Incidents
- Malware infection
- Phishing or social engineering attack
- Unauthorized system access
- Denial of service attack
- Suspicious network activity

### Physical Security
- Unauthorized facility access
- Lost or stolen access cards
- Tailgating or piggybacking
- Unattended workstations with sensitive data

### Policy Violations
- Failure to follow security procedures
- Improper data handling
- Unauthorized software installation
- Security control bypassing

## Recognition Indicators

### Technical Indicators
- Unusual system behavior or performance
- Unexpected pop-ups or error messages
- Files or programs you didn't install
- Account locked or password changed
- Missing or modified files

### Behavioral Indicators
- Suspicious questions about security
- Unusual interest in restricted areas
- Photography of sensitive locations
- Attempts to obtain unauthorized information
- Pressure to bypass security procedures

### Environmental Indicators
- Unlocked doors or cabinets
- Visitors without proper badges
- Equipment in unusual locations
- Missing security equipment
- Signs of tampering or forced entry

## Reporting Process

### Immediate Actions (First 15 Minutes)
1. **Stop** - Don't continue the activity that may have caused the incident
2. **Secure** - Lock screens, secure documents, isolate systems if needed
3. **Document** - Note time, location, and what you observed
4. **Report** - Contact security immediately

### What to Report
- Date and time of incident
- Location and systems involved
- What you were doing when you noticed it
- Specific indicators or evidence
- Any actions you've already taken
- Potential impact or sensitivity

### Reporting Channels
- **Immediate Threats**: Call Security Operations Center (SOC)
- **Cyber Incidents**: Email cybersecurity@company.com
- **Policy Violations**: Report to supervisor
- **Anonymous Reporting**: Use secure reporting portal

### Follow-up
- Preserve evidence (don't delete logs or files)
- Cooperate with investigation
- Document all interactions
- Await guidance before resuming normal operations

## Why Reporting Matters

- Early detection limits damage
- Enables rapid response
- Protects others from similar threats
- Improves overall security posture
- Demonstrates security awareness
- May prevent serious breaches

## Remember
**See Something, Say Something**
- Don't assume someone else will report it
- Better to report a false alarm than miss a real incident
- Timely reporting is critical
- You won't be penalized for good-faith reports
- Your vigilance protects everyone

When in doubt, report it out!''',
                'order': 3
            },
            {
                'title': 'Data Classification and Handling',
                'slug': 'data-classification',
                'content': '''# Data Classification and Handling

## Introduction
Proper data classification ensures that information receives appropriate protection based on its sensitivity and impact if compromised.

## Classification Levels

### TOP SECRET (TS)
- **Definition**: Information that could cause exceptionally grave damage to national security
- **Examples**: War plans, intelligence sources and methods, advanced weapon systems
- **Handling**: Requires TS clearance, need-to-know, secure facilities, encrypted storage
- **Marking**: TOP SECRET header/footer on every page

### SECRET (S)
- **Definition**: Information that could cause serious damage to national security
- **Examples**: Operational plans, tactical intelligence, force deployments
- **Handling**: Requires Secret clearance, need-to-know, locked storage
- **Marking**: SECRET header/footer

### CONFIDENTIAL (C)
- **Definition**: Information that could cause damage to national security
- **Examples**: Technical specifications, administrative procedures
- **Handling**: Requires Confidential clearance, controlled access
- **Marking**: CONFIDENTIAL header/footer

### UNCLASSIFIED
- **Definition**: Information that requires no special protection
- **Handling**: Standard office security practices
- **Marking**: No special marking required (may be marked UNCLASSIFIED for clarity)

### Controlled Unclassified Information (CUI)
- **Definition**: Unclassified information requiring safeguarding or dissemination controls
- **Examples**: PII, FOUO, Law Enforcement Sensitive
- **Handling**: Access restrictions, encryption for transmission
- **Marking**: CUI banner with category

## Handling Requirements

### Storage
- **Classified**: Approved secure containers, rooms, or vaults
- **CUI**: Locked containers or controlled access areas
- **Unclassified**: Standard office security

### Transmission
- **Classified**: Encrypted channels, courier service, classified networks
- **CUI**: Encrypted email, secure file transfer
- **Unclassified**: Standard email, regular mail

### Destruction
- **Classified**: Cross-cut shredding, burning, or degaussing
- **CUI**: Cross-cut shredding or approved destruction method
- **Unclassified**: Standard disposal (shredding recommended)

### Access
- **All Levels**: Need-to-know principle applies
- Verify clearance level matches or exceeds classification
- Document all access in security logs
- Escort uncleared personnel in classified areas

## Common Mistakes to Avoid

1. **Mixing Classifications**: Never store classified and unclassified data together
2. **Improper Marking**: Always mark documents clearly with classification level
3. **Discussing Classified Information**: Avoid classified discussions in unsecure areas
4. **Using Personal Devices**: Never process classified data on unauthorized systems
5. **Leaving Unattended**: Lock screens and secure documents when away
6. **Improper Disposal**: Always use approved destruction methods
7. **Email Mistakes**: Verify recipient clearance before sending
8. **Derivative Classification**: Properly classify information derived from classified sources

## Special Handling Caveats

- **NOFORN**: No foreign nationals
- **ORCON**: Originator controls dissemination
- **RELTO**: Releasable to specific countries
- **PROPIN**: Proprietary information involved
- **FRD**: Formerly Restricted Data

## Questions to Ask
1. What is the classification level?
2. Do I have the proper clearance?
3. Do I have a need-to-know?
4. Is the storage/transmission method approved?
5. Are all markings correct?
6. Who is the original classification authority?

Remember: When in doubt about classification, treat it as the higher level and consult your security officer!''',
                'order': 4
            },
        ]
        
        modules = []
        for module_data in modules_data:
            module, created = TrainingModule.objects.get_or_create(
                slug=module_data['slug'],
                defaults=module_data
            )
            if created:
                self.stdout.write(f'  Created module: {module.title}')
            modules.append(module)
        
        return modules

    def create_case_studies(self):
        """Create realistic security breach case studies."""
        from case_studies.models import CaseStudy
        
        self.stdout.write('Creating case studies...')
        
        case_studies_data = [
            {
                'title': 'Operation: Social Media Geolocation Compromise',
                'summary': '''In 2018, a deployed service member posted vacation photos from a popular travel destination on social media. However, the EXIF metadata embedded in the images revealed the actual GPS coordinates of a classified forward operating base. Adversarial intelligence analysts used this information to map the facility layout and identify vulnerable entry points.

**Impact**: The installation was forced to relocate operations, costing millions in resources and potentially compromising ongoing missions. Several personnel were reassigned, and security protocols were completely overhauled.

**Lessons Learned**: 
- Always disable location services before taking photos
- Strip metadata from images before posting
- Avoid posting photos in real-time from sensitive locations
- Use approved photo review processes for deployed personnel
- Educate family members about OPSEC risks

**Preventive Measures**: Implement mandatory photo security training, deploy metadata removal tools, and establish social media monitoring for deployed units.''',
                'published': True
            },
            {
                'title': 'Fitness Tracker Data Reveals Secret Installation Locations',
                'summary': '''In 2017, a popular fitness tracking application published a global heatmap showing user activity patterns. Security analysts discovered that the data revealed the exact locations, layouts, and patrol routes of classified military installations worldwide. The heatmap showed running paths, perimeter patterns, and even guard rotation schedules based on repeated movement patterns.

**Impact**: Multiple installation locations were exposed, patrol patterns were compromised, and adversaries gained detailed intelligence on security procedures. The incident led to a complete review of wearable device policies across all installations.

**Lessons Learned**:
- Personal devices can collect and transmit sensitive location data
- Aggregated data can reveal patterns even when individual data seems innocuous
- Third-party applications may share data in unexpected ways
- Privacy settings alone are insufficient for operational security
- Regular device security audits are essential

**Preventive Measures**: Ban unauthorized fitness trackers in sensitive areas, implement device scanning at security checkpoints, educate personnel on data collection risks, and establish approved fitness tracking solutions with proper security controls.''',
                'published': True
            },
            {
                'title': 'Phishing Attack Compromises Contractor Network',
                'summary': '''In 2020, a sophisticated spear-phishing campaign targeted defense contractors with emails appearing to come from legitimate government addresses. The emails contained realistic-looking documents about contract renewals that, when opened, installed malware providing persistent access to the contractor's network. Over six months, adversaries exfiltrated technical specifications, employee credentials, and classified project details.

**Impact**: Estimated 15TB of sensitive data was stolen, including designs for advanced systems. Multiple contracts were terminated, security clearances were revoked, and the company faced significant financial and reputational damage. The breach potentially set back several defense programs by years.

**Lessons Learned**:
- Social engineering attacks are increasingly sophisticated
- Email authentication (DKIM, SPF, DMARC) is critical
- Employee training must include realistic attack scenarios
- Network segmentation limits breach impact
- Continuous monitoring can detect anomalous behavior
- Incident response plans must be regularly tested

**Preventive Measures**: Deploy advanced email filtering, implement zero-trust network architecture, conduct regular phishing simulations, establish security awareness training programs, and deploy endpoint detection and response (EDR) solutions.''',
                'published': True
            },
            {
                'title': 'Insider Threat: Unauthorized Data Exfiltration',
                'summary': '''In 2019, a trusted employee with legitimate access to classified systems began systematically copying sensitive documents to personal USB drives over a three-month period. The employee, motivated by financial gain, planned to sell the information to foreign intelligence services. The breach was only detected when anomaly detection software flagged unusual file access patterns and large data transfers during non-business hours.

**Impact**: Over 10,000 classified documents were compromised before detection. The incident required a comprehensive damage assessment, re-classification of exposed information, and notification to affected intelligence partners. Several ongoing operations had to be abandoned due to compromised methods.

**Lessons Learned**:
- Insider threats are among the most dangerous security risks
- Privileged access requires enhanced monitoring
- Behavioral analytics can detect anomalous patterns
- Regular access reviews are essential
- Multiple indicators may be needed before detection
- Trust but verify principles must apply to all users

**Preventive Measures**: Implement user and entity behavior analytics (UEBA), enforce principle of least privilege, disable unauthorized removable media, deploy data loss prevention (DLP) solutions, conduct regular access audits, and establish insider threat programs with psychological evaluation components.''',
                'published': True
            },
            {
                'title': 'Conference Wi-Fi Exploitation and Man-in-the-Middle Attack',
                'summary': '''During a 2021 international defense industry conference, multiple attendees connected to what appeared to be the official conference Wi-Fi network. In reality, adversaries had established a rogue access point with a similar name. This man-in-the-middle position allowed attackers to intercept emails, capture credentials, and inject malware into downloaded files. Victims included senior executives, government officials, and technical experts who unknowingly exposed sensitive communications.

**Impact**: Hundreds of credentials were compromised, multiple email accounts were accessed, and several malware infections occurred. The incident enabled follow-on attacks against victim organizations for months afterward. Sensitive contract negotiations and technical discussions were exposed to foreign intelligence.

**Lessons Learned**:
- Public Wi-Fi networks are inherently untrusted
- SSL/TLS encryption can be bypassed in sophisticated attacks
- VPN usage is critical when accessing sensitive information remotely
- Visual confirmation of network legitimacy is insufficient
- Mobile device management (MDM) can enforce security policies
- Certificate pinning prevents some man-in-the-middle attacks

**Preventive Measures**: Mandate VPN usage for all remote connections, deploy certificate validation solutions, provide organization-managed hotspots for travel, implement mobile threat defense, educate personnel on public Wi-Fi risks, and establish procedures for verifying network authenticity before connection.''',
                'published': True
            },
        ]
        
        case_studies = []
        for study_data in case_studies_data:
            study, created = CaseStudy.objects.get_or_create(
                title=study_data['title'],
                defaults=study_data
            )
            if created:
                self.stdout.write(f'  Created case study: {study.title}')
            case_studies.append(study)
        
        return case_studies

    def create_quizzes(self):
        """Create comprehensive security awareness quizzes."""
        from quizzes.models import Quiz, Question, Choice
        
        self.stdout.write('Creating quizzes...')
        
        quizzes_data = [
            {
                'title': 'Operations Security (OPSEC) Fundamentals Assessment',
                'attempt_limit': 3,
                'questions': [
                    {
                        'text': 'What is the primary goal of Operations Security (OPSEC)?',
                        'choices': [
                            {'text': 'To prevent adversaries from detecting critical information and activities', 'is_correct': True},
                            {'text': 'To encrypt all communications', 'is_correct': False},
                            {'text': 'To conduct offensive cyber operations', 'is_correct': False},
                            {'text': 'To audit employee social media accounts', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'Which of the following is NOT one of the five steps in the OPSEC process?',
                        'choices': [
                            {'text': 'Identify critical information', 'is_correct': False},
                            {'text': 'Analyze threats and vulnerabilities', 'is_correct': False},
                            {'text': 'Implement quantum encryption', 'is_correct': True},
                            {'text': 'Apply countermeasures', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'An adversary analyzes patterns in your social media posts to determine your location and schedule. This is an example of:',
                        'choices': [
                            {'text': 'Reconnaissance through pattern analysis', 'is_correct': True},
                            {'text': 'Direct hacking', 'is_correct': False},
                            {'text': 'Malware infection', 'is_correct': False},
                            {'text': 'Authorized intelligence collection', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'What does "need to know" mean in the context of OPSEC?',
                        'choices': [
                            {'text': 'Information should only be shared with those who require it to perform their duties', 'is_correct': True},
                            {'text': 'Everyone needs to know everything for transparency', 'is_correct': False},
                            {'text': 'Only senior leadership needs to know critical information', 'is_correct': False},
                            {'text': 'Information should be publicly accessible', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'Which indicator would most likely reveal operational activity to an adversary?',
                        'choices': [
                            {'text': 'Consistent patterns in communication times and locations', 'is_correct': True},
                            {'text': 'Using encrypted messaging', 'is_correct': False},
                            {'text': 'Randomized schedule variations', 'is_correct': False},
                            {'text': 'Proper OPSEC training', 'is_correct': False},
                        ]
                    },
                ]
            },
            {
                'title': 'Social Media Security Assessment',
                'attempt_limit': 3,
                'questions': [
                    {
                        'text': 'You are about to post a photo from your vacation. What should you do FIRST?',
                        'choices': [
                            {'text': 'Check and remove location metadata (EXIF data) from the photo', 'is_correct': True},
                            {'text': 'Post it immediately to share with friends', 'is_correct': False},
                            {'text': 'Add a location tag so friends know where you are', 'is_correct': False},
                            {'text': 'Tag all your colleagues in the photo', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'Which of the following is safe to share on social media?',
                        'choices': [
                            {'text': 'General hobbies and interests that don\'t reveal operational details', 'is_correct': True},
                            {'text': 'Your current deployment location', 'is_correct': False},
                            {'text': 'Photos of your military ID badge', 'is_correct': False},
                            {'text': 'Your unit\'s upcoming mission schedule', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'Someone you don\'t know sends you a friend request claiming to be from your organization. What should you do?',
                        'choices': [
                            {'text': 'Verify their identity through official channels before accepting', 'is_correct': True},
                            {'text': 'Accept immediately since they claim to work with you', 'is_correct': False},
                            {'text': 'Message them your work details to confirm', 'is_correct': False},
                            {'text': 'Share their profile with all your contacts', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'What is "geotagging" and why is it a security risk?',
                        'choices': [
                            {'text': 'Embedding location coordinates in photos/posts, revealing your physical location', 'is_correct': True},
                            {'text': 'A secure method of marking sensitive documents', 'is_correct': False},
                            {'text': 'A type of encryption for social media', 'is_correct': False},
                            {'text': 'An approved method for sharing location data', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'When is the best time to post about an event or activity?',
                        'choices': [
                            {'text': 'After the event has concluded and you have left the location', 'is_correct': True},
                            {'text': 'During the event in real-time', 'is_correct': False},
                            {'text': 'Before the event to let people know your plans', 'is_correct': False},
                            {'text': 'Social media posting should be avoided entirely', 'is_correct': False},
                        ]
                    },
                ]
            },
            {
                'title': 'Data Classification and Handling Quiz',
                'attempt_limit': 3,
                'questions': [
                    {
                        'text': 'Which classification level could cause "exceptionally grave damage" to national security if disclosed?',
                        'choices': [
                            {'text': 'TOP SECRET', 'is_correct': True},
                            {'text': 'SECRET', 'is_correct': False},
                            {'text': 'CONFIDENTIAL', 'is_correct': False},
                            {'text': 'UNCLASSIFIED', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'You find a document marked "SECRET//NOFORN". What does NOFORN mean?',
                        'choices': [
                            {'text': 'Not releasable to foreign nationals', 'is_correct': True},
                            {'text': 'Not for distribution outside the organization', 'is_correct': False},
                            {'text': 'Requires formal approval before reading', 'is_correct': False},
                            {'text': 'Not formatted for normal printing', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'What is the minimum clearance level required to access CONFIDENTIAL information?',
                        'choices': [
                            {'text': 'CONFIDENTIAL', 'is_correct': True},
                            {'text': 'SECRET', 'is_correct': False},
                            {'text': 'TOP SECRET', 'is_correct': False},
                            {'text': 'No clearance needed', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'How should classified documents be destroyed?',
                        'choices': [
                            {'text': 'Cross-cut shredding, burning, or degaussing (for electronic media)', 'is_correct': True},
                            {'text': 'Regular recycling bin', 'is_correct': False},
                            {'text': 'Deleting the file from the computer', 'is_correct': False},
                            {'text': 'Tearing by hand into small pieces', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'You have a SECRET clearance and need-to-know. Can you access a TOP SECRET document?',
                        'choices': [
                            {'text': 'No, your clearance level must match or exceed the classification', 'is_correct': True},
                            {'text': 'Yes, if you have need-to-know', 'is_correct': False},
                            {'text': 'Yes, if your supervisor approves', 'is_correct': False},
                            {'text': 'Yes, all clearances grant access to all levels', 'is_correct': False},
                        ]
                    },
                ]
            },
            {
                'title': 'Phishing and Social Engineering Defense',
                'attempt_limit': 3,
                'questions': [
                    {
                        'text': 'You receive an urgent email from "IT Support" asking you to verify your password. What should you do?',
                        'choices': [
                            {'text': 'Report it as phishing; legitimate IT never asks for passwords via email', 'is_correct': True},
                            {'text': 'Reply with your password to maintain system access', 'is_correct': False},
                            {'text': 'Click the link to verify your account', 'is_correct': False},
                            {'text': 'Forward it to your colleagues to warn them', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'Which is a red flag indicating a phishing email?',
                        'choices': [
                            {'text': 'Urgent language, suspicious sender address, and unexpected attachments', 'is_correct': True},
                            {'text': 'Professional formatting and company logo', 'is_correct': False},
                            {'text': 'Email from a known colleague', 'is_correct': False},
                            {'text': 'Email sent during business hours', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'Someone calls claiming to be from your security office and asks for your access code. This is likely:',
                        'choices': [
                            {'text': 'Social engineering; verify caller identity through official channels first', 'is_correct': True},
                            {'text': 'A legitimate security verification', 'is_correct': False},
                            {'text': 'Required for annual security review', 'is_correct': False},
                            {'text': 'Normal procedure for remote workers', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'What is "spear phishing"?',
                        'choices': [
                            {'text': 'Targeted phishing using personalized information about the victim', 'is_correct': True},
                            {'text': 'Phishing attacks that use fishing terminology', 'is_correct': False},
                            {'text': 'Mass phishing campaigns sent to thousands', 'is_correct': False},
                            {'text': 'Government-authorized penetration testing', 'is_correct': False},
                        ]
                    },
                    {
                        'text': 'Before clicking a link in an email, you should:',
                        'choices': [
                            {'text': 'Hover over it to see the actual URL destination', 'is_correct': True},
                            {'text': 'Click it immediately if it looks legitimate', 'is_correct': False},
                            {'text': 'Forward the email to others for review', 'is_correct': False},
                            {'text': 'Reply to ask if it\'s safe', 'is_correct': False},
                        ]
                    },
                ]
            },
        ]
        
        quizzes = []
        for quiz_data in quizzes_data:
            questions_data = quiz_data.pop('questions')
            quiz, created = Quiz.objects.get_or_create(
                title=quiz_data['title'],
                defaults=quiz_data
            )
            if created:
                self.stdout.write(f'  Created quiz: {quiz.title}')
            quizzes.append(quiz)
            
            # Create questions and choices
            for q_data in questions_data:
                choices_data = q_data.pop('choices')
                question, created = Question.objects.get_or_create(
                    quiz=quiz,
                    text=q_data['text'],
                    defaults=q_data
                )
                
                # Create choices
                for choice_data in choices_data:
                    Choice.objects.get_or_create(
                        question=question,
                        text=choice_data['text'],
                        defaults=choice_data
                    )
        
        return quizzes

    def create_user_activity(self, users, training_modules, quizzes):
        """Create sample user activity (progress and quiz attempts)."""
        from training.models import TrainingProgress
        from quizzes.models import QuizAttempt, QuizResponse, Choice
        
        self.stdout.write('Creating user activity...')
        
        # Create training progress for some users
        for user in users[1:4]:  # First 3 non-admin users
            for module in random.sample(training_modules, k=min(2, len(training_modules))):
                TrainingProgress.objects.get_or_create(
                    user=user,
                    module=module,
                    defaults={'completed_at': timezone.now() - timedelta(days=random.randint(1, 30))}
                )
        
        # Create quiz attempts
        for user in users[1:5]:  # First 4 non-admin users
            for quiz in random.sample(quizzes, k=min(2, len(quizzes))):
                # Random score
                score = random.uniform(60, 100)
                attempt = QuizAttempt.objects.create(
                    user=user,
                    quiz=quiz,
                    score=score,
                    taken_at=timezone.now() - timedelta(days=random.randint(1, 20))
                )
                
                # Create some responses
                for question in quiz.questions.all()[:3]:
                    choices = list(question.choices.all())
                    if choices:
                        selected = random.choice(choices)
                        QuizResponse.objects.create(
                            attempt=attempt,
                            question=question,
                            selected=selected
                        )
        
        self.stdout.write('  Created training progress and quiz attempts')

    def create_sample_violations(self, users, policies):
        """Create sample policy violations for demonstration."""
        from policy.models import Violation, Control
        
        self.stdout.write('Creating sample violations...')
        
        violation_scenarios = [
            {
                'severity': 'high',
                'evidence': {
                    'type': 'social_media_post',
                    'content': 'Posted photo with visible location tag',
                    'timestamp': timezone.now().isoformat(),
                    'platform': 'Instagram',
                }
            },
            {
                'severity': 'medium',
                'evidence': {
                    'type': 'email',
                    'content': 'Sent unencrypted file with CUI marking',
                    'timestamp': (timezone.now() - timedelta(days=5)).isoformat(),
                    'recipient': 'external',
                }
            },
            {
                'severity': 'critical',
                'evidence': {
                    'type': 'system_access',
                    'content': 'Accessed classified system without MFA',
                    'timestamp': (timezone.now() - timedelta(days=10)).isoformat(),
                    'ip_address': '192.168.1.100',
                }
            },
        ]
        
        for user in users[1:4]:  # Create violations for a few users
            for scenario in random.sample(violation_scenarios, k=min(2, len(violation_scenarios))):
                if policies:
                    policy = random.choice(policies)
                    controls = list(policy.controls.all())
                    if controls:
                        control = random.choice(controls)
                        Violation.objects.create(
                            policy=policy,
                            control=control,
                            rule=control.rules.first() if control.rules.exists() else None,
                            user=user,
                            timestamp=timezone.now() - timedelta(days=random.randint(1, 15)),
                            severity=scenario['severity'],
                            evidence=scenario['evidence'],
                            resolved=random.choice([True, False]),
                            acknowledged=random.choice([True, False]),
                        )
        
        self.stdout.write('  Created sample violations')
