# SMS Reminder Application

This application listens for webhooks from GhostPay and sends SMS reminders for pending PIX payments.

## Features

- Receives webhook notifications from GhostPay.
- Sends SMS reminders via Twilio for PIX payments with "PENDING" status.
- Formats currency values for SMS messages.
- Basic phone number formatting (adds "+" if missing).

## Prerequisites

- Python 3.7+
- Twilio account and credentials (Account SID, Auth Token, Phone Number)
- GhostPay account and API credentials (Secret Key)
- Docker (for containerized deployment)

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd sms-rec
    ```

2.  **Create a `.env` file** in the root directory with your credentials:
    ```
    TWILIO_ACCOUNT_SID=your_twilio_account_sid
    TWILIO_AUTH_TOKEN=your_twilio_auth_token
    TWILIO_PHONE_NUMBER=your_twilio_phone_number
    GHOSTPAY_SECRET_KEY=your_ghostpay_secret_key
    # GHOSTPAY_API_URL=https://example.com.br/api/v1 # Optional: Uncomment and set if different from the default in main.py
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Running the Application

### Locally

```bash
python main.py
```
The application will start on `http://localhost:5000` by default.

### Using Docker

1.  **Build the Docker image:**
    ```bash
    docker build -t sms-reminder-app .
    ```

2.  **Run the Docker container:**
    ```bash
    docker run -p 5000:5000 -v $(pwd)/.env:/app/.env sms-reminder-app
    ```
    This command maps port 5000 of the container to port 5000 on your host and mounts your local `.env` file into the container.

## Webhook Configuration

Configure your GhostPay account to send webhook notifications to `YOUR_SERVER_ADDRESS/webhook/ghostpay`.

## Project Structure

```
.
├── Dockerfile        # Defines the Docker image
├── main.py           # Main Flask application logic
├── requirements.txt  # Python dependencies
├── .env              # Environment variables (ignored by git)
└── README.md         # This file
```

## API Endpoints

-   `POST /webhook/ghostpay`: Receives webhook data from GhostPay.

## How it Works

1.  GhostPay sends a POST request to the `/webhook/ghostpay` endpoint when a payment event occurs.
2.  The application checks if the payment method is "PIX" and the status is "PENDING".
3.  If both conditions are met, it extracts the customer's phone number and the payment amount.
4.  It formats a reminder message and sends it as an SMS using the Twilio API.
5.  The application logs the outcome of the SMS sending process.

## Customization

-   **SMS Message Content**: Modify the `message_body` variable in the `ghostpay_webhook` function in `main.py` to change the SMS text.
-   **Store Name**: Replace `[Nome da Sua Loja/Serviço]` in the `message_body` with your actual store or service name.
-   **Twilio Phone Number Formatting**: The current implementation does a basic check to add a `+` to the phone number if it's missing. You might need to adjust this based on the phone number formats you receive from GhostPay.
-   **GhostPay API URL**: If the GhostPay API URL is different from the placeholder, update `GHOSTPAY_API_URL` in `main.py` or set it in your `.env` file.

## Production Considerations

-   Use a production-ready WSGI server like Gunicorn instead of Flask's built-in development server.
    Example Gunicorn command within Docker (modify `CMD` in `Dockerfile`):
    ```Dockerfile
    CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]
    ```
    And add `gunicorn` to `requirements.txt`.
-   Set `debug=False` in `app.run()` for production environments (or remove `app.run()` if using Gunicorn).
-   Implement more robust error handling and logging.
-   Secure your webhook endpoint, for example, by verifying webhook signatures if GhostPay provides them.
-   Manage secrets securely (e.g., using a secrets management tool instead of just `.env` files in production).
