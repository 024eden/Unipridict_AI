"""
UniPredict AI - Utility Functions
Helper functions for common operations
"""

import time
import json
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
import hashlib

# Rate limiting storage
api_rate_limits = {}

def api_rate_limit(max_requests=100, window_seconds=3600):
    """
    API rate limiting decorator
    max_requests: Maximum requests allowed in the time window
    window_seconds: Time window in seconds (default: 1 hour)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get client identifier (IP address)
            client_id = request.remote_addr or 'unknown'
            
            # Get current timestamp
            now = time.time()
            
            # Initialize client data if not exists
            if client_id not in api_rate_limits:
                api_rate_limits[client_id] = []
            
            # Remove old requests outside the window
            api_rate_limits[client_id] = [
                req_time for req_time in api_rate_limits[client_id]
                if now - req_time < window_seconds
            ]
            
            # Check if rate limit exceeded
            if len(api_rate_limits[client_id]) >= max_requests:
                return jsonify({
                    'success': False,
                    'error': f'Rate limit exceeded. Maximum {max_requests} requests per {window_seconds//3600} hour(s).',
                    'retry_after': int(window_seconds - (now - api_rate_limits[client_id][0]))
                }), 429
            
            # Add current request
            api_rate_limits[client_id].append(now)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_activity(user_id, action, details=None):
    """Log user activity for analytics"""
    try:
        log_file = os.path.join(os.path.dirname(__file__), 'data', 'activity_log.json')
        
        # Load existing logs
        logs = []
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                logs = json.load(f)
        
        # Add new log entry
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'action': action,
            'details': details or {},
            'ip_address': getattr(request, 'remote_addr', 'unknown'),
            'user_agent': getattr(request, 'user_agent', {}).get('string', 'unknown') if hasattr(request, 'user_agent') else 'unknown'
        }
        
        logs.append(log_entry)
        
        # Keep only last 10000 entries to prevent file from growing too large
        if len(logs) > 10000:
            logs = logs[-10000:]
        
        # Save logs
        with open(log_file, 'w') as f:
            json.dump(logs, f, indent=2)
            
    except Exception as e:
        print(f"Error logging activity: {e}")

def get_activity_stats(days=7):
    """Get activity statistics for the last N days"""
    try:
        log_file = os.path.join(os.path.dirname(__file__), 'data', 'activity_log.json')
        
        if not os.path.exists(log_file):
            return {}
        
        with open(log_file, 'r') as f:
            logs = json.load(f)
        
        # Filter logs for the last N days
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_logs = [
            log for log in logs 
            if datetime.fromisoformat(log['timestamp']) > cutoff_date
        ]
        
        # Calculate statistics
        stats = {
            'total_actions': len(recent_logs),
            'unique_users': len(set(log['user_id'] for log in recent_logs)),
            'actions_by_type': {},
            'actions_by_user': {},
            'daily_activity': {}
        }
        
        for log in recent_logs:
            # Count by action type
            action = log['action']
            stats['actions_by_type'][action] = stats['actions_by_type'].get(action, 0) + 1
            
            # Count by user
            user_id = log['user_id']
            stats['actions_by_user'][user_id] = stats['actions_by_user'].get(user_id, 0) + 1
            
            # Count by day
            date = log['timestamp'].split('T')[0]
            stats['daily_activity'][date] = stats['daily_activity'].get(date, 0) + 1
        
        return stats
        
    except Exception as e:
        print(f"Error getting activity stats: {e}")
        return {}

def generate_cache_key(prefix, *args, **kwargs):
    """Generate a cache key for function results"""
    key_data = f"{prefix}:{str(args)}:{str(sorted(kwargs.items()))}"
    return hashlib.md5(key_data.encode()).hexdigest()

def validate_student_data(data):
    """Validate student data for CRUD operations"""
    errors = []
    
    # Required fields
    required_fields = ['student_name', 'age', 'attendance_rate', 'study_hours_weekly']
    for field in required_fields:
        if field not in data or not str(data[field]).strip():
            errors.append(f"{field.replace('_', ' ').title()} is required")
    
    # Numeric validations
    numeric_fields = {
        'age': (15, 25),
        'attendance_rate': (0, 100),
        'study_hours_weekly': (0, 40),
        'previous_grades': (0, 100),
        'assignment_completion': (0, 100),
        'class_participation': (1, 10),
        'library_visits': (0, 50),
        'online_resource_hours': (0, 40),
        'stress_level': (1, 10),
        'motivation_score': (1, 10),
        'final_grade': (0, 100)
    }
    
    for field, (min_val, max_val) in numeric_fields.items():
        if field in data and data[field] is not None:
            try:
                value = float(data[field])
                if not (min_val <= value <= max_val):
                    errors.append(f"{field.replace('_', ' ').title()} must be between {min_val} and {max_val}")
            except (ValueError, TypeError):
                errors.append(f"{field.replace('_', ' ').title()} must be a valid number")
    
    # Email validation
    if 'parent_email' in data and data['parent_email']:
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, data['parent_email']):
            errors.append("Invalid parent email format")
    
    return errors

def export_to_csv(data, filename_prefix="unipredict_export"):
    """Export data to CSV format"""
    import csv
    import io
    
    if not data:
        return None, "No data to export"
    
    output = io.StringIO()
    
    # Get headers from first item
    headers = list(data[0].keys()) if data else []
    
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(data)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.csv"
    
    return output.getvalue(), filename

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"
