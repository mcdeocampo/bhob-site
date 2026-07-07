"""
BHOB Site — Flask server
Serves static files, weather/tide proxy, announcement management API, and secure admin auth.
Data layer: Supabase Postgres + Supabase Storage.
"""
import os
import time
import uuid
import hashlib
import hmac
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Flask, jsonify, send_from_directory, abort, request, session, redirect

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Contact form
@app.route('/api/contact', methods=['POST'])
def api_contact():
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip()
    phone = str(data.get('phone', '')).strip()
    subject = str(data.get('subject', '')).strip()
    message = str(data.get('message', '')).strip()
    if not name or not email or not message:
        return jsonify({'success': False, 'error': 'Please provide name, email, and message'}), 400
    brevo_api_key = os.environ.get('BREVO_API_KEY', '')
    sender_email = os.environ.get('BREVO_SENDER_EMAIL', 'web@huloobando.com')
    sender_name = os.environ.get('BREVO_SENDER_NAME', 'Barangay Hulo')
    admin_email = os.environ.get('ADMIN_EMAIL', 'contact@huloobando.com')
    public_email = os.environ.get('PUBLIC_CONTACT_EMAIL', 'contact@huloobando.com')
    if not brevo_api_key:
        return jsonify({'success': False, 'error': 'Email service not configured'}), 500
    submitted_at = _manila_now().strftime('%B %d, %Y %I:%M %p PHT')
    def send_brevo(payload):
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request('https://api.brevo.com/v3/smtp/email', data=body, headers={'Content-Type': 'application/json', 'api-key': brevo_api_key}, method='POST')
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    try:
        send_brevo({'sender': {'name': sender_name, 'email': sender_email}, 'to': [{'email': admin_email, 'name': 'Barangay Hulo'}], 'replyTo': {'email': email, 'name': name}, 'subject': 'New Website Inquiry', 'htmlContent': '<h2>New Inquiry</h2><b>Name:</b> ' + name + '<br><b>Email:</b> ' + email + '<br><b>Phone:</b> ' + (phone or 'N/A') + '<br><b>Subject:</b> ' + (subject or 'N/A') + '<br><b>Message:</b><br>' + message})
        send_brevo({'sender': {'name': sender_name, 'email': sender_email}, 'to': [{'email': email, 'name': name}], 'replyTo': {'email': public_email, 'name': sender_name}, 'subject': 'We Received Your Inquiry - Barangay Hulo', 'htmlContent': '<p>Dear ' + name + ',</p><p>Thank you for reaching out. We have received your inquiry and will get back to you soon.</p><p>Regards,<br><strong>Barangay Hulo</strong></p>'})
        return jsonify({'success': True})
    except Exception as e:
        print(f'[contact] Error: {e}')
        return jsonify({'success': False, 'error': 'Unable to send message'}), 500
_ensure_initial_user()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
