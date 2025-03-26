import logging
from flask import current_app, jsonify
import json
import requests
import openai
import re

def log_http_response(response):
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")

def get_text_message_input(recipient, text):
    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
    )

def send_message(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }

    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/messages"

    try:
        response = requests.post(
            url, data=data, headers=headers, timeout=10
        )
        response.raise_for_status()
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return jsonify({"status": "error", "message": "Request timed out"}), 408
    except requests.RequestException as e:
        logging.error(f"Request failed due to: {e}")
        return jsonify({"status": "error", "message": "Failed to send message"}), 500
    else:
        log_http_response(response)
        return response

def process_text_for_whatsapp(text):
    # Remove brackets
    pattern = r"\【.*?\】"
    text = re.sub(pattern, "", text).strip()

    # Pattern to find double asterisks including the word(s) in between
    pattern = r"\*\*(.*?)\*\*"

    # Replacement pattern with single asterisks
    replacement = r"*\1*"

    # Substitute occurrences of the pattern with the replacement
    whatsapp_style_text = re.sub(pattern, replacement, text)

    return whatsapp_style_text

# Store user threads
user_threads = {}

def generate_response(message_body, wa_id=None, name=None):
    """
    Generate a response using a specific assistant from OpenAI.
    Uses the Assistants API instead of Chat Completions API.
    """
    try:
        client = openai.OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
        
        # Get or create a thread for this user
        thread_id = user_threads.get(wa_id)
        if not thread_id:
            thread = client.beta.threads.create()
            thread_id = thread.id
            user_threads[wa_id] = thread_id
            logging.info(f"Created new thread {thread_id} for user {wa_id}")
        
        # Add the user's message to the thread
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message_body
        )
        
        # Run the assistant on the thread
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=current_app.config['ASSISTANT_ID']  # Use your specific assistant ID
        )
        
        # Wait for the assistant to complete its response
        while True:
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            if run_status.status == 'completed':
                break
            elif run_status.status in ['failed', 'cancelled', 'expired']:
                logging.error(f"Assistant run failed with status: {run_status.status}")
                return "Sorry, I couldn't process your request at the moment."
            # Wait briefly before checking again (to avoid rate limiting)
            import time
            time.sleep(0.5)
        
        # Get the assistant's response
        messages = client.beta.threads.messages.list(
            thread_id=thread_id
        )
        
        # The first message should be the assistant's latest response
        assistant_message = None
        for msg in messages.data:
            if msg.role == "assistant":
                assistant_message = msg
                break
        
        if assistant_message and assistant_message.content:
            # Extract the text content
            response_text = assistant_message.content[0].text.value
            return response_text
        else:
            return "I'm not sure how to respond to that."
            
    except Exception as e:
        logging.error(f"OpenAI API error: {e}")
        return "Sorry, I couldn't process your request at the moment."

def process_whatsapp_message(body):
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]

    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    message_body = message["text"]["body"]

    # Generate response using the assistant
    response = generate_response(message_body, wa_id, name)
    response = process_text_for_whatsapp(response)

    data = get_text_message_input(wa_id, response)  # Send to the user's WhatsApp ID
    send_message(data)

def is_valid_whatsapp_message(body):
    """
    Check if the incoming webhook event has a valid WhatsApp message structure.
    """
    return (
        body.get("object")
        and body.get("entry")
        and body["entry"][0].get("changes")
        and body["entry"][0]["changes"][0].get("value")
        and body["entry"][0]["changes"][0]["value"].get("messages")
        and body["entry"][0]["changes"][0]["value"]["messages"][0]
    )
