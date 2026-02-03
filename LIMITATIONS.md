  # System Limitations and Known Trade-offs

**Last Updated:** February 2, 2026  
**Status:** Production Deployment Considerations

This document provides an honest assessment of the system's limitations, architectural trade-offs, and areas requiring future work. Use this to make informed deployment decisions.

---

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

## 3. Risk Scoring (Not Machine Learning)

### Current Implementation
- **RuleBasedScorer:** Weighted sum of manually-chosen features
- **Fixed weights:** Hardcoded in source code, not learned from data
- **Deterministic:** Same inputs always produce same score

### Limitations
❌ **NOT machine learning** - Despite early documentation claims, this is deterministic rule-based  
❌ **No model training** - Weights are manually tuned, not optimized from labeled data  
❌ **No validation dataset** - Cannot measure precision/recall on held-out data  
❌ **Feature engineering is manual** - Features chosen by developer intuition, not feature selection algorithms  
❌ **No online learning** - Cannot adapt to new attack patterns without code changes

### Production Impact
- **Risk:** Scoring will not adapt to novel threats or changing user behavior patterns
- **Mitigation:** Periodically review and manually adjust weights based on incident analysis
- **Future Work:** Implement actual ML pipeline with:
  - Labeled training data collection
  - Scikit-learn or PyTorch model training
  - Cross-validation and hyperparameter tuning
  - Model serialization and versioning
  - A/B testing framework

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

## 5. Policy Lifecycle Governance

### Current Implementation
- **Lifecycle states:** DRAFT → REVIEW → ACTIVE → RETIRED
- **Unique constraint:** Only one policy with same name can be ACTIVE
- **ViolationActionLog:** Tracks acknowledge/resolve actions

### Limitations
❌ **No FSM enforcement** - Can jump directly from DRAFT to RETIRED without review  
❌ **No approval workflow** - No concept of who approved REVIEW → ACTIVE transition  
❌ **No rollback** - Cannot revert to previous policy version  
❌ **No diff view** - Cannot see what changed between versions  
⚠️ **Manual lifecycle management** - Must use admin or management commands, no UI workflow

### Production Impact
- **Risk:** Untested policies could be promoted to ACTIVE without proper review
- **Mitigation:** Implement external approval process, use PolicyHistory for audit trail
- **Future Work:** Django FSM integration, approval workflow, version diffing

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

## 9. Security Considerations

### Current Protections
- **Secret key required in production:** Enforced via environment check
- **Docker secrets:** Dockerfile.prod uses /run/secrets
- **Immutability enforcement:** Application + DB triggers
- **Signed exports:** Cryptographic verification of exported data

### Limitations
❌ **No rate limiting** - Vulnerable to brute force and DoS attacks  
❌ **No input validation** - JSON payloads not validated beyond schema  
❌ **No SQL injection protection beyond Django ORM** - Raw SQL could be vulnerable  
⚠️ **Admin UI exposed** - Django admin has full DB access  
⚠️ **No 2FA requirement** - Admin accounts vulnerable to credential theft  
❌ **No anomaly detection** - Cannot detect insider threats automatically

### Production Impact
- **Risk:** Compromised admin account = full system compromise
- **Mitigation:** Restrict admin access, require 2FA, audit all admin actions, deploy WAF
- **Future Work:** RBAC, admin action logging, anomaly detection on admin behavior

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

## 11. Deployment and Operations

### Current Tooling
- **Dockerfile:** Development and production variants
- **docker-compose.yml:** Local development stack
- **DEPLOY.md:** Step-by-step deployment guide
- **Management commands:** validate_scorer, run_experiment, generate_bundle

### Limitations
❌ **No Kubernetes manifests** - Docker Compose only, not production-grade orchestration  
❌ **No health checks** - No /health endpoint for load balancers  
❌ **No metrics export** - No Prometheus/Grafana integration  
❌ **No log aggregation** - Logs to stdout only, no structured logging  
❌ **No backup strategy** - Database backups not automated  
⚠️ **No zero-downtime deploys** - Requires service restart

### Production Impact
- **Risk:** Deployments cause downtime, no observability into production health
- **Mitigation:** Implement health checks, export metrics to monitoring system, set up DB backups
- **Future Work:** K8s deployment, Prometheus metrics, ELK stack integration, blue-green deploys

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
| Risk Scoring | ✅ HONEST | No | P3 - Document as non-ML |
| Transaction Safety | ⚠️ PARTIAL | No | P2 - Add stress tests |
| Policy Governance | ⚠️ PARTIAL | No | P2 - Add approval workflow |
| Reproducibility | ⚠️ PARTIAL | No | P3 - Improve metadata |
| Scalability | ⚠️ LIMITED | **YES** | P1 - For >10k events/day |
| Security | ⚠️ BASIC | **YES** | P1 - Add rate limiting |
| Testing | ⚠️ PARTIAL | No | P2 - Add integration tests |
| Operations | ⚠️ MINIMAL | **YES** | P1 - Add monitoring |

**Deployment Recommendation:**
- ✅ **Suitable for:** Internal tools, research environments, <100 users, <1k events/day
- ⚠️ **Requires work for:** External-facing, >1000 users, high-value targets
- ❌ **Not ready for:** Financial services, healthcare (HIPAA), high-security environments

---

## References
- [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) - Deployment checklist
- [DEPLOY.md](DEPLOY.md) - Step-by-step deployment guide
- [PROVIDER_VALIDATION.md](policy/PROVIDER_VALIDATION.md) - Signing provider setup
