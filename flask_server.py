from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from datetime import datetime, timedelta
from data_processor import fetch_monday_data, process_sales_data, get_performance_metrics
from dotenv import load_dotenv
from flask_migrate import Migrate
from models import db, User

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder='pages', static_folder='static')

# Configure PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://localhost/cleverly')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Secret key for session management (use a proper secret key in production)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))

# Initialize database and migrations
db.init_app(app)
migrate = Migrate(app, db)

# Add custom Jinja2 filters
@app.template_filter('number_format')
def number_format_filter(value):
    """Format a number with thousands separator"""
    try:
        return "{:,}".format(float(value))
    except (ValueError, TypeError):
        return value

# Load Monday.com API key from environment variable
MONDAY_API_KEY = os.getenv('MONDAY_API_KEY')
if not MONDAY_API_KEY:
    raise ValueError("MONDAY_API_KEY environment variable is not set")

# Cache for Monday.com data
data_cache = {
    'data': None,
    'last_fetch': None
}

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            user.last_login = datetime.utcnow()
            db.session.commit()
            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('signup'))
        
        user = User(name=name, email=email)
        user.set_password(password)
        
        try:
            db.session.add(user)
            db.session.commit()
            session['user_id'] = user.id
            flash('Account created successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('Error creating account. Please try again.', 'error')
            print(f"Error creating user: {e}")
    
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    user = User.query.get(session['user_id'])
    return render_template('home.html', user=user)

@app.route('/dashboard')
@login_required
def dashboard():
    """Render the dashboard template without fetching data."""
    try:
        # Get default date ranges for the filter form
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = datetime.now().strftime('%Y-%m-%d')
        date_column = 'Date Created'

        return render_template('dashboard.html',
                             user=User.query.get(session['user_id']),
                             has_data=False,
                             start_date=start_date,
                             end_date=end_date,
                             date_column=date_column)

    except Exception as e:
        print(f"Error in dashboard route: {str(e)}")
        import traceback
        print("Traceback:")
        print(traceback.format_exc())
        flash('An error occurred while loading the dashboard. Please try again.', 'error')
        return render_template('dashboard.html',
                             user=User.query.get(session['user_id']),
                             has_data=False)

@app.route('/settings')
@login_required
def settings():
    user = User.query.get(session['user_id'])
    return render_template('settings.html', user=user)

@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id'])
    return render_template('profile.html', user=user)

def get_cached_data(force_refresh=False):
    """
    Get Monday.com data from cache or fetch new data if cache is expired or force refresh is requested
    """
    print("\n=== Checking Cache ===")
    current_time = datetime.now()
    
    if force_refresh:
        print("Force refresh requested")
    elif data_cache['data'] is None:
        print("Cache is empty")
    elif data_cache['last_fetch'] is None:
        print("No last fetch time")
    elif current_time - data_cache['last_fetch'] > timedelta(minutes=5):
        print("Cache expired")
    else:
        print("Using cached data from:", data_cache['last_fetch'])
        return data_cache['data']
    
    try:
        print("Fetching fresh data from Monday.com...")
        data_cache['data'] = fetch_monday_data(MONDAY_API_KEY)
        data_cache['last_fetch'] = current_time
        print("Data fetched successfully")
        return data_cache['data']
    except Exception as e:
        print(f"Error fetching Monday.com data: {e}")
        import traceback
        print("Traceback:")
        print(traceback.format_exc())
        return None

@app.route('/api/dashboard-data')
@login_required
def dashboard_data():
    """API endpoint for fetching and processing dashboard data."""
    try:
        print("\n=== Dashboard Data Request ===")
        # Check if this is a force refresh request
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        print(f"Force refresh: {force_refresh}")
        
        # Get query parameters
        start_date = request.args.get('start_date', 
                                    (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        date_column = request.args.get('date_column', 'Date Created')

        print(f"Request parameters:")
        print(f"- Start date: {start_date}")
        print(f"- End date: {end_date}")
        print(f"- Date column: {date_column}")

        # Get data from cache or fetch new data
        print("Fetching data from Monday.com...")
        dataframes = get_cached_data(force_refresh)
        if not dataframes:
            return jsonify({
                'success': False,
                'error': 'Failed to fetch data from Monday.com',
                'details': 'Please check your API key and try again.'
            }), 500

        print("Processing data...")
        # Process data
        processed_data = process_sales_data(
            dataframes,
            start_date,
            end_date,
            date_column
        )

        # Get performance metrics for charts
        metrics = get_performance_metrics(dataframes, start_date, end_date)

        # Calculate total metrics
        total_metrics = next((record for record in processed_data if record['Owner'] == 'Total'), {})
        
        print("Preparing response...")
        # Create Plotly charts
        import plotly.graph_objects as go

        # Revenue Chart
        revenue_chart = go.Figure(data=[
            go.Bar(
                x=[m['owner'] for m in metrics['closed_revenue']],
                y=[m['value'] for m in metrics['closed_revenue']],
                name='Revenue',
                marker_color='#4F46E5'
            )
        ])
        revenue_chart.update_layout(
            title='Revenue by Owner',
            xaxis_title='Owner',
            yaxis_title='Revenue ($)',
            showlegend=True,
            height=400
        )

        # Close Rate Chart
        close_rate_chart = go.Figure(data=[
            go.Bar(
                x=[m['owner'] for m in metrics['close_rate']],
                y=[m['value'] for m in metrics['close_rate']],
                name='Close Rate',
                marker_color='#7C3AED'
            )
        ])
        close_rate_chart.update_layout(
            title='Close Rate by Owner',
            xaxis_title='Owner',
            yaxis_title='Close Rate (%)',
            showlegend=True,
            height=400
        )

        # New Calls Chart
        new_calls_chart = go.Figure(data=[
            go.Bar(
                x=[m['owner'] for m in metrics['new_calls']],
                y=[m['value'] for m in metrics['new_calls']],
                name='New Calls',
                marker_color='#2563EB'
            )
        ])
        new_calls_chart.update_layout(
            title='New Calls by Owner',
            xaxis_title='Owner',
            yaxis_title='Number of Calls',
            showlegend=True,
            height=400
        )

        # Sales Calls Chart
        sales_calls_chart = go.Figure(data=[
            go.Bar(
                x=[m['owner'] for m in metrics['sales_calls_taken']],
                y=[m['value'] for m in metrics['sales_calls_taken']],
                name='Sales Calls',
                marker_color='#059669'
            )
        ])
        sales_calls_chart.update_layout(
            title='Sales Calls by Owner',
            xaxis_title='Owner',
            yaxis_title='Number of Calls',
            showlegend=True,
            height=400
        )

        # Prepare dashboard data
        dashboard_data = {
            'total_metrics': {
                'new_calls': total_metrics.get('New Calls Booked', 0),
                'sales_calls': total_metrics.get('Sales Call Taken', 0),
                'show_rate': round(total_metrics.get('Show Rate %', 0), 2),
                'unqualified_rate': round(total_metrics.get('Unqualified Rate %', 0), 2),
                'cancellation_rate': round(total_metrics.get('Cancellation Rate %', 0), 2),
                'proposal_rate': round(total_metrics.get('Proposal Rate %', 0), 2),
                'close_rate': round(total_metrics.get('Close Rate %', 0), 2),
                'close_rate_show': round(total_metrics.get('Close Rate(Show) %', 0), 2),
                'close_rate_mql': round(total_metrics.get('Close Rate(MQL) %', 0), 2),
                'revenue': total_metrics.get('Closed Revenue $', 0),
                'revenue_per_call': round(total_metrics.get('Revenue Per Call $', 0), 2),
                'revenue_per_showed_up': round(total_metrics.get('Revenue Per Showed Up $', 0), 2),
                'revenue_per_proposal': round(total_metrics.get('Revenue Per Proposal $', 0), 2),
                'pipeline_revenue': total_metrics.get('Pipeline Revenue $', 0)
            },
            'charts': {
                'revenue': revenue_chart.to_json(),
                'closeRate': close_rate_chart.to_json(),
                'newCalls': new_calls_chart.to_json(),
                'salesCalls': sales_calls_chart.to_json()
            },
            'table_data': [record for record in processed_data if record['Owner'] != 'Total']
        }

        return jsonify({
            'success': True,
            'data': dashboard_data
        })

    except Exception as e:
        print(f"Error in dashboard_data: {str(e)}")
        import traceback
        print("Traceback:")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e),
            'details': 'An error occurred while processing the dashboard data.'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
