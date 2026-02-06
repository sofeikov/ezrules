# Deployment Guide

Best practices and patterns for deploying ezrules in production environments.

---

## Deployment Options

### 1. Docker Deployment

**Recommended for:** Most production deployments

**Advantages:**
- Consistent environment
- Easy scaling
- Simple rollbacks
- Infrastructure as code

**Basic Setup:**

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . /app

# Install uv and dependencies
RUN pip install uv && uv sync

# Run service
CMD ["uv", "run", "ezrules", "api", "--port", "8888"]
```

**Docker Compose:**

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: ezrules
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ezrules
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  api:
    build: .
    command: ["uv", "run", "ezrules", "api", "--port", "8888"]
    environment:
      - EZRULES_DB_ENDPOINT=postgresql://ezrules:${DB_PASSWORD}@postgres:5432/ezrules
      - EZRULES_APP_SECRET=${APP_SECRET}
    ports:
      - "8888:8888"
    depends_on:
      - postgres
    deploy:
      replicas: 3  # Scale API service horizontally

volumes:
  postgres_data:
```

**Launch:**
```bash
docker-compose up -d
```

---

### 2. Kubernetes Deployment

**Recommended for:** Large-scale, cloud-native deployments

**Namespace:**

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ezrules
```

**Secrets:**

```yaml
# secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: ezrules-secrets
  namespace: ezrules
type: Opaque
stringData:
  db-endpoint: postgresql://ezrules:password@postgres-service:5432/ezrules
  app-secret: your-secret-key-here
```

**PostgreSQL:**

```yaml
# postgres.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: ezrules
spec:
  serviceName: postgres-service
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:16
        env:
        - name: POSTGRES_DB
          value: ezrules
        - name: POSTGRES_USER
          value: ezrules
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ezrules-secrets
              key: db-password
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: postgres-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 50Gi
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
  namespace: ezrules
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

**API Service:**

```yaml
# api.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ezrules-api
  namespace: ezrules
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ezrules-api
  template:
    metadata:
      labels:
        app: ezrules-api
    spec:
      containers:
      - name: api
        image: ezrules:latest
        command: ["uv", "run", "ezrules", "api", "--port", "8888"]
        env:
        - name: EZRULES_DB_ENDPOINT
          valueFrom:
            secretKeyRef:
              name: ezrules-secrets
              key: db-endpoint
        - name: EZRULES_APP_SECRET
          valueFrom:
            secretKeyRef:
              name: ezrules-secrets
              key: app-secret
        ports:
        - containerPort: 8888
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /api/v2/ping
            port: 8888
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v2/ping
            port: 8888
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: ezrules-api
  namespace: ezrules
spec:
  selector:
    app: ezrules-api
  ports:
  - port: 8888
    targetPort: 8888
  type: LoadBalancer
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ezrules-api-hpa
  namespace: ezrules
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ezrules-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

**Deploy:**
```bash
kubectl apply -f namespace.yaml
kubectl apply -f secrets.yaml
kubectl apply -f postgres.yaml
kubectl apply -f api.yaml
```

---

### 3. Traditional Server Deployment

**Recommended for:** On-premises or simple deployments

**Setup:**

```bash
# 1. Install dependencies
sudo apt update
sudo apt install python3.12 postgresql nginx

# 2. Clone and setup
git clone https://github.com/sofeikov/ezrules.git
cd ezrules
uv sync

# 3. Initialize database
export EZRULES_DB_ENDPOINT="postgresql://ezrules:password@localhost:5432/ezrules"
uv run ezrules init-db --auto-delete
uv run ezrules init-permissions

# 4. Create systemd service
sudo cp deploy/ezrules-api.service /etc/systemd/system/

# 5. Start service
sudo systemctl enable ezrules-api
sudo systemctl start ezrules-api
```

**Systemd Service File:**

```ini
# /etc/systemd/system/ezrules-api.service
[Unit]
Description=ezrules API Service
After=network.target postgresql.service

[Service]
Type=simple
User=ezrules
WorkingDirectory=/opt/ezrules
Environment="EZRULES_DB_ENDPOINT=postgresql://ezrules:password@localhost:5432/ezrules"
Environment="EZRULES_APP_SECRET=your-secret-key"
ExecStart=/usr/local/bin/uv run ezrules api --port 8888
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## Load Balancing

### Nginx Configuration

**For API Service:**

```nginx
# /etc/nginx/sites-available/ezrules
upstream api_backend {
    least_conn;
    server api-1:8888 max_fails=3 fail_timeout=30s;
    server api-2:8888 max_fails=3 fail_timeout=30s;
    server api-3:8888 max_fails=3 fail_timeout=30s;
}

server {
    listen 443 ssl http2;
    server_name ezrules.company.com;

    ssl_certificate /etc/ssl/certs/ezrules.crt;
    ssl_certificate_key /etc/ssl/private/ezrules.key;

    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_send_timeout 10s;
        proxy_read_timeout 10s;
    }
}
```

---

## Database Setup

### Production PostgreSQL

**Configuration:**

```ini
# postgresql.conf recommendations
max_connections = 200
shared_buffers = 2GB
effective_cache_size = 6GB
maintenance_work_mem = 512MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 10MB
min_wal_size = 1GB
max_wal_size = 4GB
```

**Backups:**

```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR="/backups/ezrules"
DATE=$(date +%Y%m%d_%H%M%S)

pg_dump -h localhost -U ezrules ezrules | gzip > "$BACKUP_DIR/ezrules_$DATE.sql.gz"

# Retain 30 days
find $BACKUP_DIR -name "ezrules_*.sql.gz" -mtime +30 -delete

# Upload to S3 (optional)
aws s3 cp "$BACKUP_DIR/ezrules_$DATE.sql.gz" s3://backups/ezrules/
```

**Replication:**

Set up read replicas for analytics queries:

```bash
# On primary
wal_level = replica
max_wal_senders = 3
wal_keep_size = 1GB

# On replica
hot_standby = on
```

---

## Monitoring

### Health Checks

**Kubernetes:**
```yaml
livenessProbe:
  httpGet:
    path: /api/v2/ping
    port: 8888
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /api/v2/ping
    port: 8888
  initialDelaySeconds: 10
  periodSeconds: 5
```

**Script-Based:**
```bash
#!/bin/bash
# health-check.sh

# Check API service
if ! curl -f http://localhost:8888/api/v2/ping > /dev/null 2>&1; then
    echo "API service down"
    systemctl restart ezrules-api
fi
```

## Security

### SSL/TLS

Use Let's Encrypt for free SSL certificates:

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d ezrules.company.com

# Auto-renewal
sudo certbot renew --dry-run
```

### Firewall Rules

```bash
# Allow only necessary ports
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# Internal services on private network only
# 5432 (PostgreSQL), 8888 (API Service)
```

### Secrets Management

**AWS Secrets Manager:**

```bash
# Store secret
aws secretsmanager create-secret \
  --name ezrules/prod/db-endpoint \
  --secret-string "postgresql://..."

# Retrieve in app
export EZRULES_DB_ENDPOINT=$(aws secretsmanager get-secret-value \
  --secret-id ezrules/prod/db-endpoint \
  --query SecretString --output text)
```

---

## CI/CD

### GitHub Actions Example

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Build Docker image
        run: docker build -t ezrules:${{ github.sha }} .

      - name: Push to registry
        run: |
          echo ${{ secrets.DOCKER_PASSWORD }} | docker login -u ${{ secrets.DOCKER_USERNAME }} --password-stdin
          docker push ezrules:${{ github.sha }}

      - name: Deploy to Kubernetes
        run: |
          kubectl set image deployment/ezrules-api \
            api=ezrules:${{ github.sha }} -n ezrules
```

---

## Scaling Guidelines

| Load | API Instances | Database | Notes |
|------|-------------|----------|-------|
| < 10 req/s | 1 | Single instance | Development/staging |
| 10-50 req/s | 2-3 | Single instance | Small production |
| 50-200 req/s | 3-5 | Single instance + connection pooling | Medium production |
| 200-500 req/s | 5-10 | Primary + read replicas | Large production |
| > 500 req/s | 10+ | Clustered database | Enterprise |

---

## Next Steps

- **[Configuration](../getting-started/configuration.md)** - Environment configuration
- **[Admin Guide](../user-guide/admin-guide.md)** - System administration
- **[Architecture Overview](overview.md)** - System design details
