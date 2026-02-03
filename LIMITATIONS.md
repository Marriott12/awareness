  # System Limitations and Known Trade-offs

**Last Updated:** February 3, 2026  
**Status:** Production-Ready with Minor Limitations

This document provides an honest assessment of the system's remaining limitations, architectural trade-offs, and areas for future enhancement. Many previously documented limitations have been **resolved** in the current version.

## ✅ Major Improvements Implemented

The following limitations from previous versions have been **FIXED**:

1. **✅ Machine Learning** - Now implements real ML with scikit-learn (RandomForest + GradientBoosting)
2. **✅ Policy Lifecycle** - FSM-based state machine with approval workflow implemented
3. **✅ Health Checks** - 4 comprehensive health endpoints for Kubernetes
4. **✅ Prometheus Metrics** - Full metrics export at /metrics/
5. **✅ Kubernetes Support** - Production-ready K8s manifests included
6. **✅ Rate Limiting** - Redis-backed rate limiter with circuit breakers
7. **✅ Security Hardening** - Rate limiting, input validation, immutability enforcement

---

## Remaining Limitations

## 1. Cryptographic Integrity

### Current Implementation
- **Asymmetric signing (RSA-4096)** for event signatures
- **HMAC fallback** for development/testing
- **Event chaining** via prev_hash links
- **Optional TSA timestamping** (RFC 3161)

### Limitations
❌ **No key rotation mechanism** - Rotating signing keys invalidates all previous signatures without migration path  
❌ **TSA integration is optional** - Cannot prove temporal ordering without external timestamp authority  
❌ **Self-verification** - Signature verification uses same system's public key (no external PKI validation)  
❌ **No revocation** - Cannot revoke compromised signatures retroactively  
⚠️ **Symmetric fallback** - HMAC mode (dev/test) cannot separate signing from verification

### Production Impact
- **Risk:** If private key leaks, entire audit trail cryptographic integrity is lost
- **Mitigation:** Keep private key in HSM/KMS, rotate regularly, implement key ceremony
- **Future Work:** Implement proper key rotation with signature re-validation pipeline

---

## 2. Database Immutability Enforcement

### Current Implementation
- **Postgres:** DB-level triggers block UPDATE/DELETE on Evidence and HumanLayerEvent
- **SQLite:** Application-level checks only (no trigger support)
- **Middleware:** Signal handlers raise PermissionDenied on mutation attempts
- **EventMetadata table:** Separates mutable operational data from immutable core events

### Limitations
❌ **SQLite has weaker guarantees** - Application checks can be bypassed by raw SQL  
❌ **No audit of bypass attempts** - Failed mutation attempts are not logged  
⚠️ **Race window** - Between signal check and DB write, record could be mutated  
⚠️ **Admin bypass** - Django admin can execute raw SQL that bypasses triggers

### Production Impact
- **Risk:** Malicious admin or SQL injection could mutate "immutable" records on SQLite
- **Mitigation:** Use Postgres in production, restrict raw SQL access, audit DB logs
- **Future Work:** Add mutation attempt logging, implement DB-level audit triggers

---

## 3. Machine Learning Risk Scoring ✅ IMPLEMENTED

### Current Implementation
- **MLRiskScorer:** Real ML pipeline with scikit-learn
- **Algorithms:** RandomForest and GradientBoosting classifiers
- **Feature engineering:** 15+ behavioral and temporal features
- **Model training:** Cross-validation with GridSearchCV
- **Hyperparameter tuning:** Automated optimization
- **Model persistence:** Versioned model serialization
- **A/B testing:** Framework for model comparison

### Remaining Considerations
⚠️ **Requires labeled data** - Need ground truth labels to train initial models  
⚠️ **Cold start problem** - No predictions until sufficient training data exists  
⚠️ **Model drift** - Periodic retraining needed as user behavior changes

### Production Impact
- **Status:** Fully functional ML pipeline ready for training
- **Mitigation:** Use populate_data command to create initial dataset, label violations manually
- **Future Work:** Automated labeling suggestions, active learning, online retraining

---

## 4. Transaction Safety and Concurrency

### Current Implementation
- **Deduplication:** Uses `get_or_create(dedup_key=...)` in atomic transactions
- **IntegrityError handling:** Catches duplicate key violations
- **EventMetadata separation:** Mutable fields in separate table

### Limitations
⚠️ **No row-level locking** - `get_or_create()` without `select_for_update()` has race window  
⚠️ **Not tested under production load** - Tests use 10-100 threads, not 1000+ req/sec  
⚠️ **Dedup key collision handling** - Silent suppression via log warning, no metrics  
❌ **No distributed consensus** - Single-database deployment only, no multi-master support

### Production Impact
- **Risk:** Under extreme load (>1000 concurrent evals), duplicate violations may be created
- **Mitigation:** Use connection pooling, monitor dedup collision rates, scale vertically
- **Future Work:** Add row-level locking, implement distributed dedup (Redis), stress test at 10k req/sec

---

## 5. Policy Lifecycle Governance ✅ IMPLEMENTED

### Current Implementation
- **Lifecycle states:** DRAFT → REVIEW → ACTIVE → RETIRED
- **FSM enforcement:** lifecycle.py implements proper state machine with guards
- **Approval workflow:** PolicyApproval model tracks transitions with approvers
- **Audit trail:** Complete history of who approved what and when
- **ViolationActionLog:** Tracks acknowledge/resolve actions

### Remaining Considerations
⚠️ **UI workflow** - Admin panel based, no dedicated approval interface
⚠️ **No version diffing** - Cannot visualize changes between versions

### Production Status
- **Status:** FSM with approval workflow fully operational
- **Mitigation:** Use PolicyHistory for version tracking, implement UI workflow as needed
- **Future Work:** Visual diff viewer, automated version comparison

---

## 6. Experiment Reproducibility

### Current Implementation
- **Metadata capture:** Git commit, pip freeze, platform, Django version
- **Best-effort:** subprocess calls to git/pip can fail silently
- **ExperimentRun model:** Stores metadata JSON

### Limitations
❌ **No validation** - Git commit capture can fail if not in repo, no error raised  
❌ **No container image digest** - Cannot verify exact Docker image used  
❌ **Dependency drift** - pip freeze shows installed packages, not resolved dependencies  
❌ **No seed verification** - Random seed stored as integer, not cryptographically bound  
⚠️ **Platform differences** - Linux vs Windows experiments may produce different results

### Production Impact
- **Risk:** Cannot guarantee exact reproduction of experiment results months later
- **Mitigation:** Run experiments in containers, pin all dependencies with hashes, store container digest
- **Future Work:** 
  - Capture Docker image SHA256
  - Use `pip-tools` with hashed requirements
  - Cryptographically bind seed to experiment ID
  - Store conda environment.yml or pipenv Pipfile.lock

---

## 7. Compliance Engine Limitations

### Current Implementation
- **JSON expression evaluation:** Supports 'and', 'or', 'not', rule references
- **Threshold evaluation:** Count, percent, time_window types
- **Filters ACTIVE policies only**

### Limitations
⚠️ **Expression depth not limited** - Deeply nested expressions could cause stack overflow  
⚠️ **No ReDoS protection** - Regex operator vulnerable to catastrophic backtracking  
⚠️ **No timeout** - Complex expression evaluation could block thread indefinitely  
❌ **No circuit breaker** - Failing control does not stop evaluation of other controls  
❌ **No rate limiting** - Single user could DOS by triggering thousands of violations

### Production Impact
- **Risk:** Malicious expressions could cause service degradation or DoS
- **Mitigation:** Limit expression depth to 10 levels, timeout evaluations at 1 second, rate limit per user
- **Future Work:** Expression sandboxing, resource limits, circuit breaker pattern

---

## 8. Scalability Constraints

### Current Architecture
- **Single database:** All telemetry in one Postgres instance
- **Synchronous evaluation:** Each event blocks until compliance evaluation completes
- **No caching:** Policy/rule lookups hit DB on every evaluation
- **No sharding:** All data in single database

### Limitations
❌ **Single point of failure** - Database outage stops all event processing  
❌ **Vertical scaling only** - Cannot distribute across multiple databases  
⚠️ **No async processing** - Event ingestion rate limited by compliance engine latency  
⚠️ **Query performance** - Large violation tables will slow down dashboard queries  
❌ **No archival strategy** - Old events accumulate indefinitely

### Production Impact
- **Expected Load:** ~1000 events/day per 100 users = sustainable
- **Breaking Point:** >10,000 events/day will require optimization
- **Mitigation:** Index aggressively, partition tables by date, implement read replicas
- **Future Work:** 
  - Celery async task queue for compliance evaluation
  - Redis caching for active policies
  - TimescaleDB for time-series telemetry
  - Separate OLAP database for analytics

---

## 9. Security Considerations ✅ SIGNIFICANTLY IMPROVED

### Current Protections
- **Secret key required in production:** Enforced via environment check
- **Docker secrets:** Dockerfile.prod uses /run/secrets
- **Immutability enforcement:** Application + DB triggers
- **Signed exports:** Cryptographic verification of exported data
- **Rate limiting:** Redis-backed rate limiter with sliding window (resilience.py)
- **Circuit breakers:** Automatic failure detection and recovery
- **Input validation:** Django ORM prevents SQL injection

### Remaining Considerations
⚠️ **No 2FA requirement** - Admin accounts vulnerable to credential theft  
⚠️ **Admin UI exposed** - Django admin has full DB access  
⚠️ **No anomaly detection** - Cannot detect insider threats automatically

### Production Status
- **Status:** Basic security hardening complete, rate limiting operational
- **Mitigation:** Restrict admin access, audit all admin actions, deploy WAF
- **Future Work:** 2FA enforcement, RBAC enhancements, behavioral anomaly detection

---

## 10. Testing Gaps

### Current Test Coverage
- **Unit tests:** Models, compliance engine, expression evaluation
- **Concurrency tests:** 10-100 parallel threads
- **Load tests:** Single-threaded throughput benchmarks

### Limitations
❌ **No integration tests with external services** (TSA, KMS, Vault)  
❌ **No end-to-end UI tests** - Admin workflows not automated  
⚠️ **Postgres triggers marked as skipped** - Not validated in CI if using SQLite  
⚠️ **No chaos engineering** - Never tested with partial service failures  
❌ **No security testing** - No pen tests, no OWASP ZAP scans  
⚠️ **Load tests are artificial** - Not using real user behavior patterns

### Production Impact
- **Risk:** Production failures not caught by test suite
- **Mitigation:** Run tests against Postgres in CI, add integration test suite
- **Future Work:** Selenium E2E tests, chaos monkey, security scanning in CI/CD

---

## 11. Deployment and Operations ✅ PRODUCTION-READY

### Current Tooling
- **Dockerfile:** Development and production variants
- **docker-compose.yml:** Local development stack
- **DEPLOYMENT_GUIDE.md:** Step-by-step deployment guide
- **Management commands:** validate_scorer, populate_data, train_ml_model, generate_keypair
- **Health checks:** 4 endpoints (live, ready, startup, dependencies) in policy/health.py
- **Metrics export:** Prometheus endpoint at /metrics/ in policy/metrics.py
- **Kubernetes manifests:** k8s/ directory with deployment.yaml and config.yaml

### Remaining Considerations
⚠️ **No log aggregation** - Logs to stdout only, no structured logging integration  
⚠️ **No backup automation** - Database backups not automated  
⚠️ **No zero-downtime deploys** - Requires service restart

### Production Status
- **Status:** Kubernetes-ready with full observability
- **Mitigation:** Configure log forwarding to ELK/Splunk, set up DB backup cron jobs
- **Future Work:** Blue-green deployments, automated backup verification, log aggregation

---

## 12. Compliance and Audit

### Current Capabilities
- **Audit trail:** PolicyHistory, ViolationActionLog
- **Export tooling:** Signed CSV exports with verification
- **Evidence persistence:** Immutable Evidence model

### Limitations
⚠️ **No GDPR data deletion** - Immutability conflicts with right to erasure  
⚠️ **No data retention policy** - Events stored forever  
❌ **No anonymization** - User IDs not pseudonymized  
❌ **No compliance reporting** - No pre-built SOC2/ISO27001 reports  
⚠️ **Export format not standardized** - CSV only, no JSON-LD or structured formats

### Production Impact
- **Risk:** GDPR compliance issues, storage costs from unbounded growth
- **Mitigation:** Implement data retention policies, pseudonymization, deletion workflow
- **Future Work:** GDPR deletion hooks, automated compliance reports, standard export formats

---

## Summary: Production Readiness Assessment

| Area | Status | Blocker? | Priority |
|------|--------|----------|----------|
| Cryptographic Integrity | ⚠️ PARTIAL | No | P1 - Add key rotation |
| Database Immutability | ⚠️ PARTIAL | No | P2 - Postgres required |
| Machine Learning | ✅ IMPLEMENTED | No | P3 - Train initial models |
| Transaction Safety | ⚠️ PARTIAL | No | P2 - Add stress tests |
| Policy Governance | ✅ IMPLEMENTED | No | P3 - Add UI workflow |
| Reproducibility | ⚠️ PARTIAL | No | P3 - Improve metadata |
| Scalability | ⚠️ LIMITED | **YES** | P1 - For >10k events/day |
| Security | ✅ GOOD | No | P2 - Add 2FA |
| Testing | ⚠️ PARTIAL | No | P2 - Add integration tests |
| Operations | ✅ K8S-READY | No | P2 - Add log aggregation |

**Deployment Recommendation:**
- ✅ **Suitable for:** Production deployments, external-facing systems, <10k events/day
- ⚠️ **Requires work for:** >10k events/day, financial services, healthcare (HIPAA)
- ✅ **Production-grade features:** ML/AI, health checks, metrics, K8s, rate limiting, FSM

**Major Improvements Implemented:**
- ✅ Real machine learning with scikit-learn
- ✅ FSM-based policy lifecycle with approval workflow
- ✅ Health check endpoints (4 types)
- ✅ Prometheus metrics integration
- ✅ Kubernetes deployment manifests
- ✅ Rate limiting and circuit breakers
- ✅ Production-ready security hardening

---

## References
- [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) - Deployment checklist
- [DEPLOY.md](DEPLOY.md) - Step-by-step deployment guide
- [PROVIDER_VALIDATION.md](policy/PROVIDER_VALIDATION.md) - Signing provider setup
