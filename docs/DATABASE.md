# Database Documentation

## Database (Docker)

CoherentMobiles uses PostgreSQL 16 managed via Docker Compose. The database schema is initialized automatically on first startup from `database/init/` in dependency-resolved order.

### Configuration
Credentials and port mappings are configured in `.env` (refer to `.env.example` for the template):
- **Host Port:** `5433` (mapped to container port `5432`)
- **Database:** `coherentmobiles`
- **Default Superuser:** `postgres`
- **Volume:** Named volume `postgres_data` mounts to `/var/lib/postgresql/data`

---

### Commands

#### Start the Database
Start the PostgreSQL container in detached mode:
```powershell
docker compose up -d
```
Check status and health:
```powershell
docker compose ps
```

#### Stop the Database
Stop the running database container without deleting data:
```powershell
docker compose stop postgres
```
Or stop and remove containers/networks:
```powershell
docker compose down
```

#### Reset the Database
> [!WARNING]
> This command deletes the persistent volume (`postgres_data`) and drops all database data. The database will re-initialize from scratch on the next startup.
```powershell
docker compose down -v
```

#### Connect with psql

**Option 1: Inside Docker Container (no local psql client required)**
```powershell
docker compose exec postgres psql -U postgres -d coherentmobiles
```

**Option 2: From Host Machine (via local psql)**
```powershell
psql -h localhost -p 5433 -U postgres -d coherentmobiles
```

**Connection String (Host):**
```text
postgresql://postgres:postgres_secure_password@localhost:5433/coherentmobiles
```

**Connection String (Container-to-Container / Docker Network):**
```text
postgresql://postgres:postgres_secure_password@postgres:5432/coherentmobiles
```
