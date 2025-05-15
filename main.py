import os
from flask import Flask, request, jsonify
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv
import logging

load_dotenv()

app = Flask(__name__)

# Configure logging
if not app.debug:
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    app.logger.addHandler(stream_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('App started in production mode.')
else:
    app.logger.setLevel(logging.DEBUG)
    app.logger.info('App started in debug mode.')

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_API_KEY_SID = os.getenv('TWILIO_API_KEY_SID')
TWILIO_API_KEY_SECRET = os.getenv('TWILIO_API_KEY_SECRET')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Validate Twilio credentials on startup
missing_twilio_creds = []
if not TWILIO_ACCOUNT_SID: missing_twilio_creds.append("TWILIO_ACCOUNT_SID")
if not TWILIO_API_KEY_SID: missing_twilio_creds.append("TWILIO_API_KEY_SID")
if not TWILIO_API_KEY_SECRET: missing_twilio_creds.append("TWILIO_API_KEY_SECRET")
if not TWILIO_PHONE_NUMBER: missing_twilio_creds.append("TWILIO_PHONE_NUMBER")

twilio_client = None
if missing_twilio_creds:
    app.logger.critical(f"Missing Twilio credentials: {', '.join(missing_twilio_creds)}. SMS functionality will be disabled.")
else:
    try:
        twilio_client = Client(TWILIO_API_KEY_SID, TWILIO_API_KEY_SECRET, TWILIO_ACCOUNT_SID)
        app.logger.info("Twilio client initialized successfully.")
    except Exception as e:
        app.logger.critical(f"Failed to initialize Twilio client: {e}. SMS functionality will be disabled.")

# GhostPay API credentials and URL
GHOSTPAY_SECRET_KEY = os.getenv('GHOSTPAY_SECRET_KEY')
GHOSTPAY_API_URL = "https://app.ghostspaysv1.com/docs"

# Duckfy webhook token
DUCKFY_WEBHOOK_TOKEN_CONFIG = os.getenv('DUCKFY_WEBHOOK_TOKEN')

def send_sms(to_phone_number, body_message):
    """Sends an SMS message using Twilio."""
    if not twilio_client:
        app.logger.error("Twilio client is not initialized. Cannot send SMS.")
        return False
    if not TWILIO_PHONE_NUMBER:
        app.logger.error("Twilio phone number is not configured. Cannot send SMS.")
        return False
        
    try:
        message = twilio_client.messages.create(
            body=body_message,
            from_=TWILIO_PHONE_NUMBER,
            to=to_phone_number
        )
        app.logger.info(f"SMS sent to {to_phone_number}: {message.sid}")
        return True
    except TwilioRestException as e:
        app.logger.error(f"Twilio API error sending SMS to {to_phone_number}: {e}")
        return False
    except Exception as e:
        app.logger.error(f"Generic error sending SMS to {to_phone_number}: {e}")
        return False

@app.route('/webhook/ghostpay', methods=['POST'])
def ghostpay_webhook():
    """
    Handles incoming webhooks from GhostPay.
    TODO: Implement GhostPay webhook signature verification if supported.
    """
    if not request.is_json:
        app.logger.warning("GhostPay webhook: Received non-JSON request.")
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.json
    app.logger.info(f"GhostPay webhook: Received data: {data}")

    required_fields = ['paymentId', 'status', 'paymentMethod', 'customer', 'totalValue']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        msg = f"Missing required fields: {', '.join(missing_fields)}"
        app.logger.warning(f"GhostPay webhook: {msg}")
        return jsonify({'status': 'error', 'message': msg}), 400

    customer_info = data.get('customer')
    if not isinstance(customer_info, dict) or not customer_info.get('phone'):
        msg = "Customer phone number missing or customer data invalid"
        app.logger.warning(f"GhostPay webhook for payment {data.get('paymentId', 'N/A')}: {msg}")
        return jsonify({'status': 'error', 'message': msg}), 400

    payment_id = data.get('paymentId')
    status = data.get('status')
    payment_method = data.get('paymentMethod')
    customer_phone_original = str(customer_info.get('phone'))

    # Phone number formatting for E.164 (for Twilio)
    # For robust international phone number parsing and validation, strongly consider using a library like 'phonenumbers'.
    # The following is a simplified logic primarily for Brazilian numbers.
    raw_phone_ghostpay = customer_phone_original
    digits_ghostpay = ''.join(filter(str.isdigit, raw_phone_ghostpay))
    customer_phone_e164 = "" # Initialize to ensure it's set

    if raw_phone_ghostpay.startswith('+'): # Already has '+', assume E.164 or similar
        customer_phone_e164 = raw_phone_ghostpay
    elif digits_ghostpay.startswith('55') and (len(digits_ghostpay) == 12 or len(digits_ghostpay) == 13): # BR number like 55119...
        customer_phone_e164 = '+' + digits_ghostpay
    elif len(digits_ghostpay) == 10 or len(digits_ghostpay) == 11: # BR number like 119... or 113... (DDD + number)
        customer_phone_e164 = '+55' + digits_ghostpay
    else: # Fallback for unrecognized formats
        app.logger.warning(f"GhostPay webhook for payment {payment_id}: Phone '{raw_phone_ghostpay}' has an unrecognized format. Attempting to prefix with '+'. This might be incorrect for non-Brazilian numbers.")
        customer_phone_e164 = '+' + digits_ghostpay

    # Sanity check and logging for the formatted number
    if not (customer_phone_e164.startswith('+') and len(customer_phone_e164) >= 11): # Basic E.164 sanity check
        app.logger.error(f"GhostPay webhook for payment {payment_id}: Phone '{customer_phone_original}' could not be reliably formatted to E.164 (result: '{customer_phone_e164}'). SMS not sent.")
        return jsonify({'status': 'error', 'message': 'Invalid phone number format for SMS sending after internal formatting.'}), 400
    
    app.logger.info(f"GhostPay webhook for payment {payment_id}: Using phone '{customer_phone_e164}' for SMS (original: '{customer_phone_original}').")

    if payment_method == 'PIX' and status == 'PENDING':
        app.logger.info(f"GhostPay webhook: PIX payment {payment_id} is PENDING. Preparing SMS for {customer_phone_e164}.")
        customer_name = customer_info.get('name', 'Cliente')
        checkout_link = data.get('checkoutUrl', data.get('pixQrCode', 'link_do_checkout_aqui'))

        message_body = (
            f"{customer_name} Você viu, pensou demais… e perdeu? "
            f"Ainda dá tempo de garantir sua INDENIZAÇÃO! Mas é só até hoje → https://pay.atendimentoaoclienteseguro.shop/BNjzgPlnjwJgM78"
        )

        if send_sms(customer_phone_e164, message_body):
            return jsonify({'status': 'success', 'message': 'SMS reminder sent for pending PIX.'}), 200
        else:
            app.logger.error(f"GhostPay webhook for payment {payment_id}: Failed to send SMS to {customer_phone_e164}.")
            return jsonify({'status': 'error', 'message': 'Failed to send SMS reminder.'}), 500
    
    elif status == 'APPROVED':
        app.logger.info(f"GhostPay webhook: Payment {payment_id} ({payment_method}) is {status}. No reminder needed.")
        return jsonify({'status': 'success', 'message': f'Payment {status}, no reminder needed.'}), 200

    else:
        app.logger.info(f"GhostPay webhook: Event for payment {payment_id} (status: {status}, method: {payment_method}) ignored.")
        return jsonify({'status': 'ignored', 'message': 'Event not relevant for PIX reminder or already handled.'}), 200

@app.route('/webhook/duckfy', methods=['POST'])
def duckfy_webhook():
    """Handles incoming webhooks from Duckfy."""
    if not request.is_json:
        app.logger.warning("Duckfy webhook: Received non-JSON request.")
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    data = request.json
    app.logger.info(f"Duckfy webhook: Received data: {data}")

    received_token = data.get('token')
    if DUCKFY_WEBHOOK_TOKEN_CONFIG and received_token != DUCKFY_WEBHOOK_TOKEN_CONFIG:
        app.logger.warning(f"Duckfy webhook: Invalid token received.")
        return jsonify({'status': 'error', 'message': 'Invalid token'}), 403

    transaction_data = data.get('transaction')
    client_data = data.get('client')

    if not isinstance(transaction_data, dict) or not isinstance(client_data, dict):
        app.logger.warning("Duckfy webhook: Missing or invalid transaction or client data structure.")
        return jsonify({'status': 'error', 'message': 'Missing or invalid transaction or client data structure'}), 400

    required_tx_fields = ['id', 'status', 'paymentMethod', 'amount']
    missing_tx_fields = [field for field in required_tx_fields if field not in transaction_data]
    if missing_tx_fields:
        msg = f"Missing transaction fields: {', '.join(missing_tx_fields)}"
        app.logger.warning(f"Duckfy webhook: {msg}")
        return jsonify({'status': 'error', 'message': msg}), 400

    if 'phone' not in client_data:
        msg = "Client phone number missing"
        app.logger.warning(f"Duckfy webhook for transaction {transaction_data.get('id', 'N/A')}: {msg}")
        return jsonify({'status': 'error', 'message': msg}), 400

    transaction_id = transaction_data.get('id')
    status = transaction_data.get('status')
    payment_method = transaction_data.get('paymentMethod')
    customer_phone_original = str(client_data.get('phone'))
    amount = transaction_data.get('amount') 
    currency = transaction_data.get('currency', 'BRL')

    product_name = "seu produto/serviço"
    order_items = data.get('orderItems')
    if isinstance(order_items, list) and order_items and isinstance(order_items[0], dict) and \
       order_items[0].get('product') and isinstance(order_items[0]['product'], dict) and order_items[0]['product'].get('name'):
        product_name = order_items[0]['product']['name']
    
    raw_phone = customer_phone_original
    digits = ''.join(filter(str.isdigit, raw_phone))
    customer_phone_e164 = ""

    if raw_phone.startswith('+'):
        customer_phone_e164 = raw_phone
    elif digits.startswith('55') and (len(digits) == 12 or len(digits) == 13):
        customer_phone_e164 = '+' + digits
    elif len(digits) == 10 or len(digits) == 11:
        customer_phone_e164 = '+55' + digits
    else:
        app.logger.warning(f"Duckfy webhook for transaction {transaction_id}: Phone '{raw_phone}' has an unrecognized format. Attempting to prefix with '+'.")
        customer_phone_e164 = '+' + digits

    if not (customer_phone_e164.startswith('+') and len(customer_phone_e164) >= 11):
        app.logger.error(f"Duckfy webhook for transaction {transaction_id}: Phone '{customer_phone_original}' could not be reliably formatted to E.164 (result: '{customer_phone_e164}').")
        return jsonify({'status': 'error', 'message': 'Invalid phone number format for SMS sending.'}), 400
    
    app.logger.info(f"Duckfy webhook for transaction {transaction_id}: Using phone '{customer_phone_e164}' for SMS (original: '{customer_phone_original}').")

    if payment_method != 'PIX':
        app.logger.info(f"Duckfy webhook: Tx {transaction_id} method {payment_method} ignored (product only PIX).")
        return jsonify({'status': 'ignored', 'message': f'Payment method {payment_method} not supported. Only PIX is accepted.'}), 200

    if status == 'PENDING':
        app.logger.info(f"Duckfy webhook: PIX transaction {transaction_id} is PENDING. Preparing SMS for {customer_phone_e164}.")
        customer_name = client_data.get('name', '')
        checkout_link = transaction_data.get('checkoutUrl', transaction_data.get('paymentLink', 'link_do_checkout_aqui'))
        
        message_body = (
            f"{customer_name} Você viu, pensou demais… e perdeu? "
            f"Ainda dá tempo de garantir sua INDENIZAÇÃO! Mas é só até hoje → https://pay.atendimentoaoclienteseguro.shop/BNjzgPlnjwJgM78"
        )

        if send_sms(customer_phone_e164, message_body):
            return jsonify({'status': 'success', 'message': 'SMS reminder sent for pending PIX.'}), 200
        else:
            app.logger.error(f"Duckfy webhook for transaction {transaction_id}: Failed to send SMS to {customer_phone_e164}.")
            return jsonify({'status': 'error', 'message': 'Failed to send SMS reminder.'}), 500
    
    elif status == 'COMPLETED':
        app.logger.info(f"Duckfy webhook: PIX transaction {transaction_id} is {status}. No reminder needed.")
        return jsonify({'status': 'success', 'message': f'PIX Payment {status}, no reminder needed.'}), 200

    else:
        app.logger.info(f"Duckfy webhook: PIX transaction {transaction_id} with status {status} ignored.")
        return jsonify({'status': 'ignored', 'message': f'PIX event with status {status} not processed.'}), 200

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true', 
            port=int(os.getenv('PORT', 5000)),
            host='0.0.0.0')
