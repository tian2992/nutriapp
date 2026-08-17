# Nutriacción App

Una aplicación para llevar un registro de medidas antropométricas y de nutrición.

Creado originalmente para las campañas nutricionales de la Asociación Qachuu Aloom, Rabinal Baja Verapaz, Guatemala, con la misión de mejorar la salud de todas las personas.

## Vision General

TODO: Llenar

## Como Instalar

Python 3.6, Django 5.

### Para desarrollar
```bash
uv init .venv
source .venv/bin/activate
python manage.py makemigrations
python manage.py migrate

python manage.py createsuperuser
python manage.py runserver
```

### Docker crudo

#### Ejecutar migraciones dentro del contenedor

Primero, ejecuta el contenedor:

```bash
# con envfile 
docker run -d -p 8000:8000 --env-file .env --name nutriapp-container nutriapp
```

Luego, ejecuta las migraciones:

```bash
docker exec -it nutriapp-container python manage.py makemigrations
docker exec -it nutriapp-container python manage.py migrate
```

#### Deploy Docker variables de entorno mínimas

```bash
docker run -d \
  -p 8000:8000 \
  -e DATABASE_URL="postgres://user:password@host:5432/nutridb" \
  -e SECRET_KEY="your-secret-key" \
  -e ALLOWED_HOSTS="*" \
  nutriapp 
```

### Docker Compose + Ansible

La opción más sencilla. Básate en el Docker Compose o el adjunto. Validá él .env generado por Ansible.

## Licencia

GNU GPL v3 o posterior.

## Autores
Sebastian Oliva
José Gómez

