# 🚀 Production Deployment Guide

**Awareness Web Portal - 100/100 Production Ready**

This guide walks through deploying the Awareness system from development to production, with all enterprise features enabled.

---

## 📋 Prerequisites

### Required Software
- Python 3.11+
- PostgreSQL 14+ (production) or SQLite (development)
- Redis 7.0+
- Docker & Docker Compose (recommended)
- Kubernetes cluster (for Tier 3 deployment)

### Required Knowledge
- Django basics
- Kubernetes fundamentals (for cloud deployment)
- Basic cryptography concepts

---

## 🏃 Quick Start (Development)

### 1. Clone and Setup

```bash
cd c:\wamp64\www\awareness

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Settings

```bash
# Create .env file
copy .env.example .env  # Windows
# cp .env.example .env  # Linux/Mac

# Edit .env
# Set SECRET_KEY, DEBUG=True, DATABASE_URL, etc.
```

**Minimal .env for development:**
```ini
SECRET_KEY=your-secret-key-here-change-in-production
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1

# Disable optional features for dev
ML_ENABLED=False
TSA_ENABLED=False
```

### 3. Initialize Database

```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Load initial data (optional)
python manage.py loaddata initial_policies.json
```

### 4. Generate Crypto Keys

```bash
# Generate RSA keypair
python manage.py generate_keypair --key-type rsa --output-dir keys/

# Keys saved to:
# - keys/rsa_private.pem (keep secret!)
# - keys/rsa_public.pem
```

### 5. Run Development Server

```bash
python manage.py runserver

# Visit http://127.0.0.1:8000
# Admin: http://127.0.0.1:8000/admin
```

---

## 🔧 Tier 2: Small Production (<1000 users)

### Architecture
- Single server (VPS/EC2/DigitalOcean droplet)
- PostgreSQL database
- Redis for caching + rate limiting
- Nginx reverse proxy
- SSL with Let's Encrypt

### 1. Server Setup (Ubuntu 22.04)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.11 python3.11-venv postgresql redis-server nginx certbot python3-certbot-nginx

# Create app user
sudo useradd -m -s /bin/bash awareness
sudo su - awareness
```

### 2. Application Setup

```bash
# Clone repo
git clone https://github.com/yourorg/awareness.git
cd awareness

# Virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt gunicorn

# Create directories
mkdir -p logs keys ml_models static media
```

### 3. PostgreSQL Setup

```bash
# Create database and user
sudo -u postgres psql

CREATE DATABASE awareness;
CREATE USER awareness_user WITH PASSWORD 'strong_password_here';
ALTER ROLE awareness_user SET client_encoding TO 'utf8';
ALTER ROLE awareness_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE awareness_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE awareness TO awareness_user;
\q
```

### 4. Configure Production Settings

```bash
# Create .env
cat > .env << EOF
SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
DEBUG=False
ALLOWED_HOSTS=awareness.example.com
DATABASE_URL=postgresql://awareness_user:strong_password_here@localhost/awareness

# Redis
REDIS_URL=redis://localhost:6379/0
CACHE_LOCATION=redis://localhost:6379/1
CELERY_BROKER_URL=redis://localhost:6379/2

# ML
ML_ENABLED=True
ML_MODEL_DIR=/home/awareness/awareness/ml_models

# Crypto
CRYPTO_KEY_DIR=/home/awareness/awareness/keys
SIGNATURE_ALGORITHM=rsa

# Rate Limiting
GLOBAL_RATE_LIMIT=1000
GLOBAL_RATE_LIMIT_WINDOW=60

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=awareness@example.com
EMAIL_HOST_PASSWORD=email_password_here
DEFAULT_FROM_EMAIL=awareness@example.com

# Security
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
EOF
```

### 5. Initialize Application

```bash
# Load environment
source venv/bin/activate

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create superuser
python manage.py createsuperuser

# Generate crypto keys
python manage.py generate_keypair --key-type rsa --output-dir keys/
chmod 400 keys/rsa_private.pem
```

### 6. Configure Gunicorn

```bash
# Create systemd service
sudo cat > /etc/systemd/system/awareness.service << EOF
[Unit]
Description=Awareness Web Application
After=network.target

[Service]
Type=notify
User=awareness
Group=awareness
WorkingDirectory=/home/awareness/awareness
Environment="PATH=/home/awareness/awareness/venv/bin"
ExecStart=/home/awareness/awareness/venv/bin/gunicorn awareness.wsgi:application \\
    --bind 127.0.0.1:8000 \\
    --workers 4 \\
    --threads 2 \\
    --worker-class gthread \\
    --access-logfile /home/awareness/awareness/logs/access.log \\
    --error-logfile /home/awareness/awareness/logs/error.log \\
    --log-level info
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
KillSignal=SIGQUIT
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Start service
sudo systemctl daemon-reload
sudo systemctl enable awareness
sudo systemctl start awareness
sudo systemctl status awareness
```

### 7. Configure Celery Workers

```bash
# Celery worker service
sudo cat > /etc/systemd/system/awareness-celery.service << EOF
[Unit]
Description=Awareness Celery Worker
After=network.target redis.service

[Service]
Type=forking
User=awareness
Group=awareness
WorkingDirectory=/home/awareness/awareness
Environment="PATH=/home/awareness/awareness/venv/bin"
ExecStart=/home/awareness/awareness/venv/bin/celery -A awareness worker \\
    --loglevel=info \\
    --concurrency=4 \\
    --max-tasks-per-child=1000 \\
    --logfile=/home/awareness/awareness/logs/celery.log

[Install]
WantedBy=multi-user.target
EOF

# Celery beat service
sudo cat > /etc/systemd/system/awareness-celerybeat.service << EOF
[Unit]
Description=Awareness Celery Beat
After=network.target redis.service

[Service]
Type=simple
User=awareness
Group=awareness
WorkingDirectory=/home/awareness/awareness
Environment="PATH=/home/awareness/awareness/venv/bin"
ExecStart=/home/awareness/awareness/venv/bin/celery -A awareness beat \\
    --loglevel=info \\
    --logfile=/home/awareness/awareness/logs/celerybeat.log

[Install]
WantedBy=multi-user.target
EOF

# Start services
sudo systemctl daemon-reload
sudo systemctl enable awareness-celery awareness-celerybeat
sudo systemctl start awareness-celery awareness-celerybeat
```

### 8. Configure Nginx

```bash
sudo cat > /etc/nginx/sites-available/awareness << EOF
server {
    listen 80;
    server_name awareness.example.com;

    client_max_body_size 10M;

    location /static/ {
        alias /home/awareness/awareness/staticfiles/;
    }

    location /media/ {
        alias /home/awareness/awareness/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/awareness /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 9. Setup SSL with Let's Encrypt

```bash
sudo certbot --nginx -d awareness.example.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

### 10. Train ML Model (Optional)

```bash
# Generate training data
python manage.py run_experiment --seed 42 --scale 1000

# Train model
python manage.py train_ml_model --use-all-labels --algorithm random_forest

# Verify model loaded
python manage.py shell
>>> from policy.ml_scorer import get_ml_scorer
>>> scorer = get_ml_scorer()
>>> print(scorer.version)
```

---

## ☸️ Tier 3: Enterprise Kubernetes Deployment

### Architecture
- Kubernetes cluster (AWS EKS, GKE, AKS)
- PostgreSQL (managed RDS/CloudSQL)
- Redis (managed ElastiCache/MemoryStore)
- Horizontal autoscaling (3-10 pods)
- Load balancer with SSL termination

### 1. Prerequisites

```bash
# Install kubectl
# Install helm
# Configure kubectl for your cluster

# Verify cluster access
kubectl cluster-info
kubectl get nodes
```

### 2. Create Namespace

```bash
kubectl create namespace awareness
kubectl config set-context --current --namespace=awareness
```

### 3. Deploy PostgreSQL (Helm)

```bash
# Add Bitnami repo
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install PostgreSQL
helm install postgres bitnami/postgresql \\
  --set auth.database=awareness \\
  --set auth.username=awareness_user \\
  --set auth.password=CHANGE_THIS_PASSWORD \\
  --set primary.persistence.size=20Gi

# Get connection string
export POSTGRES_PASSWORD=$(kubectl get secret postgres-postgresql -o jsonpath="{.data.postgres-password}" | base64 --decode)
echo "postgresql://awareness_user:$POSTGRES_PASSWORD@postgres-postgresql.awareness.svc.cluster.local/awareness"
```

### 4. Deploy Redis (Helm)

```bash
helm install redis bitnami/redis \\
  --set auth.enabled=false \\
  --set master.persistence.size=5Gi

# Connection: redis.awareness.svc.cluster.local:6379
```

### 5. Create Secrets

```bash
# Generate Django secret key
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'

# Create secret
kubectl create secret generic awareness-secrets \\
  --from-literal=SECRET_KEY='your-secret-key-here' \\
  --from-literal=DB_PASSWORD='CHANGE_THIS_PASSWORD' \\
  --from-literal=EMAIL_HOST_PASSWORD='email-password-here'

# Create crypto keys secret
# Generate keys locally first
python manage.py generate_keypair --key-type rsa --output-dir /tmp/keys

kubectl create secret generic awareness-crypto-keys \\
  --from-file=rsa_private.pem=/tmp/keys/rsa_private.pem \\
  --from-file=rsa_public.pem=/tmp/keys/rsa_public.pem

# Clean up local keys
rm -rf /tmp/keys
```

### 6. Update ConfigMap

```bash
# Edit k8s/config.yaml with your values
# - ALLOWED_HOSTS (your domain)
# - DB_HOST (postgres-postgresql.awareness.svc.cluster.local)
# - REDIS_URL (redis://redis.awareness.svc.cluster.local:6379/0)
# - EMAIL_HOST, EMAIL_HOST_USER, etc.

# Apply ConfigMap
kubectl apply -f k8s/config.yaml
```

### 7. Build and Push Docker Image

```bash
# Create Dockerfile
cat > Dockerfile << EOF
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    postgresql-client \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "awareness.wsgi:application", "--bind", "0.0.0.0:8000"]
EOF

# Build image
docker build -t awareness:latest .

# Tag and push to your registry
docker tag awareness:latest your-registry.com/awareness:latest
docker push your-registry.com/awareness:latest
```

### 8. Deploy Application

```bash
# Update k8s/deployment.yaml with your image
# image: your-registry.com/awareness:latest

# Apply manifests
kubectl apply -f k8s/deployment.yaml

# Watch deployment
kubectl get pods -w

# Check logs
kubectl logs -f deployment/awareness-web
```

### 9. Verify Deployment

```bash
# Check all pods running
kubectl get pods

# Check services
kubectl get svc

# Check ingress
kubectl get ingress

# Test health endpoints
kubectl port-forward svc/awareness-web 8080:80

# In another terminal
curl http://localhost:8080/health/live
curl http://localhost:8080/health/ready
curl http://localhost:8080/health/dependencies
```

### 10. Configure DNS

```bash
# Get load balancer IP
kubectl get ingress awareness-ingress -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Add DNS A record:
# awareness.example.com -> <LOAD_BALANCER_IP>
```

### 11. Setup Monitoring (Prometheus + Grafana)

```bash
# Install kube-prometheus-stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack

# Access Grafana
kubectl port-forward svc/prometheus-grafana 3000:80

# Login: admin / prom-operator

# Import Awareness dashboard (create custom dashboard using /metrics endpoint)
```

---

## 🔒 Security Hardening

### 1. Rotate Crypto Keys

```bash
# Generate new keypair
python manage.py generate_keypair --key-type rsa --output-dir keys_new/

# Re-sign all events with new key
python manage.py rotate_keys --old-key keys/rsa_private.pem --new-key keys_new/rsa_private.pem

# Update deployment with new keys
kubectl create secret generic awareness-crypto-keys-v2 \\
  --from-file=rsa_private.pem=keys_new/rsa_private.pem \\
  --from-file=rsa_public.pem=keys_new/rsa_public.pem

# Update deployment to use new secret
# Then delete old secret
kubectl delete secret awareness-crypto-keys
```

### 2. Enable Web Application Firewall

```bash
# AWS WAF example
# Create WAF rules for:
# - SQL injection protection
# - XSS protection
# - Rate limiting (backup for application-level)
# - Geo-blocking (if needed)
```

### 3. Setup Backups

```bash
# PostgreSQL automated backups (daily)
# Example using CronJob

kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgres-backup
  namespace: awareness
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:14
            command:
            - /bin/sh
            - -c
            - |
              pg_dump -h postgres-postgresql -U awareness_user awareness | gzip > /backups/awareness-\$(date +%Y%m%d).sql.gz
              # Upload to S3/GCS
          restartPolicy: OnFailure
EOF
```

---

## 📊 Monitoring & Alerts

### Key Metrics to Monitor

1. **Application Health**
   - `/health/ready` endpoint status
   - Pod restart count
   - Error rate (5xx responses)

2. **Performance**
   - Request latency (p50, p95, p99)
   - Throughput (requests/sec)
   - Database query time

3. **ML Model**
   - Prediction latency
   - Model version in use
   - Training success rate

4. **Infrastructure**
   - CPU usage (target <70%)
   - Memory usage (target <80%)
   - Disk usage
   - Network traffic

### Alerting Rules (Prometheus)

```yaml
groups:
- name: awareness
  rules:
  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
    for: 5m
    annotations:
      summary: "High error rate detected"
  
  - alert: PodNotReady
    expr: kube_pod_status_ready{namespace="awareness"} == 0
    for: 5m
    annotations:
      summary: "Pod not ready"
  
  - alert: HighMemoryUsage
    expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9
    for: 5m
    annotations:
      summary: "Container memory usage >90%"
```

---

## 🧪 Testing Production Deployment

### 1. Smoke Tests

```bash
# Health checks
curl https://awareness.example.com/health/live
curl https://awareness.example.com/health/ready

# Create event
curl -X POST https://awareness.example.com/api/events/ \\
  -H "Authorization: Token YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "event_type": "user_action",
    "summary": "Test event",
    "severity": "low"
  }'

# Check admin panel
open https://awareness.example.com/admin/
```

### 2. Load Testing

```bash
# Using Apache Bench
ab -n 1000 -c 10 https://awareness.example.com/api/events/

# Using Locust
pip install locust

# Create locustfile.py
cat > locustfile.py << EOF
from locust import HttpUser, task, between

class AwarenessUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def create_event(self):
        self.client.post("/api/events/", json={
            "event_type": "test",
            "summary": "Load test event",
            "severity": "low"
        }, headers={"Authorization": "Token YOUR_TOKEN"})
EOF

# Run load test
locust -f locustfile.py --host https://awareness.example.com
```

---

## 🔄 Zero-Downtime Deployments

### Rolling Update Strategy

```bash
# Update image version
kubectl set image deployment/awareness-web web=awareness:v1.1.0

# Watch rollout
kubectl rollout status deployment/awareness-web

# Rollback if needed
kubectl rollout undo deployment/awareness-web
```

### Blue-Green Deployment

```bash
# Deploy green version
kubectl apply -f deployment-green.yaml

# Switch traffic
kubectl patch service awareness-web -p '{"spec":{"selector":{"version":"green"}}}'

# Verify, then delete blue
kubectl delete -f deployment-blue.yaml
```

---

## 📞 Support & Maintenance

### Common Operations

**Check logs:**
```bash
kubectl logs -f deployment/awareness-web
kubectl logs -f deployment/awareness-celery-worker
```

**Restart services:**
```bash
kubectl rollout restart deployment/awareness-web
```

**Scale manually:**
```bash
kubectl scale deployment/awareness-web --replicas=5
```

**Run management command:**
```bash
kubectl exec -it deployment/awareness-web -- python manage.py <command>
```

**Database shell:**
```bash
kubectl exec -it postgres-postgresql-0 -- psql -U awareness_user awareness
```

---

## 🎉 Deployment Complete!

Your Awareness system is now running in production with:
- ✅ High availability (3+ replicas)
- ✅ Auto-scaling (3-10 pods)
- ✅ SSL encryption
- ✅ Rate limiting
- ✅ Circuit breakers
- ✅ ML model loaded
- ✅ Background workers
- ✅ Health monitoring
- ✅ GDPR compliance

**Next steps:**
1. Configure monitoring dashboards
2. Setup alerting rules
3. Schedule ML model retraining
4. Review security settings
5. Train your team

**Questions?** Check [PRODUCTION_GRADE_FEATURES.md](PRODUCTION_GRADE_FEATURES.md) for detailed documentation.
