import os
from flask import Flask, request, jsonify
from twilio.rest import Client
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# GhostPay API credentials and URL
GHOSTPAY_SECRET_KEY = os.getenv('GHOSTPAY_SECRET_KEY')
GHOSTPAY_API_URL = "https://example.com.br/api/v1" # Placeholder, replace with actual GhostPay API URL if different

def send_sms(to_phone_number, body_message):
    """Sends an SMS message using Twilio."""
    try:
        message = twilio_client.messages.create(
            body=body_message,
            from_=TWILIO_PHONE_NUMBER,
            to=to_phone_number
        )
        print(f"SMS sent to {to_phone_number}: {message.sid}")
        return True
    except Exception as e:
        print(f"Error sending SMS to {to_phone_number}: {e}")
        return False

@app.route('/webhook/ghostpay', methods=['POST'])
def ghostpay_webhook():
    """Handles incoming webhooks from GhostPay."""
    data = request.json
    print(f"Received webhook: {data}")

    payment_id = data.get('paymentId')
    status = data.get('status')
    payment_method = data.get('paymentMethod')
    customer_info = data.get('customer')
    total_value = data.get('totalValue') # Value in cents

    if not customer_info or not customer_info.get('phone'):
        print(f"Webhook for payment {payment_id}: Customer phone number not found. Cannot send SMS.")
        return jsonify({'status': 'error', 'message': 'Customer phone number missing'}), 400

    customer_phone = customer_info.get('phone')
    # Ensure phone is in E.164 format, Twilio might require it.
    # This is a basic assumption, might need more robust parsing if numbers come in various formats.
    if not customer_phone.startswith('+'):
        customer_phone = '+' + customer_phone # Basic attempt to format, GhostPay docs say DDI is included.

    # Check if it's a PIX payment and it's PENDING
    if payment_method == 'PIX' and status == 'PENDING':
        print(f"PIX payment {payment_id} is PENDING. Sending SMS reminder to {customer_phone}.")

        # Convert value from cents to currency string (e.g., R$ 50,00)
        value_in_reais = total_value / 100
        formatted_value = f"R$ {value_in_reais:.2f}".replace('.', ',')

        message_body = (
            f"Lembrete: Seu PIX no valor de {formatted_value} para [Nome da Sua Loja/Serviço] "
            f"ainda está pendente. Pague agora para garantir seu pedido/serviço. "
            f"ID da transação: {payment_id}"
        )
        # You might want to include a payment link if available from the webhook or GhostPay API
        # e.g., if data.get('pixQrCode') or data.get('checkoutUrl') is useful

        send_sms(customer_phone, message_body)
        return jsonify({'status': 'success', 'message': 'SMS reminder sent for pending PIX.'}), 200
    
    elif status == 'APPROVED':
        print(f"Payment {payment_id} is {status}. No action needed or send a confirmation SMS.")
        # Optionally, send a confirmation SMS for approved payments
        # message_body = f"Seu pagamento PIX de {formatted_value} para [Nome da Sua Loja/Serviço] foi aprovado! ID: {payment_id}"
        # send_sms(customer_phone, message_body)
        return jsonify({'status': 'success', 'message': f'Payment {status}, no reminder needed.'}), 200

    else:
        print(f"Webhook received for payment {payment_id} with status {status} and method {payment_method}. No action taken.")
        return jsonify({'status': 'ignored', 'message': 'Event not relevant for PIX reminder.'}), 200

if __name__ == '__main__':
    # It's recommended to use a proper WSGI server like Gunicorn in production
    # and to run Flask with debug=False in production.
    app.run(debug=True, port=5000) # Port can be configured as needed
