import click
from flask.cli import FlaskGroup
from flask_server import app, db
from models import User
import os
from dotenv import load_dotenv

load_dotenv()

@click.group()
def cli():
    """Management script for the application."""
    pass

@cli.command('create-db')
def create_db():
    """Create the database and tables."""
    with app.app_context():
        try:
            db.create_all()
            click.echo('Database and tables created successfully!')
        except Exception as e:
            click.echo(f'Error creating database: {e}', err=True)

@cli.command('drop-db')
def drop_db():
    """Drop all tables."""
    if click.confirm('Are you sure you want to drop all tables?', abort=True):
        with app.app_context():
            try:
                db.drop_all()
                click.echo('All tables dropped successfully!')
            except Exception as e:
                click.echo(f'Error dropping tables: {e}', err=True)

@cli.command('init-db')
def init_db():
    """Initialize the database with tables and initial data."""
    with app.app_context():
        try:
            # Create tables
            db.create_all()
            click.echo('Tables created successfully!')
            
            # Check if admin user exists
            admin_email = os.getenv('ADMIN_EMAIL', 'admin@cleverly.com')
            if not User.query.filter_by(email=admin_email).first():
                # Create admin user
                admin = User(
                    name='Admin',
                    email=admin_email,
                    is_active=True
                )
                admin.set_password(os.getenv('ADMIN_PASSWORD', 'admin123'))
                db.session.add(admin)
                db.session.commit()
                click.echo('Admin user created successfully!')
            
            click.echo('Database initialization completed!')
        except Exception as e:
            click.echo(f'Error initializing database: {e}', err=True)

@cli.command('create-user')
@click.option('--name', prompt=True)
@click.option('--email', prompt=True)
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
def create_user(name, email, password):
    """Create a new user."""
    with app.app_context():
        try:
            if User.query.filter_by(email=email).first():
                click.echo('Error: Email already exists!', err=True)
                return
            
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            click.echo(f'User {email} created successfully!')
        except Exception as e:
            click.echo(f'Error creating user: {e}', err=True)

if __name__ == '__main__':
    cli() 