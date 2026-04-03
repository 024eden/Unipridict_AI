"""
UniPredict AI — Real Email Sender v2
Supports: Gmail, Outlook/Hotmail, Yahoo, Custom SMTP
Config stored in email_config.json
"""
import smtplib, ssl, json, os, socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'email_config.json')

DEFAULT_CONFIG = {
    "enabled": False,
    "provider": "gmail",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    "use_ssl": True,
    "sender_email": "",
    "sender_password": "",
    "sender_name": "UniPredict AI",
    "reply_to": ""
}

PROVIDER_SETTINGS = {
    "gmail": {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 465,
        "use_ssl": True,
        "label": "Gmail",
        "password_label": "App Password (16 chars — NOT your Gmail login password)",
        "help": (
            "Step 1: Enable 2-Step Verification at myaccount.google.com/security\n"
            "Step 2: Go to myaccount.google.com/apppasswords\n"
            "Step 3: Click 'Select app' → Other → type 'UniPredict' → Generate\n"
            "Step 4: Copy the 16-character code and paste it as the password below\n"
            "  (spaces in the code don't matter — Gmail accepts with or without them)"
        )
    },
    "outlook": {
        "smtp_host": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "use_ssl": False,
        "label": "Outlook / Hotmail",
        "password_label": "Your Outlook / Hotmail password",
        "help": (
            "Use your regular Outlook or Hotmail email and password.\n"
            "If login fails: go to account.microsoft.com/security\n"
            "→ Advanced security options → App passwords → Create one."
        )
    },
    "yahoo": {
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 465,
        "use_ssl": True,
        "label": "Yahoo Mail",
        "password_label": "Yahoo App Password (NOT your Yahoo login password)",
        "help": (
            "Step 1: Go to login.yahoo.com → Account Security\n"
            "Step 2: Enable 2-step verification\n"
            "Step 3: Generate an app password → name it 'UniPredict'\n"
            "Step 4: Copy and paste the app password below"
        )
    },
    "custom": {
        "smtp_host": "",
        "smtp_port": 587,
        "use_ssl": False,
        "label": "Custom SMTP",
        "password_label": "SMTP Password",
        "help": "Enter your mail server's SMTP host, port, and credentials."
    }
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
            # Merge with defaults for any missing keys
            merged = {**DEFAULT_CONFIG, **cfg}
            return merged
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)


def get_provider_info(provider: str) -> dict:
    return PROVIDER_SETTINGS.get(provider, PROVIDER_SETTINGS['custom'])


def _build_message(cfg: dict, to_email: str, subject: str,
                   html_body: str, plain_body: str = None) -> MIMEMultipart:
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f"{cfg.get('sender_name', 'UniPredict AI')} <{cfg['sender_email']}>"
    msg['To']      = to_email
    msg['Date']    = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    if cfg.get('reply_to'):
        msg['Reply-To'] = cfg['reply_to']
    plain = plain_body or "Please view this email in an HTML-capable email client."
    msg.attach(MIMEText(plain, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    return msg


def _connect_smtp(host, port, use_ssl, email, password):
    """Open SMTP connection and login. Returns the server object."""
    if use_ssl:
        ctx = ssl.create_default_context()
        server = smtplib.SMTP_SSL(host, int(port), context=ctx, timeout=15)
    else:
        server = smtplib.SMTP(host, int(port), timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
    server.login(email, password)
    return server


def send_email(to_email: str, subject: str, html_body: str,
               plain_body: str = None) -> dict:
    """
    Send a real email. Returns {'success': bool, 'message': str, 'simulated'?: bool}
    """
    cfg = load_config()

    if not cfg.get('enabled'):
        return {
            'success': False,
            'simulated': True,
            'message': (
                'Email sending is disabled. '
                'Go to Admin → 📧 Email Settings, configure your credentials, '
                'test the connection, then toggle Enable ON.'
            )
        }

    if not cfg.get('sender_email'):
        return {'success': False, 'message': 'Sender email address not set. Go to Email Settings.'}
    if not cfg.get('sender_password'):
        return {'success': False, 'message': 'Email password not set. Go to Email Settings.'}

    msg = _build_message(cfg, to_email, subject, html_body, plain_body)
    host     = cfg.get('smtp_host', 'smtp.gmail.com')
    port     = int(cfg.get('smtp_port', 465))
    use_ssl  = bool(cfg.get('use_ssl', True))
    email    = cfg['sender_email']
    password = cfg['sender_password']

    try:
        server = _connect_smtp(host, port, use_ssl, email, password)
        server.send_message(msg)
        server.quit()
        return {'success': True, 'message': f"Email delivered to {to_email}"}

    except smtplib.SMTPAuthenticationError:
        provider = cfg.get('provider', 'gmail')
        hint = ''
        if provider == 'gmail':
            hint = (' For Gmail you MUST use an App Password — not your normal Gmail password. '
                    'Go to myaccount.google.com/apppasswords to create one.')
        elif provider in ('yahoo',):
            hint = ' For Yahoo you must use an App Password from account security settings.'
        return {'success': False,
                'message': f'Authentication failed — wrong email or password.{hint}'}

    except smtplib.SMTPRecipientsRefused:
        return {'success': False, 'message': f'Recipient address rejected by server: {to_email}'}

    except smtplib.SMTPConnectError as e:
        return {'success': False,
                'message': f'Cannot connect to {host}:{port}. Check host/port or your internet connection. ({e})'}

    except socket.timeout:
        return {'success': False,
                'message': f'Connection to {host}:{port} timed out. Check your firewall or try a different port.'}

    except ssl.SSLError as e:
        return {'success': False,
                'message': f'SSL error: {e}. Try toggling SSL on/off or changing the port.'}

    except Exception as e:
        return {'success': False, 'message': f'Unexpected error: {type(e).__name__}: {e}'}


def test_connection(host: str, port: int, use_ssl: bool,
                    email: str, password: str) -> dict:
    """Test SMTP login without sending any email."""
    if not host:
        return {'success': False, 'message': 'SMTP host is required'}
    if not email:
        return {'success': False, 'message': 'Sender email is required'}
    if not password:
        return {'success': False, 'message': 'Password is required'}
    try:
        server = _connect_smtp(host, port, use_ssl, email, password)
        server.quit()
        return {'success': True,
                'message': f'✅ Connected and authenticated successfully as {email}'}
    except smtplib.SMTPAuthenticationError:
        return {'success': False,
                'message': ('❌ Authentication failed — wrong email or password. '
                            'Gmail and Yahoo require an App Password, not your normal login password.')}
    except smtplib.SMTPConnectError as e:
        return {'success': False,
                'message': f'❌ Cannot connect to {host}:{port}. ({e})'}
    except socket.timeout:
        return {'success': False,
                'message': f'❌ Timed out connecting to {host}:{port}. Try another port.'}
    except ssl.SSLError as e:
        return {'success': False,
                'message': f'❌ SSL error: {e}. Try toggling SSL on/off.'}
    except Exception as e:
        return {'success': False,
                'message': f'❌ {type(e).__name__}: {e}'}
