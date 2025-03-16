# INSTALL

## Python
### It's pretty tricky:
- Photo scaning requires GPU. We need to resolve the cuda conflict between torch, tensorflow.
- We disable the GPU in photo extracting. We can ignore the conflict.

### For photo scaning process:
```bash
pip install -r requirements.txt
pip install 'tensorflow[and-cuda]'
```

### For web application:
```bash
pip install -r requirements.txt
pip install -r web/backend/requirements.txt
```

## PostGresql

### Install PostGresql with pgvector

```bash
## Install apt repo
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo apt update

## Install pg and pgvector

sudo apt install -y postgresql-17 postgresql-17-pgvector

## Login to psql cli
sudo -u postgres psql

## Create the extention

CREATE EXTENSION vector;

## Verify
sudo -u postgres psql
psql (17.4 (Ubuntu 17.4-1.pgdg24.04+2))
Type "help" for help.

postgres=# CREATE EXTENSION vector;
CREATE EXTENSION
postgres=# \dx
                             List of installed extensions
  Name   | Version |   Schema   |                     Description
---------+---------+------------+------------------------------------------------------
 plpgsql | 1.0     | pg_catalog | PL/pgSQL procedural language
 vector  | 0.8.0   | public     | vector data type and ivfflat and hnsw access methods
(2 rows)

postgres=#
```

### Create schema, user, database.

1. Create schema, user, roles

2. Run the script

```bash
sudo -u postgres psql -f db.sql
```
3. Verify
```bash
psql -U mphoto_user -d mphoto_db -h localhost
```
